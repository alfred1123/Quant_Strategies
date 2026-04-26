import { useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, CircularProgress,
  Stack, TextField, Typography,
} from '@mui/material';
import { useLogin } from '../api/auth';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const login = useLogin();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    login.mutate(
      { username: username.trim(), password },
      {
        onError: err => {
          // The axios interceptor already extracted the FastAPI `detail`.
          // For 429 (rate-limited) we show a friendlier message.
          const msg = err instanceof Error ? err.message : String(err);
          if (msg.toLowerCase().includes('rate limit')) {
            setErrorMsg('Too many login attempts. Try again in a few minutes.');
          } else {
            setErrorMsg('Invalid username or password.');
          }
        },
      },
    );
  };

  const isPending = login.isPending;

  return (
    <Box
      sx={{
        minHeight: '100vh',
        bgcolor: 'background.default',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 2,
      }}
    >
      <Card sx={{ width: '100%', maxWidth: 400 }} variant="outlined">
        <CardContent>
          <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
            Quant Strategies
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Sign in to continue
          </Typography>

          <form onSubmit={handleSubmit}>
            <Stack spacing={2}>
              <TextField
                label="Username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
                fullWidth
                disabled={isPending}
              />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                fullWidth
                disabled={isPending}
              />
              {errorMsg && <Alert severity="error">{errorMsg}</Alert>}
              <Button
                type="submit"
                variant="contained"
                size="large"
                fullWidth
                disabled={isPending || !username || !password}
                startIcon={isPending ? <CircularProgress size={18} color="inherit" /> : null}
              >
                {isPending ? 'Signing in…' : 'Sign in'}
              </Button>
              <Typography variant="caption" color="text.secondary" sx={{ textAlign: 'center' }}>
                Forgot password? Contact your administrator.
              </Typography>
            </Stack>
          </form>
        </CardContent>
      </Card>
    </Box>
  );
}
