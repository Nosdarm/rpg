import logging
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .ai_prompt_builder import prepare_dialogue_generation_prompt
from .ai_orchestrator import _mock_openai_api_call # Используем существующий мок
# Если понадобится реальный вызов LLM в будущем:
# from .ai_orchestrator import make_real_ai_call
from .database import transactional # Для управления сессиями, если потребуется
from typing import Tuple, List # Добавлено для active_dialogues

from ..models import Player, GeneratedNpc # Добавлено для start_dialogue
from ..models.enums import PlayerStatus, EventType # Добавлено для start_dialogue
from .crud.crud_player import player_crud # Добавлено для start_dialogue
from .crud.crud_npc import npc_crud # Добавлено для start_dialogue
from .game_events import log_event # Добавлено для start_dialogue


logger = logging.getLogger(__name__)

# Словарь для хранения активных диалоговых сессий
# Ключ: (guild_id, player_id)
# Значение: { "npc_id": int, "npc_name": str, "dialogue_history": List[Dict[str, str]] }
# dialogue_history: [{"speaker": "player/npc", "line": "text"}, ...]
active_dialogues: Dict[Tuple[int, int], Dict[str, Any]] = {}

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


async def start_dialogue(
    session: AsyncSession,
    guild_id: int,
    player_id: int,
    target_npc_id: int
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Starts a dialogue session between a player and an NPC.

    Args:
        session: The database session.
        guild_id: The ID of the guild.
        player_id: The ID of the player initiating the dialogue.
        target_npc_id: The ID of the NPC to talk to.

    Returns:
        A tuple (success: bool, message_key: str, context_data: Optional[Dict[str, Any]]).
        message_key is for localization. context_data can contain npc_name.
    """
    dialogue_key = (guild_id, player_id)

    player = await player_crud.get_by_id_and_guild(session=session, id=player_id, guild_id=guild_id)
    if not player:
        logger.warning(f"start_dialogue: Player {player_id} not found in guild {guild_id}.")
        return False, "dialogue_error_player_not_found", None

    npc = await npc_crud.get_by_id_and_guild(session=session, id=target_npc_id, guild_id=guild_id)
    if not npc:
        logger.warning(f"start_dialogue: NPC {target_npc_id} not found in guild {guild_id}.")
        return False, "dialogue_error_npc_not_found", {"player_name": player.name}

    # Проверка, не находится ли игрок уже в диалоге или в бою
    if dialogue_key in active_dialogues:
        # Если уже говорит с этим же NPC, можно считать это успехом или продолжением
        if active_dialogues[dialogue_key]["npc_id"] == target_npc_id:
            npc_name = active_dialogues[dialogue_key]["npc_name"]
            logger.info(f"Player {player_id} is already in dialogue with NPC {target_npc_id} ({npc_name}).")
            return True, "dialogue_already_started_with_npc", {"npc_name": npc_name}
        else:
            # Говорит с другим NPC
            current_npc_name = active_dialogues[dialogue_key]["npc_name"]
            logger.warning(f"Player {player_id} is already in dialogue with {current_npc_name}. Cannot start new one with {npc.name_i18n.get(player.selected_language, npc.name_i18n.get('en'))}.")
            return False, "dialogue_error_player_busy_other_npc", {"npc_name": current_npc_name}

    if player.current_status == PlayerStatus.COMBAT:
        logger.warning(f"Player {player_id} is in COMBAT state. Cannot start dialogue.")
        return False, "dialogue_error_player_in_combat", {"player_name": player.name}

    # TODO: Проверка, не занят ли NPC другим диалогом (если NPC могут говорить только с одним)
    # for key, ongoing_dialogue in active_dialogues.items():
    #     if key[0] == guild_id and ongoing_dialogue["npc_id"] == target_npc_id:
    #         # NPC уже говорит с другим игроком key[1]
    #         logger.warning(f"NPC {target_npc_id} is already in dialogue with player {key[1]}.")
    #         other_player = await player_crud.get_by_id_and_guild(session=session, id=key[1], guild_id=guild_id)
    #         other_player_name = other_player.name if other_player else "another player"
    #         return False, "dialogue_error_npc_busy", {"npc_name": npc.name_i18n.get(player.selected_language, npc.name_i18n.get("en")), "other_player_name": other_player_name}


    # Установка статуса и создание записи о диалоге
    player.current_status = PlayerStatus.DIALOGUE
    session.add(player)

    npc_display_name = npc.name_i18n.get(player.selected_language, npc.name_i18n.get("en", "the NPC"))
    active_dialogues[dialogue_key] = {
        "npc_id": target_npc_id,
        "npc_name": npc_display_name, # Сохраняем имя NPC на языке игрока для удобства
        "dialogue_history": [] # Инициализируем историю для этой сессии
    }

    await log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.DIALOGUE_START.name, # Используем .name для передачи строки
        details_json={
            "player_id": player_id,
            "npc_id": target_npc_id,
            "npc_name": npc_display_name # Логируем имя NPC на языке игрока
        },
        player_id=player_id,
        location_id=player.current_location_id,
        entity_ids_json={"players": [player_id], "npcs": [target_npc_id]}
    )

    logger.info(f"Player {player_id} ({player.name}) started dialogue with NPC {target_npc_id} ({npc_display_name}) in guild {guild_id}.")
    return True, "dialogue_started_success", {"npc_name": npc_display_name, "player_name": player.name}


async def handle_dialogue_input(
    session: AsyncSession,
    guild_id: int,
    player_id: int,
    message_text: str
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Handles player's input during a dialogue session and gets NPC's response.

    Args:
        session: The database session.
        guild_id: The ID of the guild.
        player_id: The ID of the player providing input.
        message_text: The player's dialogue line.

    Returns:
        A tuple (success: bool, response_or_error_key: str, context_data: Optional[Dict[str, Any]]).
        If success, response_or_error_key is the NPC's response string.
        If not success, response_or_error_key is an error message key.
        context_data may contain npc_name.
    """
    dialogue_key = (guild_id, player_id)
    dialogue_session_data = active_dialogues.get(dialogue_key)

    if not dialogue_session_data:
        logger.warning(f"handle_dialogue_input: Player {player_id} in guild {guild_id} is not in an active dialogue.")
        return False, "dialogue_error_not_in_dialogue", None

    player = await player_crud.get_by_id_and_guild(session=session, id=player_id, guild_id=guild_id)
    if not player: # Should not happen if dialogue_session_data exists, but good practice
        logger.error(f"handle_dialogue_input: Player {player_id} not found for active dialogue in guild {guild_id}.")
        active_dialogues.pop(dialogue_key, None) # Clean up inconsistent state
        return False, "dialogue_error_player_not_found_for_active_session", None

    npc_id = dialogue_session_data["npc_id"]
    npc_name = dialogue_session_data["npc_name"] # Имя NPC на языке игрока

    # Логируем реплику игрока
    await log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.DIALOGUE_LINE.name,
        details_json={
            "player_id": player_id,
            "npc_id": npc_id,
            "speaker": "player",
            "line": message_text,
            "npc_name": npc_name,
            "player_name": player.name
        },
        player_id=player_id,
        location_id=player.current_location_id,
        entity_ids_json={"players": [player_id], "npcs": [npc_id]}
    )
    dialogue_session_data["dialogue_history"].append({"speaker": "player", "line": message_text})


    # Формируем контекст для генерации ответа NPC
    # Убедимся, что все необходимые поля для prepare_dialogue_generation_prompt присутствуют
    # npc_model = await npc_crud.get_by_id_and_guild(session=session, id=npc_id, guild_id=guild_id)
    # if not npc_model:
    #     logger.error(f"handle_dialogue_input: NPC {npc_id} from active_dialogues not found for player {player_id}, guild {guild_id}.")
    #     active_dialogues.pop(dialogue_key, None) # Clean up
    #     return False, "dialogue_error_npc_disappeared", {"npc_name": npc_name}


    context_for_llm = {
        "guild_id": guild_id,
        "player_id": player_id,
        "player_name": player.name,
        "npc_id": npc_id,
        # "npc_name": npc_name, # prepare_dialogue_generation_prompt сам загрузит NPC и его имя
        "player_input_text": message_text,
        "dialogue_history": list(dialogue_session_data["dialogue_history"]), # <--- Создаем копию списка
        "selected_language": player.selected_language,
        "location_id": player.current_location_id, # Добавляем location_id, если он есть у игрока
        "party_id": player.current_party_id # Добавляем party_id, если он есть у игрока
    }

    logger.debug(f"Context for LLM in handle_dialogue_input for player {player_id}, npc {npc_id}: {context_for_llm}")


    npc_response_text = await generate_npc_dialogue(session, guild_id, context_for_llm)

    # Добавляем ответ NPC в оригинальный список истории в сессии
    active_dialogues[dialogue_key]["dialogue_history"].append({"speaker": "npc", "line": npc_response_text})
    # Ограничение длины истории диалога, если нужно (например, последние N реплик)
    max_history_len = 10 # Например, хранить последние 10 обменов (20 реплик)
    if len(dialogue_session_data["dialogue_history"]) > max_history_len * 2:
        dialogue_session_data["dialogue_history"] = dialogue_session_data["dialogue_history"][-max_history_len*2:]


    # Логируем ответ NPC
    await log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.DIALOGUE_LINE.name,
        details_json={
            "player_id": player_id,
            "npc_id": npc_id,
            "speaker": "npc",
            "line": npc_response_text,
            "npc_name": npc_name,
            "player_name": player.name
        },
        player_id=player_id, # Ответ NPC инициирован действием игрока
        location_id=player.current_location_id,
        entity_ids_json={"players": [player_id], "npcs": [npc_id]}
    )

    logger.info(f"NPC {npc_id} ({npc_name}) responded to Player {player_id} ({player.name}) in guild {guild_id}: \"{npc_response_text}\"")
    return True, npc_response_text, {"npc_name": npc_name, "player_name": player.name}


async def end_dialogue(
    session: AsyncSession,
    guild_id: int,
    player_id: int
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Ends the current dialogue session for a player.

    Args:
        session: The database session.
        guild_id: The ID of the guild.
        player_id: The ID of the player ending the dialogue.

    Returns:
        A tuple (success: bool, message_key: str, context_data: Optional[Dict[str, Any]]).
        message_key is for localization. context_data may contain npc_name.
    """
    dialogue_key = (guild_id, player_id)
    dialogue_session_data = active_dialogues.get(dialogue_key)

    if not dialogue_session_data:
        logger.warning(f"end_dialogue: Player {player_id} in guild {guild_id} is not in an active dialogue to end.")
        # Можно вернуть True, если игрок и так не в диалоге, чтобы команда "end" не выдавала ошибку без надобности
        player_check = await player_crud.get_by_id_and_guild(session=session, id=player_id, guild_id=guild_id)
        if player_check and player_check.current_status != PlayerStatus.DIALOGUE:
             return True, "dialogue_not_active_already_ended", None # Игрок не в диалоге
        return False, "dialogue_error_not_in_dialogue_to_end", None


    npc_id = dialogue_session_data["npc_id"]
    npc_name = dialogue_session_data["npc_name"] # Имя NPC на языке игрока

    player = await player_crud.get_by_id_and_guild(session=session, id=player_id, guild_id=guild_id)
    if not player: # Маловероятно, но для полноты
        logger.error(f"end_dialogue: Player {player_id} not found for active dialogue in guild {guild_id}.")
        active_dialogues.pop(dialogue_key, None) # Очистка
        return False, "dialogue_error_player_not_found_on_end", {"npc_name": npc_name}

    if player.current_status == PlayerStatus.DIALOGUE:
        player.current_status = PlayerStatus.EXPLORING # Или IDLE, если это более подходящий статус по умолчанию
        session.add(player)
        logger.info(f"Player {player_id} status changed from DIALOGUE to EXPLORING.")
    else:
        logger.warning(f"Player {player_id} was in active_dialogues but status was {player.current_status}, not DIALOGUE. Ending dialogue anyway.")

    active_dialogues.pop(dialogue_key, None)

    await log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.DIALOGUE_END.name,
        details_json={
            "player_id": player_id,
            "npc_id": npc_id,
            "npc_name": npc_name,
            "player_name": player.name,
            "dialogue_history_length": len(dialogue_session_data.get("dialogue_history", []))
        },
        player_id=player_id,
        location_id=player.current_location_id,
        entity_ids_json={"players": [player_id], "npcs": [npc_id]}
    )

    logger.info(f"Player {player_id} ({player.name}) ended dialogue with NPC {npc_id} ({npc_name}) in guild {guild_id}.")
    return True, "dialogue_ended_success", {"npc_name": npc_name, "player_name": player.name}
