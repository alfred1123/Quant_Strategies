import { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, createTheme } from '@mui/material';
import { MemoryRouter } from 'react-router-dom';
import { render, type RenderOptions } from '@testing-library/react';

const theme = createTheme({ palette: { mode: 'dark' } });

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

interface WrapperOptions {
  initialEntries?: string[];
}

export function renderWithProviders(
  ui: ReactNode,
  options?: Omit<RenderOptions, 'wrapper'> & WrapperOptions,
) {
  const { initialEntries = ['/'], ...renderOpts } = options ?? {};
  const qc = createTestQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={initialEntries}>
        <QueryClientProvider client={qc}>
          <ThemeProvider theme={theme}>{children}</ThemeProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );
  }
  return { ...render(ui, { wrapper: Wrapper, ...renderOpts }), queryClient: qc };
}
