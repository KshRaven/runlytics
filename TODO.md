# TODO

## Pending
- Custom scalars: Margin charts are drawn as three lines; add a shaded lower/upper band.
- add_graph: only logs the module hierarchy (or a node list you supply); no traced dataflow yet.
- add_embedding: `label_img` is accepted but ignored; no t-SNE/UMAP, PCA only.
- add_mesh: points and wireframe only; no lighting or filled faces.
- Per-chart x-zoom refetch for relative/wall-time axes.
- Optional CRC verification flag when reading event files.
- Auth/TLS options for the server.
- Writer: `add_tensor`-style generic tensors.
- UI: remaining TensorBoard settings not yet present (per-tab image actual-size, partition non-monotonic X, run grouping/regex colouring, tag-group regex sections).
- UI: persisted view state is per browser (localStorage) and keyed to the server boot id; no server-side or URL-shareable state yet.
