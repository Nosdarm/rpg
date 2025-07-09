import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import CircularProgress from '@mui/material/CircularProgress';
import Box from '@mui/material/Box';

// Предполагается, что эти компоненты будут созданы позже
const MainLayout = lazy(() => import('../components/layout/MainLayout'));
const ProtectedRoute = lazy(() => import('../routes/ProtectedRoute'));
const LoginPage = lazy(() => import('../pages/LoginPage'));
const AuthCallbackPage = lazy(() => import('../pages/AuthCallbackPage'));
const GuildSelectionPage = lazy(() => import('../pages/GuildSelectionPage'));
const DashboardPage = lazy(() => import('../pages/DashboardPage'));
const PlayersPage = lazy(() => import('../features/players/PlayersPage'));
const NpcsPage = lazy(() => import('../features/npcs/NpcsPage'));
// const PlayerFormPage = lazy(() => import('../features/players/PlayerFormPage'));
// const NpcFormPage = lazy(() => import('../features/npcs/NpcFormPage'));


const SuspenseFallback: React.FC = () => (
  <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 'calc(100vh - 64px)', mt: '64px' }}> {/* 64px - высота Navbar */}
    <CircularProgress />
  </Box>
);

export const AppRouter: React.FC = () => {
  return (
    <Suspense fallback={<SuspenseFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/discord/callback" element={<AuthCallbackPage />} />

        <Route
          path="/select-guild"
          element={
            <ProtectedRoute requireGuildSelected={false}>
              <GuildSelectionPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/guild/:guildId"
          element={
            <ProtectedRoute requireGuildSelected={true}>
              <MainLayout>
                {/* Вложенный Suspense для страниц внутри MainLayout */}
                <Suspense fallback={<CircularProgress sx={{ margin: 'auto', display: 'block', mt: 4 }} />}>
                  <Routes>
                    <Route path="dashboard" element={<DashboardPage />} />
                    <Route path="players" element={<PlayersPage />} />
                    {/* <Route path="players/new" element={<PlayerFormPage mode="create" />} /> */}
                    {/* <Route path="players/:playerId/edit" element={<PlayerFormPage mode="edit" />} /> */}
                    <Route path="npcs" element={<NpcsPage />} />
                    {/* <Route path="npcs/new" element={<NpcFormPage mode="create" />} /> */}
                    {/* <Route path="npcs/:npcIdentifier/edit" element={<NpcFormPage mode="edit" />} /> */}

                    {/* TODO: Добавить маршруты для других разделов */}

                    <Route index element={<Navigate to="dashboard" replace />} />
                    <Route path="*" element={<div>Раздел не найден в гильдии</div>} />
                  </Routes>
                </Suspense>
              </MainLayout>
            </ProtectedRoute>
          }
        />

        <Route path="/" element={<Navigate to="/login" replace />} /> {/* Редирект с корня на логин по умолчанию */}
        <Route path="*" element={<div>Страница не найдена (404)</div>} /> {/* Глобальный 404 */}
      </Routes>
    </Suspense>
  );
};
