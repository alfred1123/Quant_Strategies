import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ErrorBoundary from './ErrorBoundary';

let shouldThrow = false;

function Thrower() {
  if (shouldThrow) throw new Error('test explosion');
  return <div>child content</div>;
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    shouldThrow = false;
    render(
      <ErrorBoundary><Thrower /></ErrorBoundary>,
    );
    expect(screen.getByText('child content')).toBeInTheDocument();
  });

  it('renders error message when child throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    shouldThrow = true;

    render(
      <ErrorBoundary><Thrower /></ErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('test explosion')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it('recovers when Try Again is clicked', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    shouldThrow = true;

    render(
      <ErrorBoundary><Thrower /></ErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(screen.getByText('child content')).toBeInTheDocument();

    vi.restoreAllMocks();
  });
});
