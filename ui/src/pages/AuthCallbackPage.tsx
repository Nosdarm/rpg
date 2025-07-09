import React, { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '../app/stores/authStore';
import apiClient from '../lib/apiClient'; // Наш настроенный Axios клиент
import CircularProgress from '@mui/material/CircularProgress';
import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Typography from '@mui/material/Typography';

const AuthCallbackPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { login, setError, startLoading, status, availableGuilds, selectedGuildId } = useAuthStore();

  // Используем useRef, чтобы избежать повторного вызова API при ре-рендерах в StrictMode
  const processingRef = useRef(false);

  useEffect(() => {
    if (processingRef.current) {
      return;
    }
    processingRef.current = true;

    const code = searchParams.get('code');
    const receivedState = searchParams.get('state');
    const errorParam = searchParams.get('error');
    const errorDescription = searchParams.get('error_description');

    const storedState = sessionStorage.getItem('oauth_state');
    const codeVerifier = sessionStorage.getItem('pkce_code_verifier');

    // Очищаем временные данные из sessionStorage
    sessionStorage.removeItem('oauth_state');
    sessionStorage.removeItem('pkce_code_verifier');

    if (errorParam) {
      setError(`Ошибка авторизации Discord: ${errorDescription || errorParam}`);
      navigate('/login', { replace: true, state: { error: `Ошибка авторизации Discord: ${errorDescription || errorParam}` } });
      return;
    }

    if (!code) {
      setError("Код авторизации не получен от Discord.");
      navigate('/login', { replace: true, state: { error: "Код авторизации не получен от Discord." } });
      return;
    }

    if (!storedState || storedState !== receivedState) {
      setError("Ошибка безопасности: неверный параметр state. Попробуйте войти снова.");
      navigate('/login', { replace: true, state: { error: "Ошибка безопасности: неверный параметр state." } });
      return;
    }

    if (!codeVerifier) {
      setError("Ошибка PKCE: code_verifier не найден. Попробуйте войти снова.");
      navigate('/login', { replace: true, state: { error: "Ошибка PKCE: code_verifier не найден." } });
      return;
    }

    startLoading();

    apiClient.post('/auth/discord/finalize', { // Предполагаемый эндпоинт бэкенда
      code,
      code_verifier: codeVerifier,
      redirect_uri: import.meta.env.VITE_DISCORD_REDIRECT_URI,
    })
    .then(response => {
      const { session_token, user, available_guilds } = response.data;
      login(session_token, user, available_guilds);

      // Логика редиректа после успешного логина
      if (available_guilds.length === 1) {
        // selectGuild будет вызван внутри login, если гильдия одна
        navigate(`/guild/${available_guilds[0].id}/dashboard`, { replace: true });
      } else if (available_guilds.length > 1) {
        navigate('/select-guild', { replace: true });
      } else {
        // Нет доступных гильдий
        navigate('/select-guild', { replace: true }); // Страница выбора гильдии покажет сообщение
      }
    })
    .catch(err => {
      console.error("Ошибка при обмене кода на токен:", err);
      const errorMessage = err.response?.data?.message || err.response?.data?.error_description || err.message || "Не удалось завершить аутентификацию.";
      setError(errorMessage);
      navigate('/login', { replace: true, state: { error: errorMessage } });
    });

  }, [searchParams, navigate, login, setError, startLoading]);


  if (status === 'loading') {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
        <Typography sx={{ mt: 2 }}>Завершение аутентификации...</Typography>
      </Box>
    );
  }

  // Если произошла ошибка до начала загрузки или после, она будет в сторе,
  // и LoginPage должен ее отобразить после редиректа.
  // Этот компонент в основном для обработки и редиректа.
  return null;
};

export default AuthCallbackPage;
