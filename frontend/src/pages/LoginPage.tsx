import { useState, useEffect } from 'react';
import {
  Alert, Box, Button, Card, CardContent, CircularProgress,
  IconButton, InputAdornment, Stack, TextField, Typography, Chip,
} from '@mui/material';
import VisibilityRoundedIcon from '@mui/icons-material/VisibilityRounded';
import VisibilityOffRoundedIcon from '@mui/icons-material/VisibilityOffRounded';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLogin } from '../api/auth';
import BrandMark from '../components/BrandMark';
import { APP_NAME } from '../constants/brand';

// =====================================================
// NEW: Service status type
// This defines what info we track for each service
// =====================================================
type ServiceStatus = {
  name: string;       // Display name (e.g., "Backend API")
  status: 'checking' | 'online' | 'offline';  // Current state
  url: string;        // URL we're checking
};

/** Health endpoints probed by the login page — fixed list, module scope. */
const SERVICE_ENDPOINTS = [
  { name: 'Backend API', url: '/health' },
  { name: 'Database', url: '/health/ready' },
] as const;

// =====================================================
// NEW: Hook to check if services are running
// This runs when the page loads and checks each service
// =====================================================
function useServiceHealth() {
  const [services, setServices] = useState<ServiceStatus[]>(
    SERVICE_ENDPOINTS.map(s => ({ ...s, status: 'checking' })),
  );

  useEffect(() => {
    // Check each service when component mounts
    const checkServices = async () => {
      const results = await Promise.all(
        SERVICE_ENDPOINTS.map(async (service) => {
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
  }, []); // Endpoints are a module constant — nothing to depend on

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
  const [showPassword, setShowPassword] = useState(false);
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
        backgroundImage: `
          radial-gradient(ellipse 60% 45% at 15% 0%, rgba(77, 142, 240, 0.14), transparent),
          radial-gradient(ellipse 55% 40% at 90% 100%, rgba(52, 201, 142, 0.08), transparent)
        `,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 2,
      }}
    >
      <Card
        variant="outlined"
        sx={{
          width: '100%',
          maxWidth: 400,
          boxShadow: '0 24px 64px rgba(0, 0, 0, 0.45)',
        }}
      >
        <CardContent sx={{ p: 4 }}>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 0.5 }}>
            <BrandMark size={40} />
            <Typography variant="h5" sx={{ fontWeight: 700 }}>
              {APP_NAME}
            </Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
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
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                fullWidth
                disabled={isPending || backendOffline}
                slotProps={{
                  input: {
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          aria-label={showPassword ? 'Hide password' : 'Show password'}
                          onClick={() => setShowPassword(v => !v)}
                          edge="end"
                          size="small"
                        >
                          {showPassword ? <VisibilityOffRoundedIcon fontSize="small" /> : <VisibilityRoundedIcon fontSize="small" />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  },
                }}
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
