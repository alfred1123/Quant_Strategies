import _Plot from 'react-plotly.js';

// react-plotly.js is CJS (`module.exports.default = Component`). Vite's
// dev-server CJS interop sometimes hands us the raw module namespace
// (`{ default: Component }`) instead of unwrapping the default export.
// Detect that shape and pull `.default` out without leaking `any`.
type PlotComponent = typeof _Plot;

// We deliberately type the import as `unknown` for the runtime check below —
// TS's static type for `_Plot` is the unwrapped component, but at runtime it
// can also be the raw namespace object.
const raw = _Plot as unknown;

function hasDefault(x: unknown): x is { default: PlotComponent } {
  return typeof x === 'object' && x !== null && typeof (x as { default?: unknown }).default === 'function';
}

const Plot: PlotComponent =
  typeof raw === 'function'
    ? (raw as PlotComponent)
    : hasDefault(raw)
      ? raw.default
      : (raw as PlotComponent);

export default Plot;
