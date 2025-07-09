import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import apiClient from '../../lib/apiClient'; // Предполагаемый путь к вашему apiClient

// Типы данных (можно вынести в src/types/auth.ts или аналогичный)
export interface User {
  id: string; // ID пользователя в вашей БД
  discordId: string;
  username: string;
  avatarUrl?: string;
}

export interface GuildInfo {
  id: string;
  name: string;
  icon_url?: string;
}

export interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  accessToken: string | null; // Сессионный токен от вашего бэкенда
  selectedGuildId: string | null;
  availableGuilds: GuildInfo[];
  status: 'idle' | 'loading' | 'error' | 'success'; // Статус процесса аутентификации/загрузки
  error: string | null; // Сообщение об ошибке

  // Actions
  login: (token: string, userData: User, guilds: GuildInfo[]) => void;
  logout: () => void;
  selectGuild: (guildId: string) => void;
  startLoading: () => void;
  setSuccess: () => void;
  setError: (errorMessage: string) => void;
  clearError: () => void;
  initializeAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      isAuthenticated: false,
      user: null,
      accessToken: null,
      selectedGuildId: null,
      availableGuilds: [],
      status: 'idle',
      error: null,

      login: (token, userData, guilds) => {
        set({
          isAuthenticated: true,
          accessToken: token,
          user: userData,
          availableGuilds: guilds,
          status: 'success',
          error: null,
          // selectedGuildId: guilds.length === 1 ? guilds[0].id : null, // Автовыбор, если одна гильдия
        });

        if (guilds.length === 1) {
          get().selectGuild(guilds[0].id);
        } else if (guilds.length === 0) {
          set({ error: "Нет доступных гильдий для управления." });
        } else {
          // Если гильдий много, сбрасываем selectedGuildId, чтобы пользователь выбрал
          set({ selectedGuildId: null });
        }
      },

      logout: () => {
        // Опционально: уведомить бэкенд об инвалидации сессии
        // apiClient.post('/auth/logout').catch(err => console.error("Logout API call failed", err));
        set({
          isAuthenticated: false,
          user: null,
          accessToken: null,
          selectedGuildId: null,
          // availableGuilds: [], // Не очищаем, чтобы при быстром релогине не запрашивать снова, если не нужно
          status: 'idle',
          error: null,
        });
      },

      selectGuild: (guildId) => {
        set({ selectedGuildId: guildId, status: 'success', error: null });
      },

      startLoading: () => set({ status: 'loading', error: null }),
      setSuccess: () => set({ status: 'success', error: null }),
      setError: (errorMessage) => set({ status: 'error', error: errorMessage, isAuthenticated: false /* Важно при ошибке сессии */ }),
      clearError: () => set({ error: null }),

      initializeAuth: async () => {
        const token = get().accessToken;
        const wasAuthenticated = get().isAuthenticated; // Проверяем, были ли мы аутентифицированы из localStorage

        if (token && wasAuthenticated) { // Только если был токен и мы считали себя аутентифицированными
          get().startLoading();
          try {
            // Реальный вызов к /api/auth/session/me для валидации токена и получения актуальных данных
            const response = await apiClient.get<{ user: User; available_guilds: GuildInfo[] }>('/auth/session/me');
            // Используем login для обновления всех данных, включая токен (может быть обновлен бэкендом)
            // и списка гильдий
            get().login(token, response.data.user, response.data.available_guilds);

            // Если selectedGuildId был в localStorage и он валиден (есть в новом списке available_guilds),
            // то он сохранится. Иначе, если гильдий > 1, он сбросится в login.
            const currentSelectedGuildId = get().selectedGuildId;
            if (currentSelectedGuildId && !response.data.available_guilds.find(g => g.id === currentSelectedGuildId)) {
                set({ selectedGuildId: null }); // Сбросить, если ранее выбранная гильдия теперь недоступна
            }

          } catch (error: any) {
            console.error("Session validation failed on initializeAuth:", error);
            get().logout();
            get().setError(error.response?.data?.message || "Сессия недействительна или истекла.");
          }
        } else if (token && !wasAuthenticated) {
            // Есть токен в localStorage, но состояние isAuthenticated было false. Это странно.
            // Возможно, стоит попробовать валидировать или просто очистить. Для безопасности очистим.
            console.warn("Token found in localStorage but isAuthenticated was false. Clearing auth state.");
            get().logout();
        }
         else {
          set({ status: 'idle' });
        }
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        user: state.user,
        selectedGuildId: state.selectedGuildId,
        availableGuilds: state.availableGuilds,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => {
        // Этот коллбэк вызывается после того, как состояние было восстановлено из localStorage.
        // Мы можем здесь инициировать проверку сессии.
        return (state, error) => {
          if (error) {
            console.error("Failed to rehydrate auth state from localStorage", error);
            state?.logout(); // Если ошибка гидратации, лучше разлогинить
          } else {
            // Состояние успешно восстановлено. initializeAuth будет вызван в App.tsx useEffect.
            // Либо можно вызвать здесь, но нужно быть осторожным с первоначальным рендером.
            // useAuthStore.getState().initializeAuth(); // Вызывать здесь может быть преждевременно
          }
        }
      }
    }
  )
);

// Вызываем initializeAuth один раз при загрузке модуля, чтобы попытаться восстановить сессию
// Это не лучший способ, лучше делать это в корневом компоненте App через useEffect,
// чтобы избежать проблем с SSR или если модуль импортируется несколько раз.
// Убрано отсюда, будет в App.tsx
// if (typeof window !== 'undefined') { // Убедимся, что это клиентская сторона
//   useAuthStore.getState().initializeAuth();
// }
