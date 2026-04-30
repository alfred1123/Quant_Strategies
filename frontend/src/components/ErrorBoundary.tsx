import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Box, Typography, Button } from '@mui/material';

interface Props { children: ReactNode }
interface State { error: Error | null; resetKey: number }

/**
 * Catches render errors from descendants and shows a fallback UI.
 *
 * "Try Again" both clears the boundary's error state AND bumps `resetKey`,
 * which forces React to remount the entire child subtree. Without the key
 * bump, a broken child component would re-throw on the next render and the
 * fallback would flicker straight back.
 */
export default class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null, resetKey: 0 };

  static getDerivedStateFromError(error: Error) { return { error }; }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  private handleReset = () => {
    this.setState(prev => ({ error: null, resetKey: prev.resetKey + 1 }));
  };

  override render() {
    if (this.state.error) {
      return (
        <Box sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h6" color="error" gutterBottom>Something went wrong</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontFamily: 'monospace' }}>
            {this.state.error.message}
          </Typography>
          <Button variant="outlined" onClick={this.handleReset}>
            Try Again
          </Button>
        </Box>
      );
    }
    return <div key={this.state.resetKey}>{this.props.children}</div>;
  }
}
