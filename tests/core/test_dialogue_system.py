import asyncio
import unittest
from unittest.mock import patch, AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

# Предполагается, что AsyncSession будет мокирована или предоставлена через фикстуру в conftest.py
# Для простоты здесь мы будем использовать AsyncMock для сессии в каждом тесте.

from src.core.dialogue_system import generate_npc_dialogue

class TestDialogueSystem(unittest.IsolatedAsyncioTestCase):

    @patch('src.core.dialogue_system.prepare_dialogue_generation_prompt', new_callable=AsyncMock)
    async def test_generate_npc_dialogue_success(self, mock_prepare_prompt):
        """Тестирует успешную генерацию диалога."""
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        test_context = {
            "npc_id": 10,
            "player_id": 1,
            "player_input_text": "Hello there!",
            "dialogue_history": [],
            "location_id": 100
        }

        mock_prepare_prompt.return_value = "This is a test prompt for the LLM."

        # generate_npc_dialogue использует random.choice для мока ответа LLM.
        # Мы можем либо мокировать random.choice, либо просто проверить, что ответ - одна из ожидаемых строк.
        # Для простоты, проверим, что ответ не пустой и является строкой.
        # Более точный тест потребовал бы мокирования random.choice.

        with patch('random.choice', return_value="A mock NPC response.") as mock_random_choice:
            response = await generate_npc_dialogue(mock_session, guild_id, test_context)

        mock_prepare_prompt.assert_called_once_with(
            session=mock_session,
            guild_id=guild_id,
            context=test_context
        )
        mock_random_choice.assert_called_once() # Убедимся, что наш мок random.choice был вызван
        self.assertIsInstance(response, str)
        self.assertEqual(response, "A mock NPC response.")

    @patch('src.core.dialogue_system.prepare_dialogue_generation_prompt', new_callable=AsyncMock)
    async def test_generate_npc_dialogue_prompt_preparation_error(self, mock_prepare_prompt):
        """Тестирует случай, когда подготовка промпта возвращает ошибку."""
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        test_context = {"npc_id": 10, "player_id": 1, "player_input_text": "Hi"}

        error_message_from_prompt = "Error: Critical information missing for prompt."
        mock_prepare_prompt.return_value = error_message_from_prompt

        response = await generate_npc_dialogue(mock_session, guild_id, test_context)

        self.assertTrue(response.startswith("I seem to be at a loss for words..."))
        self.assertIn(error_message_from_prompt.replace("Error: ", ""), response)

    @patch('src.core.dialogue_system.prepare_dialogue_generation_prompt', new_callable=AsyncMock)
    @patch('random.choice') # Мокируем random.choice на уровне модуля
    async def test_generate_npc_dialogue_response_cleaning(self, mock_random_choice, mock_prepare_prompt):
        """Тестирует базовую очистку ответа LLM (удаление кавычек)."""
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        test_context = {"npc_id": 10, "player_id": 1, "player_input_text": "Tell me a secret."}

        mock_prepare_prompt.return_value = "A valid prompt."

        # Случай 1: Ответ с кавычками
        mock_random_choice.return_value = '"This is a secret response."'
        response1 = await generate_npc_dialogue(mock_session, guild_id, test_context)
        self.assertEqual(response1, "This is a secret response.")

        # Случай 2: Ответ без кавычек
        mock_random_choice.return_value = "Another response without quotes."
        response2 = await generate_npc_dialogue(mock_session, guild_id, test_context)
        self.assertEqual(response2, "Another response without quotes.")

        # Случай 3: Ответ с пробелами и кавычками
        mock_random_choice.return_value = '  "  Spaced out secret.  "  '
        response3 = await generate_npc_dialogue(mock_session, guild_id, test_context)
        self.assertEqual(response3, "Spaced out secret.") # Ожидаем, что внутренние пробелы также будут удалены

    @patch('src.core.dialogue_system.prepare_dialogue_generation_prompt', side_effect=Exception("Unexpected error during prompt generation"))
    async def test_generate_npc_dialogue_unexpected_exception(self, mock_prepare_prompt_exception):
        """Тестирует обработку неожиданного исключения во время работы функции."""
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        test_context = {"npc_id": 10, "player_id": 1, "player_input_text": "What if something breaks?"}

        response = await generate_npc_dialogue(mock_session, guild_id, test_context)

        self.assertEqual(response, "I'm sorry, I'm having a little trouble formulating a response right now. Perhaps we can talk about something else?")
        mock_prepare_prompt_exception.assert_called_once()

    @patch('src.core.dialogue_system.prepare_dialogue_generation_prompt', new_callable=AsyncMock)
    @patch('random.choice')
    async def test_generate_npc_dialogue_with_special_player_input(self, mock_random_choice, mock_prepare_prompt):
        """Тестирует передачу специального/длинного ввода игрока."""
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1

        long_input = "This is a very long player input, " + ("spamming words for length " * 10) + "to check if it's handled."
        special_char_input = "Hello? Is this thing on? \"Quotes\" and 'apostrophes' with !@#$%^&*()_+{}|:\"<>?`~[]\\;',./"

        contexts_to_test = [
            {"npc_id": 1, "player_id": 1, "player_input_text": long_input, "player_name": "Loquacious"},
            {"npc_id": 2, "player_id": 2, "player_input_text": special_char_input, "player_name": "Symbolic"}
        ]

        for i, test_context in enumerate(contexts_to_test):
            with self.subTest(input_type=f"context_{i}"):
                mock_prepare_prompt.reset_mock()
                mock_random_choice.reset_mock()

                mock_prepare_prompt.return_value = f"Prompt for input: {test_context['player_input_text']}"

                # Мок ответа LLM должен использовать player_input_text, как это делает реальная мок-логика в SUT
                expected_mock_llm_response = f"NPC ponders about \"{test_context['player_input_text']}\"."
                mock_random_choice.return_value = expected_mock_llm_response

                response = await generate_npc_dialogue(mock_session, guild_id, test_context)

                mock_prepare_prompt.assert_called_once_with(
                    session=mock_session,
                    guild_id=guild_id,
                    context=test_context
                )
                # Проверяем, что player_input_text в моке ответа LLM соответствует тому, что было в test_context
                self.assertIn(test_context['player_input_text'], mock_random_choice.call_args[0][0][0]) # Проверяем первый элемент списка, переданного в random.choice
                self.assertEqual(response, expected_mock_llm_response)


if __name__ == '__main__':
    unittest.main()
