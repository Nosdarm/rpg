/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DISCORD_CLIENT_ID: string;
  readonly VITE_DISCORD_REDIRECT_URI: string;
  readonly VITE_API_BASE_URL: string;
  // добавьте сюда другие переменные окружения, которые вы будете использовать
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
