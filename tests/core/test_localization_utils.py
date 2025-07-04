# tests/core/test_localization_utils.py
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.localization_utils import get_localized_text, get_localized_entity_name, get_batch_localized_entity_names # Added import
from src.models import Player, Location, GeneratedNpc, Item # Assuming these models exist

# Mock model instances
@pytest.fixture
def mock_player_instance():
    player = Player(id=1, guild_id=100, name="PlayerOne")
    # Player model doesn't have name_i18n statically defined.
    # We are adding it here for testing get_localized_entity_name's i18n capabilities.
    # The function uses hasattr, so this will work at runtime.
    player.name_i18n = {"en": "Player One", "ru": "Игрок Один"}  # type: ignore[attr-defined]
    return player

@pytest.fixture
def mock_location_instance():
    loc = Location(id=1, guild_id=100, static_id="loc1")
    loc.name_i18n = {"en": "Central Square", "ru": "Центральная Площадь"}
    return loc

@pytest.fixture
def mock_npc_instance():
    npc = GeneratedNpc(id=1, guild_id=100)
    npc.name_i18n = {"en": "Old Man Willow", "ru": "Старый Иваныч"}
    return npc

@pytest.fixture
def mock_item_instance():
    item = Item(id=1, guild_id=100)
    item.name_i18n = {"en": "Rusty Sword", "ru": "Ржавый Меч"}
    return item

@pytest.fixture
def mock_nameless_entity_instance():
    entity = MagicMock(spec=Player) # Use a real model for spec if possible
    entity.id = 5
    entity.guild_id = 100
    entity.name_i18n = None # No i18n name
    entity.name = None      # No plain name either
    return entity

@pytest.fixture
def mock_plain_name_entity_instance():
    entity = MagicMock(spec=Player)
    entity.id = 6
    entity.guild_id = 100
    entity.name_i18n = {"es": "Jugador Seis"} # Some other language
    entity.name = "Player Six Plain" # Has a plain name
    return entity


# Tests for get_localized_text (already in localization_utils, but good to have direct tests)
@pytest.mark.parametrize("i18n_field, lang, fallback_lang, expected", [
    ({"en": "Hello", "ru": "Привет"}, "en", "ru", "Hello"),
    ({"en": "Hello", "ru": "Привет"}, "ru", "en", "Привет"),
    ({"en": "Hello"}, "ru", "en", "Hello"), # Fallback to en
    ({"ru": "Привет"}, "en", "ru", "Привет"), # Fallback to ru
    ({"es": "Hola"}, "en", "es", "Hola"),    # Fallback to another lang if primary fallback not found
    (None, "en", "ru", ""),
    ({}, "en", "ru", ""),
    ({"en": ""}, "en", "ru", ""), # Empty string for requested lang
    # For this case, if 'en' and 'ru' are not found, it should return ""
    # as per the modified get_localized_text logic.
    ({"fr": "Bonjour"}, "en", "ru", ""),
])
def test_get_localized_text(i18n_field, lang, fallback_lang, expected):
    assert get_localized_text(i18n_field, lang, fallback_lang) == expected

# --- Tests for get_localized_entity_name ---

# Patching the ENTITY_TYPE_GETTER_MAP directly for most tests
# We assume the lambda functions in the map correctly call their respective (mocked) getters.

@pytest.mark.asyncio
async def test_get_localized_entity_name_player_success(mock_db_session: AsyncSession, mock_player_instance: Player): # mock_session -> mock_db_session
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_specific_player_getter = AsyncMock(return_value=mock_player_instance)
        mock_getter_map.get.return_value = mock_specific_player_getter

        name_en = await get_localized_entity_name(mock_db_session, 100, "player", 1, "en")
        assert name_en == "Player One"
        mock_specific_player_getter.assert_called_once_with(mock_db_session, 100, 1)
        mock_getter_map.get.assert_called_with("player")

        mock_specific_player_getter.reset_mock()
        name_ru = await get_localized_entity_name(mock_db_session, 100, "player", 1, "ru")
        assert name_ru == "Игрок Один"
        mock_specific_player_getter.assert_called_once_with(mock_db_session, 100, 1)

        mock_specific_player_getter.reset_mock()
        name_fr_fallback_en = await get_localized_entity_name(mock_db_session, 100, "player", 1, "fr", "en")
        assert name_fr_fallback_en == "Player One" # Falls back to English
        mock_specific_player_getter.assert_called_once_with(mock_db_session, 100, 1)

@pytest.mark.asyncio
async def test_get_localized_entity_name_location_success(mock_db_session: AsyncSession, mock_location_instance: Location): # mock_session -> mock_db_session
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_specific_loc_getter = AsyncMock(return_value=mock_location_instance)
        mock_getter_map.get.return_value = mock_specific_loc_getter

        name_en = await get_localized_entity_name(mock_db_session, 100, "location", 1, "en")
        assert name_en == "Central Square"
        mock_specific_loc_getter.assert_called_once_with(mock_db_session, 100, 1)

@pytest.mark.asyncio
async def test_get_localized_entity_name_npc_success(mock_db_session: AsyncSession, mock_npc_instance: GeneratedNpc): # mock_session -> mock_db_session
     with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_specific_npc_getter = AsyncMock(return_value=mock_npc_instance)
        mock_getter_map.get.return_value = mock_specific_npc_getter

        name_ru = await get_localized_entity_name(mock_db_session, 100, "npc", 1, "ru")
        assert name_ru == "Старый Иваныч"
        mock_specific_npc_getter.assert_called_once_with(mock_db_session, 100, 1)


@pytest.mark.asyncio
async def test_get_localized_entity_name_item_success(mock_db_session: AsyncSession, mock_item_instance: Item): # mock_session -> mock_db_session
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_specific_item_getter = AsyncMock(return_value=mock_item_instance)
        mock_getter_map.get.return_value = mock_specific_item_getter

        name_en = await get_localized_entity_name(mock_db_session, 100, "item", 1, "en")
        assert name_en == "Rusty Sword"
        mock_specific_item_getter.assert_called_once_with(mock_db_session, 100, 1)

@pytest.mark.asyncio
async def test_get_localized_entity_name_entity_not_found(mock_db_session: AsyncSession): # mock_session -> mock_db_session
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_getter_that_returns_none = AsyncMock(return_value=None)
        mock_getter_map.get.return_value = mock_getter_that_returns_none

        name = await get_localized_entity_name(mock_db_session, 100, "player", 99, "en")
        assert name == "[Player ID: 99 (Unknown)]"
        mock_getter_that_returns_none.assert_called_once_with(mock_db_session, 100, 99)

@pytest.mark.asyncio
async def test_get_localized_entity_name_unsupported_type(mock_db_session: AsyncSession): # mock_session -> mock_db_session
    # No need to patch ENTITY_TYPE_GETTER_MAP if .get() will return None for the key
    with patch("src.core.localization_utils.ENTITY_TYPE_MODEL_MAP", new_callable=MagicMock) as mock_model_map:
        mock_model_map.get.return_value = None # Ensure model map also doesn't find it
        with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP", new_callable=MagicMock) as mock_getter_map:
            mock_getter_map.get.return_value = None # Ensure getter map doesn't find it

            name = await get_localized_entity_name(mock_db_session, 100, "dragon", 1, "en")
            assert name == "[dragon ID: 1]"
            # mock_model_map.get.assert_called_with("dragon") # This is no longer called
            mock_getter_map.get.assert_called_with("dragon")


@pytest.mark.asyncio
async def test_get_localized_entity_name_nameless_entity(mock_db_session: AsyncSession, mock_nameless_entity_instance: MagicMock): # mock_session -> mock_db_session
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_getter = AsyncMock(return_value=mock_nameless_entity_instance)
        mock_getter_map.get.return_value = mock_getter

        name = await get_localized_entity_name(mock_db_session, 100, "player", 5, "en")
        assert name == "[Player ID: 5 (Nameless)]"

@pytest.mark.asyncio
async def test_get_localized_entity_name_plain_name_fallback(mock_db_session: AsyncSession, mock_plain_name_entity_instance: MagicMock): # mock_session -> mock_db_session
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_getter = AsyncMock(return_value=mock_plain_name_entity_instance)
        mock_getter_map.get.return_value = mock_getter

        # Requested 'en', name_i18n only has 'es', so it should fallback to plain 'name'
        name = await get_localized_entity_name(mock_db_session, 100, "player", 6, "en")
        assert name == "Player Six Plain"

@pytest.mark.asyncio
async def test_get_localized_entity_name_getter_exception(mock_db_session: AsyncSession): # mock_session -> mock_db_session
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_getter_with_exception = AsyncMock(side_effect=Exception("Database connection failed"))
        mock_getter_map.get.return_value = mock_getter_with_exception

        name = await get_localized_entity_name(mock_db_session, 100, "item", 123, "en")
        assert name == "[Item ID: 123 (Error)]"

# The test `test_get_localized_entity_name_generic_getter_fallback` was removed
# because the generic fallback mechanism using `get_entity_by_id_gino_style` and
# `ENTITY_TYPE_MODEL_MAP` (when a specific getter is not found) has been removed
# from `src.core.localization_utils.get_localized_entity_name`.
# The current behavior (returning a placeholder like "[entity_type ID: entity_id]")
# is already covered by `test_get_localized_entity_name_unsupported_type`.

@pytest.mark.asyncio
async def test_get_batch_localized_entity_names_success(mock_db_session: AsyncSession): # mock_session -> mock_db_session
    guild_id = 100

    player1 = MagicMock(spec=Player)
    player1.id = 1
    player1.name_i18n = {"en": "Player Alpha", "ru": "Игрок Альфа"}
    player1.name = "PlayerAlphaPlain" # For fallback testing if needed

    loc1 = MagicMock(spec=Location)
    loc1.id = 10
    loc1.name_i18n = {"en": "Location Beta", "ru": "Локация Бета"}
    loc1.name = "LocationBetaPlain"

    item1 = MagicMock(spec=Item)
    item1.id = 20
    item1.name_i18n = {"en": "Item Gamma", "ru": "Предмет Гамма"}
    item1.name = "ItemGammaPlain"

    entities_to_fetch = [
        {"entity_type": "player", "entity_id": 1},
        {"entity_type": "location", "entity_id": 10},
        {"entity_type": "item", "entity_id": 20},
        {"entity_type": "player", "entity_id": 2}, # Non-existent player
    ]

    mock_player_crud_instance = MagicMock()
    mock_player_crud_instance.get_many_by_ids = AsyncMock(return_value=[player1]) # Only player1 exists

    mock_location_crud_instance = MagicMock()
    mock_location_crud_instance.get_many_by_ids = AsyncMock(return_value=[loc1])

    mock_item_crud_instance = MagicMock()
    mock_item_crud_instance.get_many_by_ids = AsyncMock(return_value=[item1])


    with patch("src.core.localization_utils.ENTITY_TYPE_CRUD_MAP", {
        "player": mock_player_crud_instance,
        "location": mock_location_crud_instance,
        "item": mock_item_crud_instance
    }):
        names_cache_en = await get_batch_localized_entity_names(mock_db_session, guild_id, entities_to_fetch, "en")
        names_cache_ru = await get_batch_localized_entity_names(mock_db_session, guild_id, entities_to_fetch, "ru", "en")

    assert names_cache_en[("player", 1)] == "Player Alpha"
    assert names_cache_en[("location", 10)] == "Location Beta"
    assert names_cache_en[("item", 20)] == "Item Gamma"
    assert names_cache_en.get(("player", 2)) == "[player ID: 2 (Unknown)]" # Исправлено P -> p

    assert names_cache_ru[("player", 1)] == "Игрок Альфа"
    assert names_cache_ru[("location", 10)] == "Локация Бета"
    assert names_cache_ru[("item", 20)] == "Предмет Гамма"

    mock_player_crud_instance.get_many_by_ids.assert_any_call(db=mock_db_session, ids=[1, 2], guild_id=guild_id)
    mock_location_crud_instance.get_many_by_ids.assert_any_call(db=mock_db_session, ids=[10], guild_id=guild_id)
    mock_item_crud_instance.get_many_by_ids.assert_any_call(db=mock_db_session, ids=[20], guild_id=guild_id)
    # Each CRUD's get_many_by_ids should be called twice (once for 'en', once for 'ru')
    assert mock_player_crud_instance.get_many_by_ids.call_count == 2
    assert mock_location_crud_instance.get_many_by_ids.call_count == 2
    assert mock_item_crud_instance.get_many_by_ids.call_count == 2


@pytest.mark.asyncio
async def test_get_batch_localized_entity_names_empty_input(mock_db_session: AsyncSession): # mock_session -> mock_db_session
    names_cache = await get_batch_localized_entity_names(mock_db_session, 100, [], "en")
    assert names_cache == {}

@pytest.mark.asyncio
async def test_get_batch_localized_entity_names_unsupported_type_in_batch(mock_db_session: AsyncSession): # mock_session -> mock_db_session
    guild_id = 100
    entities_to_fetch = [{"entity_type": "dragon", "entity_id": 1}]
    with patch("src.core.localization_utils.ENTITY_TYPE_CRUD_MAP", {}): # Ensure dragon is not in map
        names_cache = await get_batch_localized_entity_names(mock_db_session, guild_id, entities_to_fetch, "en")
    assert names_cache[("dragon", 1)] == "[dragon ID: 1 (No CRUD)]" # Исправлено


@pytest.mark.asyncio
async def test_get_batch_localized_entity_names_crud_exception(mock_db_session: AsyncSession): # mock_session -> mock_db_session
    guild_id = 100
    entities_to_fetch = [{"entity_type": "player", "entity_id": 1}]

    mock_player_crud_failing = MagicMock()
    mock_player_crud_failing.get_many_by_ids = AsyncMock(side_effect=Exception("DB error"))

    with patch("src.core.localization_utils.ENTITY_TYPE_CRUD_MAP", {"player": mock_player_crud_failing}):
        names_cache = await get_batch_localized_entity_names(mock_db_session, guild_id, entities_to_fetch, "en")

    assert names_cache[("player", 1)] == "[player ID: 1 (Error)]" # Исправлено P -> p

@pytest.mark.asyncio
async def test_get_batch_localized_entity_names_all_entities_not_found(mock_db_session: AsyncSession):
    guild_id = 100
    entities_to_fetch = [
        {"entity_type": "player", "entity_id": 1},
        {"entity_type": "location", "entity_id": 10},
    ]

    mock_player_crud_instance = MagicMock()
    mock_player_crud_instance.get_many_by_ids = AsyncMock(return_value=[]) # No players found

    mock_location_crud_instance = MagicMock()
    mock_location_crud_instance.get_many_by_ids = AsyncMock(return_value=[]) # No locations found

    with patch("src.core.localization_utils.ENTITY_TYPE_CRUD_MAP", {
        "player": mock_player_crud_instance,
        "location": mock_location_crud_instance,
    }):
        names_cache = await get_batch_localized_entity_names(mock_db_session, guild_id, entities_to_fetch, "en")

    assert names_cache.get(("player", 1)) == "[player ID: 1 (Unknown)]"
    assert names_cache.get(("location", 10)) == "[location ID: 10 (Unknown)]"
    assert len(names_cache) == 2
    mock_player_crud_instance.get_many_by_ids.assert_called_once_with(db=mock_db_session, ids=[1], guild_id=guild_id)
    mock_location_crud_instance.get_many_by_ids.assert_called_once_with(db=mock_db_session, ids=[10], guild_id=guild_id)

@pytest.mark.asyncio
async def test_get_batch_localized_entity_names_fallback_and_nameless(mock_db_session: AsyncSession):
    guild_id = 100

    entity_plain_name = MagicMock(spec=Player)
    entity_plain_name.id = 1
    entity_plain_name.name_i18n = {"fr": "Joueur FR"} # No 'en' or 'ru'
    entity_plain_name.name = "Player Plain Name"

    entity_no_name = MagicMock(spec=Location)
    entity_no_name.id = 2
    entity_no_name.name_i18n = None
    entity_no_name.name = None

    entities_to_fetch = [
        {"entity_type": "player", "entity_id": 1},
        {"entity_type": "location", "entity_id": 2},
    ]

    mock_player_crud_instance = MagicMock()
    mock_player_crud_instance.get_many_by_ids = AsyncMock(return_value=[entity_plain_name])

    mock_location_crud_instance = MagicMock()
    mock_location_crud_instance.get_many_by_ids = AsyncMock(return_value=[entity_no_name])

    with patch("src.core.localization_utils.ENTITY_TYPE_CRUD_MAP", {
        "player": mock_player_crud_instance,
        "location": mock_location_crud_instance,
    }):
        # Request "en", fallback "ru". "fr" exists in i18n, but not requested/fallback, so plain name should be used.
        names_cache = await get_batch_localized_entity_names(mock_db_session, guild_id, entities_to_fetch, "en", "ru")

    assert names_cache.get(("player", 1)) == "Player Plain Name"
    assert names_cache.get(("location", 2)) == "[location ID: 2 (Nameless)]"
    assert len(names_cache) == 2

@pytest.mark.asyncio
async def test_get_batch_localized_entity_names_invalid_refs_skipped(mock_db_session: AsyncSession):
    guild_id = 100
    player1 = MagicMock(spec=Player)
    player1.id = 1
    player1.name_i18n = {"en": "Player Valid"}

    entities_to_fetch = [
        {"entity_type": "player", "entity_id": 1},
        {"entity_type": "player"}, # Missing entity_id
        {"entity_id": 2}, # Missing entity_type
        {"entity_type": "player", "entity_id": "not_an_int"},
        "not_a_dict"
    ]

    mock_player_crud_instance = MagicMock()
    mock_player_crud_instance.get_many_by_ids = AsyncMock(return_value=[player1])

    with patch("src.core.localization_utils.ENTITY_TYPE_CRUD_MAP", {"player": mock_player_crud_instance}):
        with patch.object(localization_utils_logger, 'warning') as mock_logger_warning: # Assuming logger is named localization_utils_logger
            names_cache = await get_batch_localized_entity_names(mock_db_session, guild_id, entities_to_fetch, "en")

    assert names_cache.get(("player", 1)) == "Player Valid"
    assert len(names_cache) == 1 # Only the valid entity should be processed
    # Check that warnings were logged for invalid entries
    assert mock_logger_warning.call_count >= 3 # One for each clearly invalid dict structure, "not_a_dict" might not trigger same path
    # Example check for one of the warnings
    # mock_logger_warning.assert_any_call("Invalid entity reference found in batch: {'entity_type': 'player'}. Skipping.")
    # This specific assertion depends on exact logger message format.
    # For now, checking call_count is a good indicator.

# Need to import logger from the module to patch it correctly
from src.core import localization_utils as localization_utils_module
localization_utils_logger = localization_utils_module.logger
