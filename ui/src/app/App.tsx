import React, { useEffect, Suspense } from 'react';
import { AppRouter } from './router';
import { useAuthStore } from './stores/authStore';
import CircularProgress from '@mui/material/CircularProgress';
import Box from '@mui/material/Box';

// Глобальный лоадер для первоначальной загрузки сессии
const GlobalLoader: React.FC = () => (
  <Box
    sx={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      height: '100vh',
      width: '100vw',
      position: 'fixed',
      top: 0,
      left: 0,
      backgroundColor: 'rgba(255, 255, 255, 0.8)', // Полупрозрачный фон
      zIndex: 9999
    }}
  >
    <CircularProgress />
  </Box>
);

function App() {
  const initializeAuth = useAuthStore((state) => state.initializeAuth);
  const authStatus = useAuthStore((state) => state.status);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  // Показываем глобальный лоадер только при первоначальной проверке сессии,
  // если пользователь еще не был аутентифицирован (например, из localStorage)
  const showGlobalLoader = authStatus === 'loading' && !isAuthenticated && !useAuthStore.getState().accessToken;


  return (
    <>
      {showGlobalLoader && <GlobalLoader />}
      <Suspense fallback={<GlobalLoader />}> {/* Fallback для AppRouter, если он сам lazy */}
        <AppRouter />
      </Suspense>
    </>
  );
}

export default App;
