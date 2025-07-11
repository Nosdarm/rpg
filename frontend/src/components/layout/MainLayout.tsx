import React, { ReactNode, useState, Suspense } from 'react';
import Box from '@mui/material/Box';
import CssBaseline from '@mui/material/CssBaseline';
import CircularProgress from '@mui/material/CircularProgress';
import { Navbar } from './Navbar';
import { Sidebar } from './Sidebar';
import Toolbar from '@mui/material/Toolbar'; // Для отступа под AppBar

const drawerWidth = 240; // Ширина Sidebar, можно вынести в константы темы

interface MainLayoutProps {
  children: ReactNode;
}

const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <CssBaseline />
      <Navbar onDrawerToggle={handleDrawerToggle} drawerWidth={drawerWidth} />
      <Sidebar
        drawerWidth={drawerWidth}
        mobileOpen={mobileOpen}
        onDrawerToggle={handleDrawerToggle}
      />
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          // mt: '64px', // Отступ для AppBar теперь обрабатывается через Toolbar в Navbar/Sidebar
          display: 'flex',
          flexDirection: 'column'
        }}
      >
        <Toolbar /> {/* Этот Toolbar обеспечивает отступ для контента под фиксированным AppBar */}
        <Suspense fallback={
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', flexGrow: 1 }}>
            <CircularProgress />
          </Box>
        }>
          {children}
        </Suspense>
      </Box>
    </Box>
  );
};

export default MainLayout;
