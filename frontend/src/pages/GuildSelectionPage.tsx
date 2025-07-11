import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore, GuildInfo } from '../app/stores/authStore';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import ListItemAvatar from '@mui/material/ListItemAvatar';
import Avatar from '@mui/material/Avatar';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Box from '@mui/material/Box';

const GuildSelectionPage: React.FC = () => {
  const navigate = useNavigate();
  const {
    availableGuilds,
    selectGuild,
    isAuthenticated,
    status,
    error,
    logout,
    selectedGuildId, // Добавлено для проверки, не выбрана ли уже гильдия
  } = useAuthStore();

  useEffect(() => {
    if (!isAuthenticated && status !== 'loading') {
      navigate('/login', { replace: true });
    }
    // Если гильдия уже выбрана (например, пользователь нажал "назад" в браузере),
    // и мы оказались на этой странице, перенаправляем на дашборд.
    else if (isAuthenticated && selectedGuildId) {
        navigate(`/guild/${selectedGuildId}/dashboard`, { replace: true });
    }
    // Если аутентифицирован, гильдия не выбрана, но доступна только одна гильдия,
    // store.login должен был ее выбрать автоматически. Если этого не произошло,
    // или логика изменилась, можно добавить авто-выбор здесь.
    // Однако, `authStore.login` уже имеет эту логику.
  }, [isAuthenticated, status, navigate, selectedGuildId]);

  const handleGuildSelect = (guildId: string) => {
    selectGuild(guildId);
    navigate(`/guild/${guildId}/dashboard`, { replace: true });
  };

  const handleLogout = () => {
    logout();
    // navigate('/login', { replace: true }); // logout в authStore должен сбросить isAuthenticated, что вызовет редирект из ProtectedRoute или этого useEffect
  };

  if (status === 'loading' && !isAuthenticated) { // Показываем лоадер только если еще не было попытки восстановить сессию
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  // Если пользователь аутентифицирован, но нет доступных гильдий
  if (isAuthenticated && availableGuilds.length === 0 && status !== 'loading') {
    return (
      <Container component="main" maxWidth="sm" sx={{ textAlign: 'center', mt: 8 }}>
        <Typography variant="h5" component="h1" gutterBottom>
          Нет доступных гильдий
        </Typography>
        <Alert severity="warning" sx={{ mb: 2 }}>
          У вас нет гильдий, где вы являетесь Мастером и бот активен.
          Убедитесь, что бот добавлен на нужный сервер и у вас есть права администратора, либо обратитесь к документации.
        </Alert>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Button variant="contained" onClick={handleLogout} color="primary">
          Выйти
        </Button>
      </Container>
    );
  }

  // Если есть гильдии для выбора
  if (isAuthenticated && availableGuilds.length > 0 && status !== 'loading') {
    return (
      <Container component="main" maxWidth="sm" sx={{ mt: 8 }}>
        <Typography variant="h4" component="h1" gutterBottom textAlign="center">
          Выберите гильдию для управления
        </Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <List sx={{ width: '100%', bgcolor: 'background.paper' }}>
          {availableGuilds.map((guild: GuildInfo) => (
            <ListItem key={guild.id} disablePadding>
              <ListItemButton onClick={() => handleGuildSelect(guild.id)}>
                {guild.icon_url ? (
                  <ListItemAvatar>
                    <Avatar alt={guild.name} src={guild.icon_url} />
                  </ListItemAvatar>
                ) : (
                  <ListItemAvatar>
                    <Avatar>{guild.name.substring(0,1)}</Avatar> {/* Первая буква имени, если нет иконки */}
                  </ListItemAvatar>
                )}
                <ListItemText primary={guild.name} secondary={`ID: ${guild.id}`} />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
        <Box sx={{ textAlign: 'center', mt: 3 }}>
            <Button variant="outlined" onClick={handleLogout}>
                Выйти
            </Button>
        </Box>
      </Container>
    );
  }

  // Если не аутентифицирован и не загрузка - будет редирект из useEffect
  // или если какой-то другой непредвиденный статус
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Typography>Перенаправление...</Typography>
        {/* Можно добавить лоадер на случай если useEffect не успел сработать */}
    </Box>
  );
};

export default GuildSelectionPage;
