import { Box, ButtonBase } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

export type AppMode = 'backtest' | 'trade';

interface AppModeSwitchProps {
  mode: AppMode;
}

const SEGMENTS: { mode: AppMode; to: string; label: string }[] = [
  { mode: 'backtest', to: '/backtest', label: 'Backtest' },
  { mode: 'trade', to: '/trade', label: 'Trade' },
];

/** Segmented app-mode control — Backtest vs Trade. */
export default function AppModeSwitch({ mode }: AppModeSwitchProps) {
  return (
    <Box
      role="group"
      aria-label="Application mode"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        p: '3px',
        gap: '2px',
        borderRadius: '10px',
        bgcolor: 'rgba(255, 255, 255, 0.04)',
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      {SEGMENTS.map(({ mode: segmentMode, to, label }) => {
        const active = mode === segmentMode;
        return (
          <ButtonBase
            key={segmentMode}
            component={RouterLink}
            to={to}
            aria-label={`${label} mode`}
            aria-current={active ? 'page' : undefined}
            sx={{
              px: 2,
              py: 0.625,
              borderRadius: '8px',
              fontSize: '0.8125rem',
              fontWeight: active ? 600 : 500,
              letterSpacing: '0.01em',
              color: active ? 'text.primary' : 'text.secondary',
              bgcolor: active ? 'background.paper' : 'transparent',
              boxShadow: active ? '0 1px 3px rgba(0,0,0,0.35)' : 'none',
              transition: 'background-color 0.15s ease, color 0.15s ease, box-shadow 0.15s ease',
              '&:hover': {
                bgcolor: active ? 'background.paper' : 'rgba(255, 255, 255, 0.06)',
                color: 'text.primary',
              },
            }}
          >
            {label}
          </ButtonBase>
        );
      })}
    </Box>
  );
}
