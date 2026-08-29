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
import { NavLink, Outlet, useLocation } from 'react-router';
import UserMenu from '../components/UserMenu';
import AppModeSwitch from '../components/AppModeSwitch';
import BrandMark from '../components/BrandMark';
import { APP_NAME } from '../constants/brand';
import TradeNavBar from '../components/trade/TradeNavBar';
import ExecutionLogPanel from '../components/trade/ExecutionLogPanel';
import { useMe } from '../api/auth';
import { TradeSessionProvider } from '../trade/TradeSessionContext';

const SIDEBAR_WIDTH = 200;

const NAV_ITEMS = [
  { to: '/trade/config', label: 'Config' },
  { to: '/trade/apply', label: 'Trade' },
] as const;

/** Phase 1.4+ — Trade tab shell: sidebar, filters, main content, execution log. */
export default function TradeLayout() {
  const { data: currentUser } = useMe();
  const location = useLocation();

  return (
    <TradeSessionProvider>
      <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', display: 'flex', flexDirection: 'column' }}>
        <AppBar
          position="static"
          elevation={0}
          sx={{ bgcolor: 'background.paper', borderBottom: '1px solid', borderColor: 'divider' }}
        >
          <Toolbar sx={{ gap: 2 }}>
            <BrandMark />
            <Typography variant="h6" color="text.primary" sx={{ fontWeight: 700, mr: 1 }}>
              {APP_NAME}
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
            <Box
              sx={{
                px: 3,
                py: 1.25,
                borderBottom: '1px solid',
                borderColor: 'divider',
                bgcolor: 'background.paper',
              }}
            >
              <TradeNavBar />
            </Box>
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
                maxHeight: 360,
                overflow: 'auto',
                bgcolor: 'background.paper',
                border: '1px solid',
                borderColor: 'divider',
              }}
            >
              <ExecutionLogPanel />
            </Paper>
          </Box>
        </Box>
      </Box>
    </TradeSessionProvider>
  );
}
