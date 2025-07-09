import React from 'react';
import { useNavigate } from 'react-router-dom';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import MenuIcon from '@mui/icons-material/Menu';
import AccountCircle from '@mui/icons-material/AccountCircle';
import MenuItem from '@mui/material/MenuItem';
import Menu from '@mui/material/Menu';
import Button from '@mui/material/Button';
import Box from '@mui/material/Box';
import { useAuthStore } from '../../app/stores/authStore';

interface NavbarProps {
  onDrawerToggle: () => void;
  drawerWidth: number;
}

export const Navbar: React.FC<NavbarProps> = ({ onDrawerToggle, drawerWidth }) => {
  const navigate = useNavigate();
  const { user, logout, selectedGuildId, availableGuilds } = useAuthStore();
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);

  const handleMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = () => {
    logout();
    // Роутер должен автоматически перенаправить на /login из-за ProtectedRoute
    // или можно явно: navigate('/login', { replace: true });
    handleClose();
  };

  const handleChangeGuild = () => {
    useAuthStore.setState({ selectedGuildId: null }); // Сбрасываем выбранную гильдию
    navigate('/select-guild', { replace: true });
    handleClose();
  };

  const currentSelectedGuild = availableGuilds.find(g => g.id === selectedGuildId);

  return (
    <AppBar
      position="fixed"
      sx={{
        width: { sm: `calc(100% - ${drawerWidth}px)` },
        ml: { sm: `${drawerWidth}px` },
        zIndex: (theme) => theme.zIndex.drawer + 1, // Чтобы быть выше Sidebar
      }}
    >
      <Toolbar>
        <IconButton
          color="inherit"
          aria-label="open drawer"
          edge="start"
          onClick={onDrawerToggle}
          sx={{ mr: 2, display: { sm: 'none' } }}
        >
          <MenuIcon />
        </IconButton>
        <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
          Master Panel {currentSelectedGuild ? `| ${currentSelectedGuild.name}` : (selectedGuildId ? `| Guild ID: ${selectedGuildId}`: '')}
        </Typography>
        {user && (
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            {availableGuilds.length > 1 && (
                 <Button color="inherit" onClick={handleChangeGuild} sx={{mr: 1}}>
                    Сменить гильдию
                 </Button>
            )}
            <Typography sx={{ display: { xs: 'none', sm: 'block' }, mr:1 }}>{user.username}</Typography>
            <IconButton
              size="large"
              aria-label="account of current user"
              aria-controls="menu-appbar"
              aria-haspopup="true"
              onClick={handleMenu}
              color="inherit"
            >
              <AccountCircle />
            </IconButton>
            <Menu
              id="menu-appbar"
              anchorEl={anchorEl}
              anchorOrigin={{
                vertical: 'bottom',
                horizontal: 'right',
              }}
              keepMounted
              transformOrigin={{
                vertical: 'top',
                horizontal: 'right',
              }}
              open={Boolean(anchorEl)}
              onClose={handleClose}
            >
              <MenuItem disabled>{user.username}</MenuItem>
              <MenuItem onClick={handleLogout}>Выйти</MenuItem>
            </Menu>
          </Box>
        )}
      </Toolbar>
    </AppBar>
  );
};

export default Navbar;
