import {
  AppBar,
  Box,
  Drawer,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Toolbar,
  Typography,
} from '@mui/material';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import UserMenu from '../components/UserMenu';
import AppModeSwitch from '../components/AppModeSwitch';
import { useMe } from '../api/auth';

const SIDEBAR_WIDTH = 200;

const NAV_ITEMS = [
  { to: '/trade/config', label: 'Config' },
  { to: '/trade/apply', label: 'Trade' },
] as const;

/** Phase 1.4 — Trade tab shell: sidebar, main content, execution log placeholder. */
export default function TradeLayout() {
  const { data: currentUser } = useMe();
  const location = useLocation();

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', display: 'flex', flexDirection: 'column' }}>
      <AppBar
        position="static"
        elevation={0}
        sx={{ bgcolor: 'background.paper', borderBottom: '1px solid', borderColor: 'divider' }}
      >
        <Toolbar sx={{ gap: 2 }}>
          <Typography variant="h6" color="text.primary" sx={{ fontWeight: 700, mr: 1 }}>
            Quant Strategies
          </Typography>
          <AppModeSwitch mode="trade" />
          <Box sx={{ flexGrow: 1 }} />
          {currentUser && <UserMenu user={currentUser} />}
        </Toolbar>
      </AppBar>

      <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <Drawer
          variant="permanent"
          sx={{
            width: SIDEBAR_WIDTH,
            flexShrink: 0,
            '& .MuiDrawer-paper': {
              width: SIDEBAR_WIDTH,
              boxSizing: 'border-box',
              position: 'relative',
              bgcolor: 'background.paper',
              borderRight: '1px solid',
              borderColor: 'divider',
            },
          }}
        >
          <List component="nav" aria-label="Trade sections">
            {NAV_ITEMS.map(({ to, label }) => (
              <ListItemButton
                key={to}
                component={NavLink}
                to={to}
                selected={location.pathname === to}
              >
                <ListItemText primary={label} />
              </ListItemButton>
            ))}
          </List>
        </Drawer>

        <Box
          component="main"
          sx={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            minHeight: 0,
          }}
        >
          <Box sx={{ flex: 1, p: 3, overflow: 'auto' }}>
            <Outlet />
          </Box>
          <Paper
            elevation={0}
            sx={{
              m: 2,
              mt: 0,
              p: 2,
              minHeight: 120,
              bgcolor: 'background.paper',
              border: '1px solid',
              borderColor: 'divider',
            }}
          >
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              Execution log
            </Typography>
            <Typography variant="body2" color="text.disabled">
              Recent orders and fills will appear here (Phase 1.8).
            </Typography>
          </Paper>
        </Box>
      </Box>
    </Box>
  );
}
