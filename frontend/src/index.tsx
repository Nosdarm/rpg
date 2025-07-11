import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { ThemeProvider, createTheme } from '@mui/material/styles'; // Для MUI темы
import CssBaseline from '@mui/material/CssBaseline'; // Для MUI нормализации

import App from './app/App';
import './lib/i18n'; // Инициализация i18next
import './styles/global.css'; // Глобальные стили

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 минут
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Пример базовой темы MUI (можно будет вынести и расширить)
const theme = createTheme({
  palette: {
    // mode: 'light', // или 'dark'
    primary: {
      main: '#1976d2', // Пример основного цвета
    },
    secondary: {
      main: '#dc004e', // Пример вторичного цвета
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline /> {/* Сбрасывает стили браузера и применяет базовые от MUI */}
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ThemeProvider>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  </React.StrictMode>
);
