import React, { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Button from '@mui/material/Button';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import { useAuthStore } from '../app/stores/authStore';
import { generateCodeVerifier, generatePkceChallenge } from '../lib/pkceUtils'; // Предполагается, что pkceUtils будет создан

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, status, error, selectedGuildId, availableGuilds, startLoading, setError, clearError } = useAuthStore();

  useEffect(() => {
    // Если пользователь уже аутентифицирован, перенаправляем его
    if (isAuthenticated) {
      if (selectedGuildId) {
        navigate(`/guild/${selectedGuildId}/dashboard`, { replace: true });
      } else if (availableGuilds.length > 0) {
        navigate('/select-guild', { replace: true });
      } else {
        // Аутентифицирован, но нет гильдий или выбранной гильдии - это странное состояние,
        // возможно, остаться здесь и показать сообщение или перенаправить на /select-guild, где будет сообщение.
        // Пока оставим так, /select-guild обработает "нет доступных гильдий".
        navigate('/select-guild', { replace: true });
      }
    }
  }, [isAuthenticated, selectedGuildId, availableGuilds, navigate]);

  const handleLogin = async () => {
    startLoading();
    clearError();

    try {
      const verifier = generateCodeVerifier();
      const challenge = await generatePkceChallenge(verifier);

      sessionStorage.setItem('pkce_code_verifier', verifier);
      sessionStorage.setItem('oauth_state', crypto.randomUUID()); // Генерируем state

      const params = new URLSearchParams({
        client_id: import.meta.env.VITE_DISCORD_CLIENT_ID,
        redirect_uri: import.meta.env.VITE_DISCORD_REDIRECT_URI,
        response_type: 'code',
        scope: 'identify guilds', // Запрашиваемые разрешения
        state: sessionStorage.getItem('oauth_state')!,
        code_challenge: challenge,
        code_challenge_method: 'S256',
        prompt: 'consent', // Чтобы всегда показывать окно авторизации Discord
      });

      window.location.href = `https://discord.com/api/oauth2/authorize?${params.toString()}`;
    } catch (e) {
      console.error("Failed to initiate OAuth2 login", e);
      setError("Ошибка при инициации входа. Попробуйте еще раз.");
    }
  };

  // Если есть ошибка из предыдущей попытки входа (например, из AuthCallbackPage)
  const locationState = location.state as { error?: string };
  const oauthError = locationState?.error;


  return (
    <Container component="main" maxWidth="xs">
      <Box
        sx={{
          marginTop: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <Typography component="h1" variant="h5">
          Панель Управления Мастера
        </Typography>
        {(error || oauthError) && (
          <Alert severity="error" sx={{ width: '100%', mt: 2 }}>
            {error || oauthError}
          </Alert>
        )}
        <Button
          type="button"
          fullWidth
          variant="contained"
          sx={{ mt: 3, mb: 2 }}
          onClick={handleLogin}
          disabled={status === 'loading'}
        >
          {status === 'loading' ? <CircularProgress size={24} /> : 'Войти с помощью Discord'}
        </Button>
      </Box>
    </Container>
  );
};

export default LoginPage;
