import React from 'react';
import Typography from '@mui/material/Typography';
import Container from '@mui/material/Container';
import Paper from '@mui/material/Paper';
import Grid from '@mui/material/Grid';
import { useParams } from 'react-router-dom';
import { useAuthStore } from '../app/stores/authStore';

const DashboardPage: React.FC = () => {
  const { guildId } = useParams<{ guildId: string }>();
  const { user, selectedGuildId, availableGuilds } = useAuthStore();

  const currentGuild = availableGuilds.find(g => g.id === (selectedGuildId || guildId));

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" gutterBottom component="h1">
        Дашборд Гильдии: {currentGuild?.name || guildId}
      </Typography>

      <Grid container spacing={3}>
        {/* Пример карточки */}
        <Grid item xs={12} md={4} lg={3}>
          <Paper
            sx={{
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              height: 180, // Пример высоты
            }}
          >
            <Typography component="h2" variant="h6" color="primary" gutterBottom>
              Активных Игроков
            </Typography>
            <Typography component="p" variant="h4">
              {/* TODO: Загрузить и отобразить количество активных игроков */}
              N/A
            </Typography>
            <Typography color="text.secondary" sx={{ flex: 1 }}>
              {/* Дополнительная информация */}
            </Typography>
            <div>
              {/* Ссылка или кнопка */}
            </div>
          </Paper>
        </Grid>

        {/* Пример карточки */}
        <Grid item xs={12} md={4} lg={3}>
          <Paper
            sx={{
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              height: 180,
            }}
          >
            <Typography component="h2" variant="h6" color="primary" gutterBottom>
              Всего NPC
            </Typography>
            <Typography component="p" variant="h4">
              {/* TODO: Загрузить и отобразить количество NPC */}
              N/A
            </Typography>
          </Paper>
        </Grid>

        {/* Пример карточки */}
        <Grid item xs={12} md={4} lg={3}>
          <Paper
            sx={{
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              height: 180,
            }}
          >
            <Typography component="h2" variant="h6" color="primary" gutterBottom>
              Активных Квестов
            </Typography>
            <Typography component="p" variant="h4">
              {/* TODO: Загрузить и отобразить количество активных квестов */}
              N/A
            </Typography>
          </Paper>
        </Grid>

        {/* Можно добавить другие информационные блоки или графики */}
         <Grid item xs={12}>
          <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column' }}>
            <Typography component="h2" variant="h6" color="primary" gutterBottom>
              Быстрые действия
            </Typography>
            {/* TODO: Добавить кнопки для частых действий, например, "Создать NPC", "Просмотреть логи" */}
            <Typography>
              Раздел для быстрых ссылок или кнопок частых операций.
            </Typography>
          </Paper>
        </Grid>
      </Grid>
    </Container>
  );
};

export default DashboardPage;
