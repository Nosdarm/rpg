import logging
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .ai_prompt_builder import prepare_dialogue_generation_prompt
from .ai_orchestrator import _mock_openai_api_call # Используем существующий мок
# Если понадобится реальный вызов LLM в будущем:
# from .ai_orchestrator import make_real_ai_call
from .database import transactional # Для управления сессиями, если потребуется

logger = logging.getLogger(__name__)

@transactional
async def generate_npc_dialogue(
    session: AsyncSession, # transactional передаст сессию
    guild_id: int,
    context: Dict[str, Any]
) -> str:
    """
    Generates an NPC dialogue line based on the provided context.

    Args:
        session: The database session.
        guild_id: The ID of the guild.
        context: A dictionary containing necessary context for dialogue generation,
                 as expected by prepare_dialogue_generation_prompt.
                 Required keys: npc_id, player_id, player_input_text.
                 Optional: party_id, dialogue_history, location_id.

    Returns:
        A string containing the generated NPC dialogue line, or an error message.
    """
    logger.info(f"Generating NPC dialogue for guild {guild_id}, player input: '{context.get('player_input_text')}'")

    try:
        # 1. Prepare the prompt for the LLM
        prompt = await prepare_dialogue_generation_prompt(
            session=session,
            guild_id=guild_id,
            context=context
        )

        if prompt.startswith("Error:"):
            logger.error(f"Failed to prepare dialogue prompt: {prompt}")
            # Возвращаем ошибку пользователю в виде реплики, чтобы было понятно, что что-то пошло не так
            # Можно сделать это более общим сообщением в будущем
            return f"I seem to be at a loss for words... ({prompt.replace('Error: ', '')})"

        # 2. Call the LLM (currently using a local mock for simplicity)
        # В будущем здесь может быть реальный вызов:
        # if use_real_ai_from_config: # (например, из RuleConfig)
        #     llm_response_str = await make_real_ai_call(prompt, guild_id, model="gpt-3.5-turbo-instruct" or similar for dialogue)
        # else:
        #     llm_response_str = await _mock_openai_api_call(prompt) # _mock_openai_api_call возвращает JSON

        # Простой мок для диалоговых ответов, чтобы не зависеть от структуры JSON _mock_openai_api_call
        import random
        player_name = context.get("player_name", "traveler") # Получим имя игрока из контекста, если оно там есть

        # Получим имя NPC из контекста, если оно было добавлено в prepare_dialogue_generation_prompt
        # Это можно сделать, передав npc_name в context или загрузив NPC здесь снова (менее оптимально)
        # Для простоты мока, пока не используем имя NPC в ответе.

        mock_dialogue_responses = [
            f"Ah, {player_name}, you mention \"{context.get('player_input_text','')}\"? That's an interesting perspective.",
            "I understand. What else is on your mind?",
            "Is that truly what you think? Tell me more about your reasoning.",
            "Hmm, I shall ponder this. It gives me much to consider.",
            f"'{context.get('player_input_text','')}'... A curious thing to say. Why do you ask?",
            "Indeed. The currents of fate are ever-shifting, wouldn't you agree?"
        ]
        llm_response_str = random.choice(mock_dialogue_responses)
        logger.info(f"Mock LLM response for dialogue (NPC ID: {context.get('npc_id')}): \"{llm_response_str}\"")


        # 3. Process the LLM response (basic cleaning)
        processed_response = llm_response_str.strip()
        # Убираем кавычки, если LLM их добавил по краям всей строки
        if processed_response.startswith('"') and processed_response.endswith('"'):
            processed_response = processed_response[1:-1].strip() # Возвращен .strip()

        # Опционально: Убрать префиксы типа "NPC:" или "As NPC_NAME, I say:", если они иногда появляются.
        # Это очень базовый способ, можно улучшить регулярными выражениями или более умной логикой.
        # if ":" in processed_response and len(processed_response.split(":", 1)[0]) < 30:
        #     # Если есть двоеточие и префикс до него короткий (предположительно, имя/роль)
        #     possible_prefix = processed_response.split(":", 1)[0]
        #     if "npc" in possible_prefix.lower() or context.get("npc_name","").lower() in possible_prefix.lower():
        #          processed_response = processed_response.split(":", 1)[1].strip()

        logger.info(f"Processed NPC dialogue response for guild {guild_id}: \"{processed_response}\"")
        return processed_response

    except Exception as e:
        logger.exception(f"Error in generate_npc_dialogue for guild {guild_id}, context keys: {list(context.keys()) if isinstance(context,dict) else 'InvalidContext'}: {e}")
        # Возвращаем дружелюбное сообщение об ошибке в виде реплики NPC
        return "I'm sorry, I'm having a little trouble formulating a response right now. Perhaps we can talk about something else?"

logger.info("Dialogue system module (dialogue_system.py) created with generate_npc_dialogue API.")
