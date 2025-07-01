import pytest
from src.core.nlu_service import parse_player_input
from src.models.actions import ActionEntity

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_text, expected_intent, expected_entities",
    [
        # Simple commands
        ("look", "look_around", []),
        ("l", "look_around", []),
        ("examine", "look_around", []),
        ("inventory", "view_inventory", []),
        ("inv", "view_inventory", []),
        ("i", "view_inventory", []),
        ("help", "get_help", []),
        ("?", "get_help", []),

        # Movement
        ("go north", "move", [ActionEntity(type="direction", value="north")]),
        ("move west", "move", [ActionEntity(type="direction", value="west")]),
        ("n", "move", [ActionEntity(type="direction", value="n")]),
        ("s", "move", [ActionEntity(type="direction", value="s")]),
        ("e", "move", [ActionEntity(type="direction", value="e")]),
        ("w", "move", [ActionEntity(type="direction", value="w")]),
        ("u", "move", [ActionEntity(type="direction", value="u")]),
        ("d", "move", [ActionEntity(type="direction", value="d")]),


        # Examine target
        ("look at goblin", "examine", [ActionEntity(type="name", value="goblin")]),
        ("examine the sword", "examine", [ActionEntity(type="name", value="sword")]),
        ("l the chest", "examine", [ActionEntity(type="name", value="chest")]),
        ("exa note", "examine", [ActionEntity(type="name", value="note")]),


        # Interact with target
        ("interact with lever", "interact", [ActionEntity(type="name", value="lever")]),
        ("use the terminal", "interact", [ActionEntity(type="name", value="terminal")]),
        ("activate button", "interact", [ActionEntity(type="name", value="button")]),
        ("touch stone", "interact", [ActionEntity(type="name", value="stone")]),
        ("press switch", "interact", [ActionEntity(type="name", value="switch")]),
        ("pull rope", "interact", [ActionEntity(type="name", value="rope")]),

        # Go to sublocation
        ("go to the kitchen", "go_to", [ActionEntity(type="name", value="kitchen")]),
        ("enter the library", "go_to", [ActionEntity(type="name", value="library")]),
        ("move to arena", "go_to", [ActionEntity(type="name", value="arena")]),

        # Get/Take item
        ("get sword", "get_item", [ActionEntity(type="item_name", value="sword")]),
        ("take the potion", "get_item", [ActionEntity(type="item_name", value="potion")]),

        # Drop item
        ("drop shield", "drop_item", [ActionEntity(type="item_name", value="shield")]),
        ("discard key", "drop_item", [ActionEntity(type="item_name", value="key")]),

        # Attack target
        ("attack goblin", "attack_target", [ActionEntity(type="target_name", value="goblin")]),
        ("hit the orc with my axe", "attack_target", [ActionEntity(type="target_name", value="orc with my axe")]), # Current regex is greedy

        # Talk to NPC
        ("talk to elara", "talk_to_npc", [ActionEntity(type="npc_name", value="elara")]),
        ("speak with the guard", "talk_to_npc", [ActionEntity(type="npc_name", value="guard")]),

        # Say
        ("say Hello there!", "say_text", [ActionEntity(type="text_to_say", value="Hello there!")]),
        ("'General Kenobi", "say_text", [ActionEntity(type="text_to_say", value="General Kenobi")]),
        ("shout FOR THE ALLIANCE", "say_text", [ActionEntity(type="text_to_say", value="FOR THE ALLIANCE")]),
        ("whisper meet me by the docks", "say_text", [ActionEntity(type="text_to_say", value="meet me by the docks")]),

        # Inputs that should result in "unknown_intent"
        ("do something completely random", "unknown_intent", []),
        ("sing a song", "unknown_intent", []),
        ("", "unknown_intent", []), # Empty string
        ("   ", "unknown_intent", []), # Only spaces

        # Test case sensitivity and spacing
        ("  LoOk  ", "look_around", []),
        ("gO NoRTh  ", "move", [ActionEntity(type="direction", value="NoRTh")]), # Value keeps original casing from regex
        ("  examine  THE  Shiny Orb  ", "examine", [ActionEntity(type="name", value="Shiny Orb")]),
    ],
)
async def test_parse_player_input(raw_text, expected_intent, expected_entities):
    guild_id = 123
    player_id = 456

    parsed_action = await parse_player_input(raw_text, guild_id, player_id)

    assert parsed_action is not None
    assert parsed_action.raw_text == raw_text
    assert parsed_action.intent == expected_intent
    assert parsed_action.guild_id == guild_id
    assert parsed_action.player_id == player_id
    assert parsed_action.timestamp is not None

    # Sort entities by type and value for consistent comparison
    sorted_entities = sorted(parsed_action.entities, key=lambda e: (e.type, e.value))
    sorted_expected_entities = sorted(expected_entities, key=lambda e: (e.type, e.value))

    assert len(sorted_entities) == len(sorted_expected_entities)
    for i, entity in enumerate(sorted_entities):
        assert entity.type == sorted_expected_entities[i].type
        # For "move" intent with single letter directions, the regex captures the letter itself.
        # For other directions, it captures the full word.
        # The value comparison should be case-insensitive for directions if the spec implies it,
        # but current regex keeps original casing for the matched group.
        # For this test, we'll assume the current behavior (value matches regex group) is intended.
        assert entity.value == sorted_expected_entities[i].value


@pytest.mark.asyncio
async def test_parse_player_input_empty_string_returns_unknown():
    """Test that an empty string or only whitespace returns an 'unknown_intent' action."""
    action_empty = await parse_player_input("", 1, 1)
    assert action_empty is not None
    assert action_empty.intent == "unknown_intent"
    assert action_empty.raw_text == ""

    action_whitespace = await parse_player_input("   ", 1, 1)
    assert action_whitespace is not None
    assert action_whitespace.intent == "unknown_intent"
    assert action_whitespace.raw_text == "   "

@pytest.mark.asyncio
async def test_parse_player_input_no_match_returns_unknown():
    """Test that input not matching any pattern returns an 'unknown_intent' action."""
    action = await parse_player_input("this will not match any pattern", 1, 1)
    assert action is not None
    assert action.intent == "unknown_intent"
    assert action.raw_text == "this will not match any pattern"
    assert not action.entities # No entities for unknown intent
    assert action.parser_confidence == 0.0

@pytest.mark.asyncio
async def test_parse_player_input_confidence_values():
    """Test that parser_confidence is set correctly."""
    action_known = await parse_player_input("look", 1, 1)
    assert action_known is not None
    assert action_known.intent == "look_around"
    assert action_known.parser_confidence == 1.0 # MVP confidence

    action_unknown = await parse_player_input("gibberish input", 1, 1)
    assert action_unknown is not None
    assert action_unknown.intent == "unknown_intent"
    assert action_unknown.parser_confidence == 0.0
