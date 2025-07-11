// src/ui/src/services/commandListService.ts
import { UICommandListResponse, UICommandInfo, UICommandParameterInfo } from '../types/commands';

// Моковый API клиент, если он будет использоваться для реальных вызовов.
// import apiClient from './apiClient';

const mockCommandParams: UICommandParameterInfo[] = [
  { name: 'user', type: 'User', description: 'The user to target.', required: true },
  { name: 'reason', type: 'String', description: 'The reason for this action.', required: false },
];

const mockCommands: UICommandInfo[] = [
  {
    name: 'ping',
    description: 'Checks the bot\'s latency.',
    parameters: [],
  },
  {
    name: 'help',
    description: 'Displays a list of commands or help for a specific command.',
    parameters: [
      { name: 'command_name', type: 'String', description: 'The command to get help for.', required: false }
    ],
  },
  {
    name: 'party create',
    description: 'Creates a new party.',
    parameters: [
      { name: 'name', type: 'String', description: 'The name of the party.', required: true }
    ],
  },
  {
    name: 'master_player view',
    description: 'View details of a specific player.',
    parameters: [
      { name: 'player_id', type: 'Integer', description: 'The database ID of the player.', required: true },
      { name: 'include_inventory', type: 'Boolean', description: 'Whether to include inventory details.', required: false }
    ]
  },
  {
    name: 'ban', // Пример команды с несколькими параметрами
    description: 'Bans a user from the server.',
    parameters: mockCommandParams,
  },
];

/**
 * Fetches the list of bot commands.
 * Currently returns mock data.
 * TODO: Implement actual API call to GET /api/v1/command-list/
 * @param language - Optional language code for localization.
 */
export const fetchCommandList = async (language?: string): Promise<UICommandListResponse> => {
  console.log(`Fetching command list for language: ${language || 'default'}`);

  // Имитация задержки API
  await new Promise(resolve => setTimeout(resolve, 500));

  // В реальном сценарии:
  // try {
  //   const params = language ? { language } : {};
  //   // Предполагается, что apiClient настроен для базового URL API, например, http://localhost:8000
  //   // и путь здесь будет /api/v1/command-list/
  //   // const response = await apiClient.get<UICommandListResponse>('/api/v1/command-list/', { params });
  //   // return response.data;
  // } catch (error) {
  //   console.error('Error fetching command list:', error);
  //   // Можно выбросить ошибку или вернуть структуру ошибки, которую UI сможет обработать
  //   throw error;
  // }

  // Моковый ответ
  return Promise.resolve({
    commands: mockCommands,
    language_code: language || 'en', // Возвращаем запрошенный язык или 'en' по умолчанию
  });
};

// Можно добавить другие функции, если потребуется, например, для получения деталей одной команды в будущем.
