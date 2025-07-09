import React from 'react';
import { NavLink, useParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Toolbar from '@mui/material/Toolbar';
import Divider from '@mui/material/Divider';

// Иконки для меню (примеры, добавьте нужные)
import DashboardIcon from '@mui/icons-material/Dashboard';
import PeopleIcon from '@mui/icons-material/People';
import FaceIcon from '@mui/icons-material/Face'; // Для NPC
import CategoryIcon from '@mui/icons-material/Category'; // Для Предметов
import AssignmentIcon from '@mui/icons-material/Assignment'; // Для Квестов
import MapIcon from '@mui/icons-material/Map'; // Для Локаций
import SecurityIcon from '@mui/icons-material/Security'; // Для Фракций
import SettingsIcon from '@mui/icons-material/Settings'; // Для Правил
import BarChartIcon from '@mui/icons-material/BarChart'; // Для Мониторинга
import BuildIcon from '@mui/icons-material/Build'; // Для Инструментов
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'; // Для Списка команд

interface SidebarProps {
  drawerWidth: number;
  mobileOpen: boolean;
  onDrawerToggle: () => void;
}

interface NavItem {
  text: string;
  pathSuffix: string; // Путь относительно /guild/:guildId/
  icon: React.ReactElement;
  disabled?: boolean; // Для будущих разделов
}

export const Sidebar: React.FC<SidebarProps> = ({ drawerWidth, mobileOpen, onDrawerToggle }) => {
  const { guildId } = useParams<{ guildId: string }>();

  const navItems: NavItem[] = [
    { text: 'Дашборд', pathSuffix: 'dashboard', icon: <DashboardIcon /> },
    { text: 'Игроки', pathSuffix: 'players', icon: <PeopleIcon /> },
    { text: 'NPC', pathSuffix: 'npcs', icon: <FaceIcon /> },
    { text: 'Предметы', pathSuffix: 'items', icon: <CategoryIcon />, disabled: true },
    { text: 'Квесты', pathSuffix: 'quests', icon: <AssignmentIcon />, disabled: true },
    { text: 'Локации', pathSuffix: 'locations', icon: <MapIcon />, disabled: true },
    { text: 'Фракции', pathSuffix: 'factions', icon: <SecurityIcon />, disabled: true },
    { text: 'Правила', pathSuffix: 'rules', icon: <SettingsIcon />, disabled: true },
    { text: 'Мониторинг', pathSuffix: 'monitoring', icon: <BarChartIcon />, disabled: true },
    { text: 'Инструменты', pathSuffix: 'tools', icon: <BuildIcon />, disabled: true },
    { text: 'Команды Бота', pathSuffix: 'bot-commands', icon: <HelpOutlineIcon />, disabled: true },
  ];

  const drawerContent = (
    <Box>
      <Toolbar /> {/* Отступ, чтобы контент был под AppBar */}
      <Divider />
      <List>
        {navItems.map((item) => (
          <ListItem key={item.text} disablePadding sx={item.disabled ? { opacity: 0.5 } : {}}>
            <ListItemButton
              component={item.disabled ? 'div' : NavLink}
              to={guildId ? `/guild/${guildId}/${item.pathSuffix}` : '#'}
              onClick={mobileOpen && !item.disabled ? onDrawerToggle : undefined}
              disabled={!guildId || item.disabled}
              sx={{
                '&.active': {
                  backgroundColor: 'action.selected',
                  fontWeight: 'fontWeightBold',
                }
              }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Box>
  );

  return (
    <Box
      component="nav"
      sx={{ width: { sm: drawerWidth }, flexShrink: { sm: 0 } }}
      aria-label="main navigation"
    >
      {/* Мобильный Drawer */}
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={onDrawerToggle}
        ModalProps={{
          keepMounted: true, // Better open performance on mobile.
        }}
        sx={{
          display: { xs: 'block', sm: 'none' },
          '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
        }}
      >
        {drawerContent}
      </Drawer>
      {/* Десктопный Drawer */}
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', sm: 'block' },
          '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth, position: 'relative' },
        }}
        open
      >
        {drawerContent}
      </Drawer>
    </Box>
  );
};

export default Sidebar;
