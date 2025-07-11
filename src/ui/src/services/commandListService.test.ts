// src/ui/src/services/commandListService.test.ts
import { fetchCommandList } from './commandListService';
// import { UICommandListResponse } from '../types/commands'; // Not strictly needed for these tests

// Если бы мы тестировали реальный API вызов с apiClient, мы бы мокировали apiClient.
// Поскольку fetchCommandList сейчас возвращает моковые данные напрямую, тест будет простым.

describe('commandListService', () => {
  describe('fetchCommandList', () => {
    // Тест на то, что функция возвращает данные, соответствующие структуре (хотя бы базово)
    test('should return mock command list data with expected structure', async () => {
      const response = await fetchCommandList(); // No language, should default
      expect(response).toBeDefined();
      expect(Array.isArray(response.commands)).toBe(true);

      // Проверяем, что в моковых данных есть хотя бы одна команда (согласно текущему моку)
      if (response.commands.length > 0) {
        const firstCommand = response.commands[0];
        expect(firstCommand).toHaveProperty('name');
        expect(firstCommand).toHaveProperty('description');
        expect(firstCommand).toHaveProperty('parameters');
        expect(Array.isArray(firstCommand.parameters)).toBe(true);
      } else {
        // Если мок может вернуть пустой массив, это тоже валидный сценарий
        expect(response.commands.length).toBe(0);
      }

      expect(response.language_code).toBe('en'); // Default mock language
    });

    test('should reflect requested language in language_code for mock response', async () => {
      const lang = 'ru';
      const response = await fetchCommandList(lang);
      expect(response.language_code).toBe(lang);
      // Дополнительно можно проверить, что сами команды (если бы мок их менял) соответствуют языку,
      // но текущий мок просто меняет language_code.
    });

    test('mock should contain specific commands as defined in the service', async () => {
        const response = await fetchCommandList();
        const commandNames = response.commands.map(cmd => cmd.name);
        expect(commandNames).toContain('ping');
        expect(commandNames).toContain('help');
        expect(commandNames).toContain('party create');
        expect(commandNames).toContain('master_player view');
        expect(commandNames).toContain('ban');
    });

    // Если бы это был реальный API вызов с использованием apiClient, тест мог бы выглядеть так:
    //
    // import apiClient from './apiClient'; // Предполагаем, что apiClient экспортируется
    // jest.mock('./apiClient'); // Мокируем apiClient
    // const mockedApiClient = apiClient as jest.Mocked<typeof apiClient>;

    // test('should call the correct API endpoint with language parameter via apiClient', async () => {
    //   const mockApiResponseData: UICommandListResponse = { commands: [], language_code: 'de' };
    //   mockedApiClient.get = jest.fn().mockResolvedValue({ data: mockApiResponseData });

    //   const lang = 'de';
    //   const result = await fetchCommandList(lang); // Используем реальную функцию, но с мокнутым apiClient

    //   expect(mockedApiClient.get).toHaveBeenCalledWith('/api/v1/command-list/', { params: { language: lang } });
    //   expect(result).toEqual(mockApiResponseData);
    // });

    // test('should throw an error if apiClient.get fails', async () => {
    //   mockedApiClient.get = jest.fn().mockRejectedValue(new Error("API Network Error"));

    //   await expect(fetchCommandList('en')).rejects.toThrow("API Network Error");
    // });
  });
});
