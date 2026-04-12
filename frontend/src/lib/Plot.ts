/* eslint-disable @typescript-eslint/no-explicit-any */
import _Plot from 'react-plotly.js';

// react-plotly.js is CJS (exports.default = Component).
// Vite's dev-server CJS interop can deliver it as { default: Component }
// instead of unwrapping the default automatically.
const Plot: typeof _Plot =
  typeof _Plot === 'function'
    ? _Plot
    : ((_Plot as any).default as typeof _Plot);

export default Plot;
