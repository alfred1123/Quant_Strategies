import { useState } from 'react';
import {
  Avatar, IconButton, Menu, MenuItem,
  ListItemText, Divider,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useLogout, type CurrentUser } from '../api/auth';

interface UserMenuProps {
  user: CurrentUser;
}

/** Avatar button + dropdown for the top-right of the AppBar. */
export default function UserMenu({ user }: UserMenuProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const logout = useLogout();
  const navigate = useNavigate();
  const open = Boolean(anchorEl);

  const initial = (user.username[0] ?? '?').toUpperCase();

  return (
    <>
      <IconButton
        onClick={e => setAnchorEl(e.currentTarget)}
        size="small"
        sx={{ ml: 1 }}
        aria-label="user menu"
      >
        <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: 14 }}>
          {initial}
        </Avatar>
      </IconButton>
      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { minWidth: 200 } } }}
      >
        <MenuItem disabled sx={{ opacity: '1 !important' }}>
          <ListItemText
            primary={user.username}
            secondary="Signed in"
            slotProps={{ primary: { sx: { fontWeight: 600 } } }}
          />
        </MenuItem>
        <Divider />
        <MenuItem
          onClick={() => {
            setAnchorEl(null);
            logout.mutate(undefined, {
              onSettled: () => navigate('/login', { replace: true }),
            });
          }}
          disabled={logout.isPending}
        >
          <ListItemText primary={logout.isPending ? 'Signing out…' : 'Sign out'} />
        </MenuItem>
      </Menu>
    </>
  );
}
