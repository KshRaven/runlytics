'use strict';
/* The "i" button: a short description per chart. Custom text comes from `description=` in the logging code;
   otherwise a generic explanation of the chart type is shown. */
const HINT_KIND = { line: 'scalars', hist: 'histograms', image: 'images', audio: 'audio', text: 'text', graph: 'graphs',
  projector: 'projector', pr: 'pr_curves', hparams: 'hparams', custom: 'custom_scalars', mesh: 'mesh' };   // card kind -> tag kind (extended by other views)
const DEFAULT_HINTS = {
  scalars: 'A single number logged over time (**step**). Hover to compare runs, drag to zoom, double-click to reset. ' +
    'Smoothing is a display-only moving average; the faint line is the raw value.',
  histograms: 'How a set of values (weights, gradients, activations…) is distributed, one outline per logged step. ' +
    'Horizontal axis: value. Height: how many values fell in that range. Offset mode stacks steps in time; overlay draws them on top of each other.',
  images: 'Images logged at different steps. Drag the slider to move through steps; brightness and contrast only change how it is displayed.',
  audio: 'Audio clips logged at different steps. Drag the slider to pick a step, then press play.',
  text: 'Text logged at different steps (Markdown is rendered). Drag the slider to move through steps.',
  graphs: 'The structure of the model: each box is a layer or operation (name above, type below), arrows follow the data. Scroll to zoom, drag to pan, click a box for details, double-click to fit.',
  projector: 'High-dimensional points (embeddings) projected onto their 3 strongest directions (PCA). Drag to rotate, scroll to zoom, hover a point for its label. Points that sit close together are similar to the model.',
  pr_curves: 'Precision (how many predicted positives were right) against recall (how many real positives were found) as the decision threshold moves from 0 to 1. A curve hugging the top-right corner is better. Use the slider to see other steps.',
  hparams: 'One row per run with the hyper-parameters it was started with and the final metrics it reached. Click a column to sort; shaded bars compare metric values across runs.',
  custom_scalars: 'Several scalar tags drawn together in one chart, as arranged by the layout logged with add_custom_scalars. Interaction is the same as in Scalars.',
  mesh: 'A 3D point cloud or mesh logged at different steps. Drag to rotate, scroll to zoom, double-click to reset, use the slider to change step.'
};
function hintFor(kind, tag) {
  const d = S.tags.desc && S.tags.desc[kind] && S.tags.desc[kind][tag];
  return { text: d || DEFAULT_HINTS[kind] || 'No description available.', custom: !!d };
}
function closeHints() { document.querySelectorAll('.hint').forEach(h => { h.parentNode.querySelector('.ci').classList.remove('on'); h.remove(); }); }
function toggleHint(card, kind, tag) {
  const open = $('.hint', card); closeHints();
  if (open) return;
  const { text, custom } = hintFor(kind, tag), h = el('div', 'hint');
  h.innerHTML = `<div class="hh">${esc(tag)}</div><div class="hb">${mdLite(text)}</div>` +
    (custom ? '' : '<div class="hf">No description was logged for this chart. Add one with <code>description="…"</code> when logging.</div>');
  h.addEventListener('click', e => e.stopPropagation());
  card.append(h); $('.ci', card).classList.add('on');
}
document.addEventListener('click', closeHints);
addEventListener('keydown', e => { if (e.key === 'Escape') closeHints(); });
