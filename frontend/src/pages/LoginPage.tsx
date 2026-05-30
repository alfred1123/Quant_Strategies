import { useState, useEffect } from 'react';
import {
  Alert, Box, Button, Card, CardContent, CircularProgress,
  Stack, TextField, Typography, Chip,
} from '@mui/material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLogin } from '../api/auth';

// =====================================================
// NEW: Service status type
// This defines what info we track for each service
// =====================================================
type ServiceStatus = {
  name: string;       // Display name (e.g., "Backend API")
  status: 'checking' | 'online' | 'offline';  // Current state
  url: string;        // URL we're checking
};

// =====================================================
// NEW: Hook to check if services are running
// This runs when the page loads and checks each service
// =====================================================
function useServiceHealth() {
  const [services, setServices] = useState<ServiceStatus[]>([
    { name: 'Backend API', status: 'checking', url: 'http://localhost:8000/health' },
    { name: 'Database', status: 'checking', url: 'http://localhost:8000/health/ready' },
  ]);

  useEffect(() => {
    // Check each service when component mounts
    const checkServices = async () => {
      const results = await Promise.all(
        services.map(async (service) => {
          try {
            // Try to fetch the health endpoint
            const response = await fetch(service.url, {
              method: 'GET',
              signal: AbortSignal.timeout(5000), // 5 second timeout
            });
            return {
              ...service,
              status: response.ok ? 'online' : 'offline',
            } as ServiceStatus;
          } catch {
            // If fetch fails, service is offline
            return { ...service, status: 'offline' } as ServiceStatus;
          }
        })
      );
      setServices(results);
    };

    checkServices();

    // Re-check every 30 seconds
    const interval = setInterval(checkServices, 30000);
    return () => clearInterval(interval);
  }, []); // Empty array = run once on mount

  return services;
}

// =====================================================
// NEW: Component to display a single service status
// Shows a colored chip: green=online, red=offline, gray=checking
// =====================================================
function ServiceStatusChip({ service }: { service: ServiceStatus }) {
  const colorMap = {
    checking: 'default',
    online: 'success',
    offline: 'error',
  } as const;

  const labelMap = {
    checking: 'Checking...',
    online: 'Online',
    offline: 'Offline',
  };

  return (
    <Chip
      label={`${service.name}: ${labelMap[service.status]}`}
      color={colorMap[service.status]}
      size="small"
      variant={service.status === 'offline' ? 'filled' : 'outlined'}
      sx={{
        // Make offline status more noticeable
        fontWeight: service.status === 'offline' ? 700 : 400,
      }}
    />
  );
}

// =====================================================
// NEW: Component to show all service statuses together
// Displays a row of status chips above the login form
// =====================================================
function ServiceStatusPanel({ services }: { services: ServiceStatus[] }) {
  const hasOffline = services.some(s => s.status === 'offline');

  return (
    <Box sx={{ mb: 2 }}>
      {/* Row of status chips */}
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap', mb: 1 }}>
        {services.map((service) => (
          <ServiceStatusChip key={service.name} service={service} />
        ))}
      </Stack>

      {/* Warning message if any service is offline */}
      {hasOffline && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          Some services are offline. Login may not work until they are restored.
        </Alert>
      )}
    </Box>
  );
}

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();

  // =====================================================
  // NEW: Get service status from our custom hook
  // =====================================================
  const services = useServiceHealth();

  const redirectTo = (location.state as { from?: Location })?.from?.pathname ?? '/backtest';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    login.mutate(
      { username: username.trim(), password },
      {
        onSuccess: () => {
          navigate(redirectTo, { replace: true });
        },
        onError: err => {
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

  // =====================================================
  // NEW: Check if backend is offline to disable login
  // No point trying to login if API is down
  // =====================================================
  const backendOffline = services.find(s => s.name === 'Backend API')?.status === 'offline';

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
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Sign in to continue
          </Typography>

          {/* =====================================================
              NEW: Service status panel added here
              Shows status of Backend API and Database
              ===================================================== */}
          <ServiceStatusPanel services={services} />

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
                disabled={isPending || backendOffline}
              />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                fullWidth
                disabled={isPending || backendOffline}
              />
              {errorMsg && <Alert severity="error">{errorMsg}</Alert>}
              <Button
                type="submit"
                variant="contained"
                size="large"
                fullWidth
                disabled={isPending || !username || !password || backendOffline}
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
