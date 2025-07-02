# tests/core/test_localization_utils.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.localization_utils import get_localized_text, get_localized_entity_name
from src.models import Player, Location, GeneratedNpc, Item # Assuming these models exist

# Mock model instances
@pytest.fixture
def mock_player_instance():
    player = Player(id=1, guild_id=100, name="PlayerOne")
    player.name_i18n = {"en": "Player One", "ru": "Игрок Один"}
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
    ({"fr": "Bonjour"}, "en", "ru", "Bonjour"), # Fallback to first available if others fail
])
def test_get_localized_text(i18n_field, lang, fallback_lang, expected):
    assert get_localized_text(i18n_field, lang, fallback_lang) == expected

# --- Tests for get_localized_entity_name ---

# Patching the ENTITY_TYPE_GETTER_MAP directly for most tests
# We assume the lambda functions in the map correctly call their respective (mocked) getters.

@pytest.mark.asyncio
async def test_get_localized_entity_name_player_success(mock_session: AsyncSession, mock_player_instance: Player):
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_specific_player_getter = AsyncMock(return_value=mock_player_instance)
        mock_getter_map.get.return_value = mock_specific_player_getter

        name_en = await get_localized_entity_name(mock_session, 100, "player", 1, "en")
        assert name_en == "Player One"
        mock_specific_player_getter.assert_called_once_with(mock_session, 100, 1)
        mock_getter_map.get.assert_called_with("player")

        mock_specific_player_getter.reset_mock()
        name_ru = await get_localized_entity_name(mock_session, 100, "player", 1, "ru")
        assert name_ru == "Игрок Один"
        mock_specific_player_getter.assert_called_once_with(mock_session, 100, 1)

        mock_specific_player_getter.reset_mock()
        name_fr_fallback_en = await get_localized_entity_name(mock_session, 100, "player", 1, "fr", "en")
        assert name_fr_fallback_en == "Player One" # Falls back to English
        mock_specific_player_getter.assert_called_once_with(mock_session, 100, 1)

@pytest.mark.asyncio
async def test_get_localized_entity_name_location_success(mock_session: AsyncSession, mock_location_instance: Location):
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_specific_loc_getter = AsyncMock(return_value=mock_location_instance)
        mock_getter_map.get.return_value = mock_specific_loc_getter

        name_en = await get_localized_entity_name(mock_session, 100, "location", 1, "en")
        assert name_en == "Central Square"
        mock_specific_loc_getter.assert_called_once_with(mock_session, 100, 1)

@pytest.mark.asyncio
async def test_get_localized_entity_name_npc_success(mock_session: AsyncSession, mock_npc_instance: GeneratedNpc):
     with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_specific_npc_getter = AsyncMock(return_value=mock_npc_instance)
        mock_getter_map.get.return_value = mock_specific_npc_getter

        name_ru = await get_localized_entity_name(mock_session, 100, "npc", 1, "ru")
        assert name_ru == "Старый Иваныч"
        mock_specific_npc_getter.assert_called_once_with(mock_session, 100, 1)


@pytest.mark.asyncio
async def test_get_localized_entity_name_item_success(mock_session: AsyncSession, mock_item_instance: Item):
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_specific_item_getter = AsyncMock(return_value=mock_item_instance)
        mock_getter_map.get.return_value = mock_specific_item_getter

        name_en = await get_localized_entity_name(mock_session, 100, "item", 1, "en")
        assert name_en == "Rusty Sword"
        mock_specific_item_getter.assert_called_once_with(mock_session, 100, 1)

@pytest.mark.asyncio
async def test_get_localized_entity_name_entity_not_found(mock_session: AsyncSession):
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_getter_that_returns_none = AsyncMock(return_value=None)
        mock_getter_map.get.return_value = mock_getter_that_returns_none

        name = await get_localized_entity_name(mock_session, 100, "player", 99, "en")
        assert name == "[Player ID: 99 (Unknown)]"
        mock_getter_that_returns_none.assert_called_once_with(mock_session, 100, 99)

@pytest.mark.asyncio
async def test_get_localized_entity_name_unsupported_type(mock_session: AsyncSession):
    # No need to patch ENTITY_TYPE_GETTER_MAP if .get() will return None for the key
    with patch("src.core.localization_utils.ENTITY_TYPE_MODEL_MAP", new_callable=MagicMock) as mock_model_map:
        mock_model_map.get.return_value = None # Ensure model map also doesn't find it
        with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP", new_callable=MagicMock) as mock_getter_map:
            mock_getter_map.get.return_value = None # Ensure getter map doesn't find it

            name = await get_localized_entity_name(mock_session, 100, "dragon", 1, "en")
            assert name == "[dragon ID: 1]"
            mock_model_map.get.assert_called_with("dragon")
            mock_getter_map.get.assert_called_with("dragon")


@pytest.mark.asyncio
async def test_get_localized_entity_name_nameless_entity(mock_session: AsyncSession, mock_nameless_entity_instance: MagicMock):
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_getter = AsyncMock(return_value=mock_nameless_entity_instance)
        mock_getter_map.get.return_value = mock_getter

        name = await get_localized_entity_name(mock_session, 100, "player", 5, "en")
        assert name == "[Player ID: 5 (Nameless)]"

@pytest.mark.asyncio
async def test_get_localized_entity_name_plain_name_fallback(mock_session: AsyncSession, mock_plain_name_entity_instance: MagicMock):
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_getter = AsyncMock(return_value=mock_plain_name_entity_instance)
        mock_getter_map.get.return_value = mock_getter

        # Requested 'en', name_i18n only has 'es', so it should fallback to plain 'name'
        name = await get_localized_entity_name(mock_session, 100, "player", 6, "en")
        assert name == "Player Six Plain"

@pytest.mark.asyncio
async def test_get_localized_entity_name_getter_exception(mock_session: AsyncSession):
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP") as mock_getter_map:
        mock_getter_with_exception = AsyncMock(side_effect=Exception("Database connection failed"))
        mock_getter_map.get.return_value = mock_getter_with_exception

        name = await get_localized_entity_name(mock_session, 100, "item", 123, "en")
        assert name == "[Item ID: 123 (Error)]"

# Example of testing the generic fallback if ENTITY_TYPE_GETTER_MAP doesn't have the type
# but ENTITY_TYPE_MODEL_MAP does. This relies on the generic getter.
@pytest.mark.asyncio
@patch("src.core.localization_utils.get_entity_by_id_gino_style", new_callable=AsyncMock) # Mock the generic getter
async def test_get_localized_entity_name_generic_getter_fallback(
    mock_generic_getter: AsyncMock,
    mock_session: AsyncSession,
    mock_player_instance: Player # Use a real model instance
):
    # Ensure the specific getter is NOT found, but model IS found
    with patch("src.core.localization_utils.ENTITY_TYPE_GETTER_MAP", return_value={}) as mock_getter_map_empty, \
         patch("src.core.localization_utils.ENTITY_TYPE_MODEL_MAP", return_value={"player": Player}) as mock_model_map_with_player:

        # mock_getter_map_empty.get.return_value = None # This is implicitly true if map is empty or key missing
        # mock_model_map_with_player.get.return_value = Player # This is set by the patch

        mock_generic_getter.return_value = mock_player_instance

        name = await get_localized_entity_name(mock_session, 100, "player", 1, "en")
        assert name == "Player One"

        # Check that the specific getter map was checked and returned None (or key not found)
        # This is tricky to assert directly if the .get just returns None.
        # Instead, we check that the generic_getter was called.
        mock_generic_getter.assert_called_once_with(mock_session, Player, 1, guild_id=100)

        # Verify that the maps were indeed accessed
        # These assertions might be too fragile if the internal logic of get_localized_entity_name changes slightly
        # mock_getter_map_empty.get.assert_called_with("player")
        # mock_model_map_with_player.get.assert_called_with("player")

