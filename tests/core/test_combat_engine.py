import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import datetime
from typing import Generator, AsyncIterator, Any # Added Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.combat_engine import process_combat_action
from src.models.combat_outcomes import CombatActionResult
from src.models.combat_encounter import CombatEncounter
from src.models.player import Player
from src.models.generated_npc import GeneratedNpc
from src.models.enums import EventType, RelationshipEntityType, CombatStatus
# Assuming CheckResult is a Pydantic model or a dict for now
# from src.core.check_resolver import CheckResult


@pytest_asyncio.fixture()
async def mock_session() -> AsyncIterator[AsyncMock]: # Changed to AsyncIterator and yield
    yield AsyncMock(spec=AsyncSession)

@pytest.fixture() # Changed from @pytest_asyncio.fixture()
def mock_combat_encounter_crud_get() -> Generator[AsyncMock, Any, None]:
    with patch("src.core.crud.crud_combat_encounter.combat_encounter_crud.get", new_callable=AsyncMock) as mock_get:
        yield mock_get

@pytest.fixture() # Changed from @pytest_asyncio.fixture()
def mock_combat_encounter_crud_get_by_id_and_guild() -> Generator[AsyncMock, Any, None]: # Used by combat_engine's load
    with patch("src.core.crud.crud_combat_encounter.combat_encounter_crud.get_by_id_and_guild", new_callable=AsyncMock) as mock_get:
        yield mock_get


@pytest.fixture() # Changed from @pytest_asyncio.fixture()
def mock_player_crud_get_by_id_and_guild() -> Generator[AsyncMock, Any, None]:
    with patch("src.core.crud.player_crud.get_by_id_and_guild", new_callable=AsyncMock) as mock_get:
        yield mock_get

@pytest.fixture() # Changed from @pytest_asyncio.fixture()
def mock_npc_crud_get_by_id_and_guild() -> Generator[AsyncMock, Any, None]:
    with patch("src.core.crud.crud_npc.npc_crud.get_by_id_and_guild", new_callable=AsyncMock) as mock_get:
        yield mock_get

@pytest.fixture() # Changed from @pytest_asyncio.fixture()
def mock_get_rule() -> Generator[AsyncMock, Any, None]:
    with patch("src.core.combat_engine.get_rule", new_callable=AsyncMock) as mock_fn:
        # Default mock behavior: return the key itself or a default value
        mock_fn.side_effect = lambda session, guild_id, key, default=None: default if default is not None else key
        yield mock_fn

@pytest.fixture() # Changed from @pytest_asyncio.fixture()
def mock_resolve_check() -> Generator[AsyncMock, Any, None]:
    with patch("src.core.combat_engine.resolve_check", new_callable=AsyncMock) as mock_fn:
        # Default: successful check
        mock_fn.return_value = MagicMock(success=True, roll=15, dc=10, critical_success=False, critical_failure=False, total_roll_value=15)
        yield mock_fn

@pytest.fixture() # Changed from @pytest_asyncio.fixture()
def mock_log_event() -> Generator[AsyncMock, Any, None]:
    with patch("src.core.combat_engine.log_event", new_callable=AsyncMock) as mock_fn:
        yield mock_fn

# --- Test Data ---
GUILD_ID = 1
COMBAT_ID = 10
PLAYER_ID = 100
NPC_ID = 200
LOCATION_ID = 300

@pytest.mark.asyncio
async def test_process_combat_action_attack_hit_successful(
    mock_session,
    mock_combat_encounter_crud_get, # Patching the generic get
    mock_player_crud_get_by_id_and_guild,
    mock_npc_crud_get_by_id_and_guild,
    mock_get_rule,
    mock_resolve_check, # Using the new CheckResult-like mock
    mock_log_event
):
    player = Player(id=PLAYER_ID, name="Hero", guild_id=GUILD_ID, current_hp=50)
    npc = GeneratedNpc(
        id=NPC_ID,
        name_i18n={"en": "Goblin"}, # name_i18n is non-nullable and defaults to {}
        guild_id=GUILD_ID,
        properties_json={"stats": {"current_hp": 30}}
    )

    combat_encounter = CombatEncounter(
        id=COMBAT_ID,
        guild_id=GUILD_ID,
        location_id=LOCATION_ID,
        status=CombatStatus.ACTIVE,
        participants_json={
            "entities": [
                {"id": PLAYER_ID, "type": "player", "current_hp": 50, "attack_power": 12},
                {"id": NPC_ID, "type": "generated_npc", "current_hp": 30, "defense": 3}
            ]
        },
        combat_log_json={"entries": []}, # Initialized, not None
        rules_config_snapshot_json={}
    )
    mock_combat_encounter_crud_get.return_value = combat_encounter
    mock_player_crud_get_by_id_and_guild.return_value = player
    mock_npc_crud_get_by_id_and_guild.return_value = npc

    action_data = {"action_type": "attack", "target_id": NPC_ID}

    result = await process_combat_action(
        guild_id=GUILD_ID,
        session=mock_session,
        combat_instance_id=COMBAT_ID,
        actor_id=PLAYER_ID,
        actor_type_str=RelationshipEntityType.PLAYER.value,
        action_data=action_data
    )

    assert result.success is True
    assert result.action_type == "attack"
    assert result.actor_id == PLAYER_ID
    assert result.target_id == NPC_ID
    assert result.damage_dealt == 5 # Current fixed damage in MVP

    assert result.description_i18n is not None # Check before subscripting
    expected_npc_name = npc.name_i18n.get("en", "Unknown Target") # npc.name_i18n is guaranteed to be a dict
    assert result.description_i18n["en"] == f"{player.name} attacks {expected_npc_name} for {result.damage_dealt} damage!"

    assert combat_encounter.participants_json is not None # Check before subscripting
    updated_npc_data = next(p for p in combat_encounter.participants_json["entities"] if p["id"] == NPC_ID)
    assert updated_npc_data["current_hp"] == 30 - result.damage_dealt

    assert combat_encounter.combat_log_json is not None # Check before subscripting
    assert len(combat_encounter.combat_log_json["entries"]) == 1
    log_entry = combat_encounter.combat_log_json["entries"][0]
    assert log_entry["actor_id"] == PLAYER_ID
    assert log_entry["action_type"] == "attack"
    assert log_entry["damage_dealt"] == result.damage_dealt

    mock_log_event.assert_called_once()
    call_args_list = mock_log_event.call_args_list
    assert len(call_args_list) == 1
    call_args = call_args_list[0].kwargs # Use .kwargs to access keyword arguments

    assert call_args["guild_id"] == GUILD_ID
    assert call_args["event_type"] == EventType.COMBAT_ACTION.name # Compare with the string name

    details_json = call_args["details_json"]
    assert details_json is not None
    assert details_json["combat_id"] == COMBAT_ID

    action_result_in_log = details_json["action_result"]
    assert action_result_in_log is not None
    assert action_result_in_log["damage_dealt"] == result.damage_dealt

@pytest.mark.asyncio
async def test_process_combat_action_attack_miss(
    mock_session, mock_combat_encounter_crud_get, mock_player_crud_get_by_id_and_guild,
    mock_npc_crud_get_by_id_and_guild, mock_get_rule, mock_resolve_check, mock_log_event
):
    player = Player(id=PLAYER_ID, name="Hero", guild_id=GUILD_ID, current_hp=50)
    npc = GeneratedNpc(
        id=NPC_ID,
        name_i18n={"en": "Goblin"},
        guild_id=GUILD_ID,
        properties_json={"stats": {"current_hp": 30}}
    )
    combat_encounter = CombatEncounter(
        id=COMBAT_ID, guild_id=GUILD_ID, status=CombatStatus.ACTIVE,
        participants_json={"entities": [
            {"id": PLAYER_ID, "type": "player", "current_hp": 50},
            {"id": NPC_ID, "type": "generated_npc", "current_hp": 30}
        ]},
        combat_log_json={"entries": []} # Initialized
    )
    mock_combat_encounter_crud_get.return_value = combat_encounter
    mock_player_crud_get_by_id_and_guild.return_value = player
    mock_npc_crud_get_by_id_and_guild.return_value = npc
    mock_resolve_check.return_value = MagicMock(success=False, roll=5, dc=10, total_roll_value=5)
    # Test logic for miss... (currently this test is just a pass through)
    pass


@pytest.mark.asyncio
async def test_process_combat_action_combat_not_found(
    mock_session, mock_combat_encounter_crud_get
):
    mock_combat_encounter_crud_get.return_value = None
    action_data = {"action_type": "attack", "target_id": NPC_ID}
    result = await process_combat_action(GUILD_ID, mock_session, COMBAT_ID, PLAYER_ID, "player", action_data)
    assert result.success is False
    assert result.description_i18n is not None # Check before subscripting
    assert result.description_i18n["en"] == "Combat encounter not found."

@pytest.mark.asyncio
async def test_process_combat_action_actor_not_found_in_db(
    mock_session, mock_combat_encounter_crud_get, mock_player_crud_get_by_id_and_guild
):
    # Ensure combat_encounter has non-None dicts for json fields
    combat_encounter = CombatEncounter(
        id=COMBAT_ID, guild_id=GUILD_ID, status=CombatStatus.ACTIVE,
        participants_json={"entities": []},
        combat_log_json={"entries": []}
    )
    mock_combat_encounter_crud_get.return_value = combat_encounter
    mock_player_crud_get_by_id_and_guild.return_value = None # Actor not in DB

    action_data = {"action_type": "attack", "target_id": NPC_ID}
    result = await process_combat_action(GUILD_ID, mock_session, COMBAT_ID, PLAYER_ID, "player", action_data)
    assert result.success is False
    assert result.description_i18n is not None # Check before subscripting
    assert result.description_i18n["en"] == "Actor not found."

@pytest.mark.asyncio
async def test_process_combat_action_actor_not_in_participants_json(
    mock_session, mock_combat_encounter_crud_get, mock_player_crud_get_by_id_and_guild
):
    player = Player(id=PLAYER_ID, name="Hero", guild_id=GUILD_ID)
    combat_encounter = CombatEncounter(
        id=COMBAT_ID, guild_id=GUILD_ID, status=CombatStatus.ACTIVE,
        participants_json={"entities": [{"id": NPC_ID, "type": "generated_npc", "current_hp": 30}]}, # Player missing
        combat_log_json={"entries": []} # Initialized
    )
    mock_combat_encounter_crud_get.return_value = combat_encounter
    mock_player_crud_get_by_id_and_guild.return_value = player

    action_data = {"action_type": "attack", "target_id": NPC_ID}
    result = await process_combat_action(GUILD_ID, mock_session, COMBAT_ID, PLAYER_ID, "player", action_data)
    assert result.success is False
    assert result.description_i18n is not None # Check before subscripting
    assert result.description_i18n["en"] == "Actor not found in combat."


@pytest.mark.asyncio
async def test_process_combat_action_target_not_in_participants_json(
    mock_session, mock_combat_encounter_crud_get, mock_player_crud_get_by_id_and_guild,
    mock_npc_crud_get_by_id_and_guild
):
    player = Player(id=PLAYER_ID, name="Hero", guild_id=GUILD_ID)
    npc_target_in_db = GeneratedNpc(
        id=NPC_ID,
        name_i18n={"en": "GoblinTarget"},
        guild_id=GUILD_ID,
        properties_json={"stats": {"current_hp": 10}}
    )

    combat_encounter = CombatEncounter(
        id=COMBAT_ID, guild_id=GUILD_ID, status=CombatStatus.ACTIVE,
        participants_json={"entities": [{"id": PLAYER_ID, "type": "player", "current_hp": 50}]}, # Target NPC missing
        combat_log_json={"entries": []} # Initialized
    )
    mock_combat_encounter_crud_get.return_value = combat_encounter
    mock_player_crud_get_by_id_and_guild.return_value = player
    mock_npc_crud_get_by_id_and_guild.return_value = npc_target_in_db

    action_data = {"action_type": "attack", "target_id": NPC_ID}
    result = await process_combat_action(GUILD_ID, mock_session, COMBAT_ID, PLAYER_ID, "player", action_data)

    assert result.success is False
    assert result.description_i18n is not None # Check before subscripting
    assert result.description_i18n["en"] == "Target not found in combat."


@pytest.mark.asyncio
async def test_process_combat_action_unknown_action_type(
    mock_session, mock_combat_encounter_crud_get, mock_player_crud_get_by_id_and_guild
):
    player = Player(id=PLAYER_ID, name="Hero", guild_id=GUILD_ID)
    combat_encounter = CombatEncounter(
        id=COMBAT_ID, guild_id=GUILD_ID, status=CombatStatus.ACTIVE,
        participants_json={"entities": [{"id": PLAYER_ID, "type": "player", "current_hp": 50}]},
        combat_log_json={"entries": []} # Initialized
    )
    mock_combat_encounter_crud_get.return_value = combat_encounter
    mock_player_crud_get_by_id_and_guild.return_value = player

    action_data = {"action_type": "dance"}
    result = await process_combat_action(GUILD_ID, mock_session, COMBAT_ID, PLAYER_ID, "player", action_data)
    assert result.success is False
    assert result.action_type == "dance"
    assert result.description_i18n is not None # Check before subscripting
    assert result.description_i18n["en"] == "Unknown action: dance"

# TODO: Add tests for:
# - Critical hit scenario (when engine supports it via resolve_check)
# - Action with status effect applied (when engine supports it)
# - Action with resource cost (when engine supports it)
# - Different actor types (NPC attacking player)
# - Rules loaded from snapshot vs RuleConfig
# - Test case where target_entity is not found in DB but is in participants_json (warning logged)

# Note on the "miss" test:
# The current `combat_engine.py` has a placeholder `simulated_check_success = True`.
# To properly test a "miss" scenario driven by `resolve_check`, the engine needs to be updated
# to use the `success` attribute from the `CheckResult` object returned by `resolve_check`.
# Once that's done, `mock_resolve_check.return_value = MagicMock(success=False, ...)`
# would correctly simulate a miss and the corresponding `else` block in the engine would be covered.
# The current `test_process_combat_action_attack_miss` is a pass-through due to this.
# A more robust test for "miss" could be written once the engine logic is updated.
