import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.relationship_system import _get_canonical_entity_pair, update_relationship
from src.models.enums import RelationshipEntityType, EventType
from src.models.relationship import Relationship # For type hinting and creating mock instances

# Test cases for _get_canonical_entity_pair
# Parameters: (e1_id, e1_type, e2_id, e2_type, expected_e1_id, expected_e1_type, expected_e2_id, expected_e2_type)
# Enum values for context: PLAYER="player", PARTY="party", GENERATED_NPC="generated_npc", GENERATED_FACTION="generated_faction"
# Sorted by string value: GENERATED_FACTION, GENERATED_NPC, PARTY, PLAYER
canonical_pair_test_cases = [
    # Type comparison leading
    # 1. PLAYER vs GENERATED_NPC: "generated_npc" < "player"
    (1, RelationshipEntityType.PLAYER, 2, RelationshipEntityType.GENERATED_NPC,
     2, RelationshipEntityType.GENERATED_NPC, 1, RelationshipEntityType.PLAYER),
    (2, RelationshipEntityType.GENERATED_NPC, 1, RelationshipEntityType.PLAYER,
     2, RelationshipEntityType.GENERATED_NPC, 1, RelationshipEntityType.PLAYER), # Already canonical

    # 2. PARTY vs GENERATED_FACTION: "generated_faction" < "party"
    (1, RelationshipEntityType.PARTY, 5, RelationshipEntityType.GENERATED_FACTION,
     5, RelationshipEntityType.GENERATED_FACTION, 1, RelationshipEntityType.PARTY),
    (5, RelationshipEntityType.GENERATED_FACTION, 1, RelationshipEntityType.PARTY,
     5, RelationshipEntityType.GENERATED_FACTION, 1, RelationshipEntityType.PARTY), # Already canonical

    # Same type, ID comparison
    (1, RelationshipEntityType.PLAYER, 10, RelationshipEntityType.PLAYER,
     1, RelationshipEntityType.PLAYER, 10, RelationshipEntityType.PLAYER),
    (10, RelationshipEntityType.PLAYER, 1, RelationshipEntityType.PLAYER,
     1, RelationshipEntityType.PLAYER, 10, RelationshipEntityType.PLAYER),

    (1, RelationshipEntityType.GENERATED_NPC, 1, RelationshipEntityType.GENERATED_NPC,
     1, RelationshipEntityType.GENERATED_NPC, 1, RelationshipEntityType.GENERATED_NPC), # Identical
]

@pytest.mark.parametrize(
    "e1_id, e1_type, e2_id, e2_type, exp_e1_id, exp_e1_type, exp_e2_id, exp_e2_type",
    canonical_pair_test_cases
)
def test_get_canonical_entity_pair(e1_id, e1_type, e2_id, e2_type, exp_e1_id, exp_e1_type, exp_e2_id, exp_e2_type):
    res_e1_id, res_e1_type, res_e2_id, res_e2_type = _get_canonical_entity_pair(
        e1_id, e1_type, e2_id, e2_type
    )
    assert res_e1_id == exp_e1_id
    assert res_e1_type == exp_e1_type
    assert res_e2_id == exp_e2_id
    assert res_e2_type == exp_e2_type

# --- Fixtures for update_relationship tests ---
@pytest.fixture
def mock_session() -> AsyncMock:
    """Provides a mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.rollback = AsyncMock()
    return session

@pytest.fixture
def mock_crud_relationship() -> MagicMock:
    """Provides a mock crud_relationship object."""
    mock_crud = MagicMock()
    mock_crud.get_relationship_between_entities = AsyncMock()
    mock_crud.update = AsyncMock()
    # We are not using crud_relationship.create directly anymore, but model constructor + session.add
    # mock_crud.create_with_guild_id = AsyncMock() # Not used directly
    return mock_crud

@pytest.fixture
def mock_get_rule() -> AsyncMock:
    """Provides a mock get_rule function."""
    return AsyncMock()

@pytest.fixture
def mock_log_event() -> AsyncMock:
    """Provides a mock log_event function."""
    return AsyncMock()

# --- Tests for update_relationship ---

@pytest.mark.asyncio
async def test_update_relationship_existing_relationship_updated(
    mock_session, mock_crud_relationship, mock_get_rule, mock_log_event
):
    # Arrange
    guild_id = 1
    entity_doing_id = 10
    entity_doing_type = RelationshipEntityType.PLAYER
    target_entity_id = 20
    target_entity_type = RelationshipEntityType.GENERATED_NPC # Corrected
    event_type = "COMBAT_VICTORY"
    event_log_id = 100

    # Canonical pair will depend on string comparison of enum values.
    # "player" vs "generated_npc". "generated_npc" comes first.
    # So canonical is (20, GENERATED_NPC, 10, PLAYER)
    expected_c_e1_id, expected_c_e1_type = 20, RelationshipEntityType.GENERATED_NPC
    expected_c_e2_id, expected_c_e2_type = 10, RelationshipEntityType.PLAYER


    rule = {"delta": 15, "min_val": -50, "max_val": 50, "relationship_type": "personal"}
    mock_get_rule.return_value = rule

    existing_rel = Relationship(
        id=1,
        guild_id=guild_id,
        entity1_id=expected_c_e1_id, entity1_type=expected_c_e1_type, # Stored canonically
        entity2_id=expected_c_e2_id, entity2_type=expected_c_e2_type,
        value=5,
        relationship_type="personal",
        source_log_id=90
    )
    mock_crud_relationship.get_relationship_between_entities.return_value = existing_rel

    updated_rel_sim = Relationship(
        id=1,
        guild_id=guild_id,
        entity1_id=expected_c_e1_id, entity1_type=expected_c_e1_type,
        entity2_id=expected_c_e2_id, entity2_type=expected_c_e2_type,
        value=20, # 5 + 15
        relationship_type="personal",
        source_log_id=event_log_id
    )
    mock_crud_relationship.update.return_value = updated_rel_sim


    with patch('src.core.relationship_system.crud_relationship', mock_crud_relationship), \
         patch('src.core.relationship_system.get_rule', mock_get_rule), \
         patch('src.core.relationship_system.log_event', mock_log_event):

        # Act
        await update_relationship(
            mock_session, guild_id, entity_doing_id, entity_doing_type,
            target_entity_id, target_entity_type, event_type, event_log_id
        )

        # Assert
        mock_get_rule.assert_called_once_with(mock_session, guild_id, f"relationship_rules:{event_type.upper()}")

        mock_crud_relationship.get_relationship_between_entities.assert_called_once_with(
            session=mock_session, guild_id=guild_id, # Changed db to session
            entity1_id=expected_c_e1_id, entity1_type=expected_c_e1_type,
            entity2_id=expected_c_e2_id, entity2_type=expected_c_e2_type
        )

        expected_new_value = 5 + 15 # 20
        mock_crud_relationship.update.assert_called_once()
        update_call_args = mock_crud_relationship.update.call_args
        assert update_call_args[1]['db_obj'] == existing_rel
        assert update_call_args[1]['obj_in'] == {"value": expected_new_value, "source_log_id": event_log_id}

        mock_log_event.assert_called_once()
        log_args = mock_log_event.call_args[1]
        assert log_args['guild_id'] == guild_id
        assert log_args['event_type'] == EventType.RELATIONSHIP_CHANGE.value
        assert log_args['details_json']['old_value'] == 5
        assert log_args['details_json']['new_value'] == expected_new_value
        assert log_args['details_json']['change_amount'] == 15
        assert log_args['details_json']['entity1_id'] == expected_c_e1_id
        assert log_args['details_json']['entity1_type'] == expected_c_e1_type.value
        assert log_args['details_json']['entity2_id'] == expected_c_e2_id
        assert log_args['details_json']['entity2_type'] == expected_c_e2_type.value
        assert log_args['details_json']['relationship_type'] == "personal" # from existing_rel
        assert log_args['details_json']['original_event_log_id'] == event_log_id


# More tests to be added:
# - test_update_relationship_new_relationship_created
# - test_update_relationship_rule_not_found
# - test_update_relationship_invalid_rule_structure
# - test_update_relationship_value_clamped_min
# - test_update_relationship_value_clamped_max
# - test_update_relationship_no_change_if_value_and_log_id_same
# - test_update_relationship_type_mismatch_warning (if desired to test logging)

# Placeholder for next test addition
async def test_placeholder():
    assert True
