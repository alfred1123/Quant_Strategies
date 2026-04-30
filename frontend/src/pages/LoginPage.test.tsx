import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import LoginPage from './LoginPage';
import { renderWithProviders } from '../test/wrapper';

vi.mock('../api/auth', async () => {
  const { useMutation } = await import('@tanstack/react-query');
  return {
    ME_QUERY_KEY: ['auth', 'me'],
    useLogin: () => useMutation({
      mutationFn: vi.fn(),
    }),
    useMe: () => ({ data: null, isLoading: false }),
    useLogout: () => useMutation({ mutationFn: vi.fn() }),
  };
});

beforeEach(() => vi.clearAllMocks());

describe('LoginPage', () => {
  it('renders the sign-in form', () => {
    renderWithProviders(<LoginPage />);
    expect(screen.getByText('Quant Strategies')).toBeInTheDocument();
    expect(screen.getByText('Sign in to continue')).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it('disables submit when fields are empty', () => {
    renderWithProviders(<LoginPage />);
    const btn = screen.getByRole('button', { name: /sign in/i });
    expect(btn).toBeDisabled();
  });

  it('enables submit when both fields have values', () => {
    renderWithProviders(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'password123!' } });
    const btn = screen.getByRole('button', { name: /sign in/i });
    expect(btn).not.toBeDisabled();
  });

  it('shows admin contact message', () => {
    renderWithProviders(<LoginPage />);
    expect(screen.getByText(/contact your administrator/i)).toBeInTheDocument();
  });
});
