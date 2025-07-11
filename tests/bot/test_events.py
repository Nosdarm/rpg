import sys
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession
import discord # Import discord for Guild type hint if needed, or use MagicMock
from discord.ext.commands import Bot as DiscordBot # Import Bot directly

# Import the Cog and the function to test
import backend.bot.events # Changed import style
# _ensure_guild_config_exists is a method of EventCog, so we test it via an instance.
# Alternatively, if it were a static/module-level function, we could import it directly.

from backend.models import GuildConfig

@pytest_asyncio.fixture
async def mock_session() -> AsyncSession:
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def mock_bot() -> MagicMock: # Using MagicMock for bot as its methods might not be async for this test
    return MagicMock(spec=DiscordBot) # Use the imported DiscordBot

@pytest.fixture
def event_cog(mock_bot: MagicMock) -> backend.bot.events.EventCog: # Use full path for type hint
    return backend.bot.events.EventCog(bot=mock_bot) # Use full path for instantiation

@pytest.mark.asyncio
@patch('backend.bot.events.guild_crud', new_callable=MagicMock) # Mock the entire crud module object
@patch('backend.bot.events.update_rule_config', new_callable=AsyncMock) # Mock the function
async def test_ensure_guild_config_exists_new_guild(
    mock_update_rule_config: AsyncMock,
    mock_guild_crud: MagicMock,
    event_cog: backend.bot.events.EventCog, # Corrected type hint
    mock_session: AsyncSession
):
    guild_id = 123
    guild_name = "Test Guild New"

    mock_guild_crud.get = AsyncMock(return_value=None) # Simulate guild not existing

    mock_created_guild_config = GuildConfig(id=guild_id, name=guild_name, main_language="en")
    mock_guild_crud.create = AsyncMock(return_value=mock_created_guild_config)

    # Debug prints
    print(f"Type of event_cog: {type(event_cog)}")
    print(f"Has attribute _ensure_guild_config_exists: {hasattr(event_cog, '_ensure_guild_config_exists')}")
    if not hasattr(event_cog, '_ensure_guild_config_exists'):
        print(f"Available attributes: {dir(event_cog)}")

    returned_config = await event_cog._ensure_guild_config_exists( # Reverted call
        session=mock_session, guild_id=guild_id, guild_name=guild_name
    )

    mock_guild_crud.get.assert_called_once_with(session=mock_session, id=guild_id)

    expected_obj_in = {"id": guild_id, "main_language": 'en', "name": guild_name}
    mock_guild_crud.create.assert_called_once_with(session=mock_session, obj_in=expected_obj_in)

    mock_update_rule_config.assert_called_once_with(
        session=mock_session, # Changed db to session
        guild_id=guild_id,
        key="guild_main_language",
        value={"language": "en"}
    )
    assert returned_config == mock_created_guild_config

@pytest.mark.asyncio
@patch('backend.bot.events.guild_crud', new_callable=MagicMock)
@patch('backend.bot.events.update_rule_config', new_callable=AsyncMock)
async def test_ensure_guild_config_exists_existing_guild(
    mock_update_rule_config: AsyncMock,
    mock_guild_crud: MagicMock,
    event_cog: backend.bot.events.EventCog, # Corrected type hint
    mock_session: AsyncSession
):
    guild_id = 456
    guild_name = "Test Guild Existing"

    mock_existing_guild_config = GuildConfig(id=guild_id, name=guild_name, main_language="en")
    mock_guild_crud.get = AsyncMock(return_value=mock_existing_guild_config)
    mock_guild_crud.create = AsyncMock() # Should not be called

    # Debug prints
    print(f"Type of event_cog (existing guild test): {type(event_cog)}")
    print(f"Has attribute _ensure_guild_config_exists (existing guild test): {hasattr(event_cog, '_ensure_guild_config_exists')}")
    if not hasattr(event_cog, '_ensure_guild_config_exists'):
        print(f"Available attributes (existing guild test): {dir(event_cog)}")

    returned_config = await event_cog._ensure_guild_config_exists( # Reverted call
        session=mock_session, guild_id=guild_id, guild_name=guild_name
    )

    mock_guild_crud.get.assert_called_once_with(session=mock_session, id=guild_id)
    mock_guild_crud.create.assert_not_called()
    mock_update_rule_config.assert_not_called()
    assert returned_config == mock_existing_guild_config
