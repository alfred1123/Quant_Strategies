import { Component, Suspense, lazy } from 'react';
import type { ComponentType, ReactNode } from 'react';
import type { PlotParams } from 'react-plotly.js';

// react-plotly.js is CJS (`module.exports.default = Component`). Vite's
// dev-server CJS interop sometimes hands us the raw module namespace
// (`{ default: Component }`) instead of unwrapping the default export.
// Detect that shape and pull `.default` out without leaking `any`.
function hasDefault(x: unknown): x is { default: ComponentType<PlotParams> } {
  return typeof x === 'object' && x !== null && typeof (x as { default?: unknown }).default === 'function';
}

// plotly.js is roughly 4 MB of the build. Importing it on demand keeps it out
// of the entry chunk: a page with no chart never downloads it, and a failed
// fetch costs one chart instead of blanking the whole app.
const LazyPlot = lazy(async () => {
  const raw = (await import('react-plotly.js')).default as unknown;
  if (typeof raw === 'function') return { default: raw as ComponentType<PlotParams> };
  if (hasDefault(raw)) return { default: raw.default };
  return { default: raw as ComponentType<PlotParams> };
});

// A chunk that fails to fetch throws while rendering, which unmounts everything
// above it unless the throw is caught here.
class PlotBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  override render() {
    if (this.state.failed) return <p style={{ color: '#ef5350' }}>Plotly failed to load.</p>;
    return this.props.children;
  }
}

export default function Plot(props: PlotParams) {
  return (
    <PlotBoundary>
      <Suspense fallback={null}>
        <LazyPlot {...props} />
      </Suspense>
    </PlotBoundary>
  );
}
