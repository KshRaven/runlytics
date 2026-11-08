"""Writer methods for structured summaries: graphs, PR curves, HParams, custom scalars, embeddings, mesh."""
from __future__ import annotations

import json
import os
import time
import warnings

from ..core import encode_event, json_value, scalar_value, summary
from ..utils.arrays import np, require_numpy, to_float, to_numpy

__all__ = ["StructuredMixin"]

_MAX_EMBED_POINTS, _MAX_EMBED_DIMS, _MAX_MESH_VERTS = 5000, 128, 100_000


def _plain(v):
    """JSON-friendly scalar (numbers, bools and strings pass through; anything else becomes text)."""
    if hasattr(v, "item"):
        v = v.item()
    return v if isinstance(v, (bool, int, float, str)) else str(v)


class StructuredMixin:
    # ---- graphs ------------------------------------------------------------------------------
    def _emit_graph(self, spec) -> None:
        if self._main is not None:
            self._main.add(encode_event(time.time(), 0, graph_def=json.dumps(spec, separators=(",", ":")).encode()))

    def add_graph(self, model, input_to_model=None, verbose=False, use_strict_trace=True):
        """Log a model graph. Accepts ``{"nodes": [{"name", "op", "inputs"}]}``, a list of such nodes, or any
        object with ``named_modules()`` (its module hierarchy is logged)."""
        self._emit_graph(_graph_spec(model))

    def add_onnx_graph(self, onnx_model_file):
        """Log an ONNX model's dataflow graph (needs the ``onnx`` package)."""
        try:
            import onnx
        except ImportError as e:  # pragma: no cover
            raise ImportError("add_onnx_graph needs the 'onnx' package") from e
        g = onnx.load(onnx_model_file).graph
        nodes, made = [{"name": i.name, "op": "Input", "inputs": []} for i in g.input], {}
        for i, n in enumerate(g.node):
            name = n.name or "%s_%d" % (n.op_type, i)
            for o in n.output:
                made[o] = name
            nodes.append({"name": name, "op": n.op_type, "inputs": [made.get(x, x) for x in n.input if x in made or any(x == i.name for i in g.input)]})
        self._emit_graph({"nodes": nodes})

    # ---- precision / recall ------------------------------------------------------------------
    def add_pr_curve(self, tag, labels, predictions, global_step=None, num_thresholds=127, weights=None,
                     walltime=None, *, description=None):
        require_numpy("add_pr_curve")
        y = to_numpy(labels).astype("float64").ravel() > 0.5
        p = np.clip(to_numpy(predictions).astype("float64").ravel(), 0.0, 1.0)
        w = np.ones_like(p) if weights is None else to_numpy(weights).astype("float64").ravel()
        n = int(num_thresholds)
        bucket = np.clip(np.floor(p * (n - 1) + 1e-9).astype(int), 0, n - 1)
        pos = np.bincount(bucket[y], weights=w[y], minlength=n)
        neg = np.bincount(bucket[~y], weights=w[~y], minlength=n)
        tp, fp = pos[::-1].cumsum()[::-1], neg[::-1].cumsum()[::-1]   # predictions >= threshold i
        P, N = pos.sum(), neg.sum()
        self.add_pr_curve_raw(tag, tp, fp, N - fp, P - tp, tp / np.maximum(tp + fp, 1e-12),
                              tp / np.maximum(P, 1e-12), global_step, walltime, description=description)

    def add_pr_curve_raw(self, tag, true_positive_counts, false_positive_counts, true_negative_counts,
                         false_negative_counts, precision, recall, global_step=None, walltime=None,
                         num_thresholds=127, weights=None, *, description=None):
        lst = lambda a: [round(float(x), 6) for x in a]  # noqa: E731
        obj = dict(tp=lst(true_positive_counts), fp=lst(false_positive_counts), tn=lst(true_negative_counts),
                   fn=lst(false_negative_counts), precision=lst(precision), recall=lst(recall))
        self._emit(summary(json_value(tag, obj, "pr_curves", description)), global_step, walltime)

    # ---- hyper-parameters ----------------------------------------------------------------------
    def add_hparams(self, hparam_dict, metric_dict, hparam_domain_discrete=None, run_name=None, global_step=None, *,
                    description=None):
        """Log one trial: hyper-parameters plus final metrics, as a sub-run of this log directory."""
        w = self._writer(os.path.join(self.logdir, str(run_name or time.time())))
        if w is None:
            return
        obj = dict(hparams={k: _plain(v) for k, v in hparam_dict.items()}, metrics=list(metric_dict),
                   domain={k: [_plain(x) for x in v] for k, v in (hparam_domain_discrete or {}).items()})
        self._emit(summary(json_value("Hyperparameters", obj, "hparams", description)), global_step, None, w)
        for k, v in metric_dict.items():
            self._emit(summary(scalar_value(k, to_float(v))), global_step, None, w)

    # ---- custom scalars ------------------------------------------------------------------------
    def add_custom_scalars(self, layout, *, description=None):
        """``layout = {category: {chart: ["Multiline", [tag_regex, ...]] | ["Margin", [[value, lower, upper]]]}}``."""
        self._emit(summary(json_value("custom_scalars__config__", layout, "custom_scalars", description)), 0, None)

    def _custom_chart(self, category, title, spec):
        self.__dict__.setdefault("_cs_layout", {}).setdefault(category, {})[title] = spec
        self.add_custom_scalars(self._cs_layout)

    def add_custom_scalars_multilinechart(self, tags, category="default", title="untitled"):
        self._custom_chart(category, title, ["Multiline", list(tags)])

    def add_custom_scalars_marginchart(self, tags, category="default", title="untitled"):
        if len(tags) != 3:
            raise ValueError("a margin chart needs exactly 3 tags: value, lower, upper")
        self._custom_chart(category, title, ["Margin", [list(tags)]])

    # ---- embeddings / mesh ---------------------------------------------------------------------
    def add_embedding(self, mat, metadata=None, label_img=None, global_step=None, tag="default",
                      metadata_header=None, *, description=None):
        """Log points for the Embeddings tab (PCA is computed in the browser). Large inputs are subsampled to
        ``5000`` points and reduced to ``128`` dimensions."""
        require_numpy("add_embedding")
        a = to_numpy(mat).astype("float64")
        a = a.reshape(len(a), -1)
        idx = None
        if len(a) > _MAX_EMBED_POINTS:
            warnings.warn("runlytics: embedding subsampled to %d points" % _MAX_EMBED_POINTS, stacklevel=2)
            idx = np.linspace(0, len(a) - 1, _MAX_EMBED_POINTS).round().astype(int)
            a = a[idx]
        if a.shape[1] > _MAX_EMBED_DIMS:
            c = a - a.mean(0)
            a = c @ np.linalg.svd(c, full_matrices=False)[2][:_MAX_EMBED_DIMS].T
        meta, header = None, None
        if metadata is not None:
            meta = [m if isinstance(m, (list, tuple)) else [m] for m in (metadata if idx is None else [metadata[i] for i in idx])]
            meta = [[str(_plain(x)) for x in row] for row in meta]
            header = list(metadata_header) if metadata_header else (["label"] if len(meta[0]) == 1 else ["col%d" % i for i in range(len(meta[0]))])
        obj = dict(shape=list(a.shape), data=np.round(a, 5).ravel().tolist(), metadata=meta, header=header)
        self._emit(summary(json_value(tag, obj, "projector", description)), global_step, None)

    def add_mesh(self, tag, vertices, colors=None, faces=None, config_dict=None, global_step=None, walltime=None, *,
                 description=None):
        """Log a 3D point cloud or triangle mesh (``vertices`` ``(N, 3)`` or ``(1, N, 3)``)."""
        require_numpy("add_mesh")

        def arr(x):
            a = to_numpy(x)
            return a[0] if a.ndim == 3 else a
        v = arr(vertices)[:_MAX_MESH_VERTS]
        obj = dict(v=np.round(v.astype("float64"), 4).tolist(),
                   c=None if colors is None else arr(colors)[:len(v)].astype(int).tolist(),
                   f=None if faces is None else arr(faces).astype(int).tolist(), config=config_dict or {})
        self._emit(summary(json_value(tag, obj, "mesh", description)), global_step, walltime)

    # ---- export --------------------------------------------------------------------------------
    def export_scalars_to_json(self, path):
        """Write every scalar logged through this writer as ``{tag: [[wall, step, value], ...]}``."""
        with open(path, "w") as f:
            json.dump(self._scalar_log, f)


def _graph_spec(model) -> dict:
    if isinstance(model, dict) and "nodes" in model:
        return {"nodes": list(model["nodes"])}
    if isinstance(model, (list, tuple)):
        return {"nodes": list(model)}
    if hasattr(model, "named_modules"):
        root = type(model).__name__
        nodes = []
        for name, m in model.named_modules():
            if not name:
                nodes.append({"name": root, "op": root, "inputs": []})
                continue
            parent = name.rpartition(".")[0]
            extra = m.extra_repr() if hasattr(m, "extra_repr") else ""
            nodes.append({"name": root + "/" + name.replace(".", "/"), "op": type(m).__name__,
                          "inputs": [root + "/" + parent.replace(".", "/") if parent else root], "attrs": extra[:200]})
        return {"nodes": nodes}
    raise TypeError("add_graph expects a dict/list of nodes or an object with named_modules()")
