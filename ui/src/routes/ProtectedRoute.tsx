import React, { ReactNode } from 'react';
import { Navigate, useLocation, useParams } from 'react-router-dom';
import { useAuthStore } from '../app/stores/authStore';
import CircularProgress from '@mui/material/CircularProgress';
import Box from '@mui/material/Box';

interface ProtectedRouteProps {
  children: ReactNode;
  /**
   * Если true, то для доступа к маршруту должна быть выбрана гильдия.
   * Если false, то достаточно только аутентификации (например, для страницы выбора гильдии).
   */
  requireGuildSelected?: boolean;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requireGuildSelected = true }) => {
  const { isAuthenticated, selectedGuildId, status, availableGuilds } = useAuthStore();
  const location = useLocation(); // Для сохранения пути, с которого пришли
  const params = useParams<{guildId?: string}>(); // Для проверки guildId в URL, если он там есть

  // Показываем лоадер, если идет первоначальная проверка сессии и пользователь еще не аутентифицирован
  // Это помогает избежать мигания страницы логина, если сессия валидна
  if (status === 'loading' && !isAuthenticated && !useAuthStore.getState().accessToken) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!isAuthenticated) {
    // Пользователь не аутентифицирован, перенаправляем на страницу логина
    // Сохраняем `location.state.from` чтобы вернуться сюда после логина
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Пользователь аутентифицирован, проверяем необходимость выбора гильдии
  const guildIdForCheck = selectedGuildId || params.guildId;

  if (requireGuildSelected && !guildIdForCheck) {
    // Гильдия должна быть выбрана, но это не так.
    // Если есть доступные гильдии, перенаправляем на страницу выбора.
    if (availableGuilds && availableGuilds.length > 0) {
      return <Navigate to="/select-guild" state={{ from: location }} replace />;
    }
    // Если доступных гильдий нет (например, ошибка или пользователь не Мастер нигде)
    // Страница /select-guild должна будет это обработать и показать сообщение.
    // Либо можно здесь показать сообщение об ошибке или перенаправить на спец. страницу.
    // Пока что перенаправляем на /select-guild, он покажет сообщение.
    return <Navigate to="/select-guild" state={{ from: location }} replace />;
  }

  // Если маршрут требует guildId в URL (например, /guild/:guildId/...)
  // и он не совпадает с выбранной в сторе гильдией, это может быть проблемой.
  // Можно добавить логику для синхронизации или редиректа.
  // Например, если params.guildId есть, но не равен selectedGuildId,
  // возможно, стоит перенаправить на /guild/{selectedGuildId}/... или на /select-guild.
  // Для простоты пока предполагаем, что навигация через Sidebar и другие ссылки будет корректной.
  if (params.guildId && selectedGuildId && params.guildId !== selectedGuildId) {
    // Пример: если пользователь вручную ввел другой guildId в URL
    console.warn(`Mismatch between URL guildId (${params.guildId}) and selectedGuildId (${selectedGuildId}). Redirecting...`);
    return <Navigate to={`/guild/${selectedGuildId}/${location.pathname.split('/').pop() || 'dashboard'}`} replace />;
  }


  return <>{children}</>; // Если все проверки пройдены, отображаем дочерний компонент
};

export default ProtectedRoute;
