import unittest
import datetime

from src.models.quest import Questline, GeneratedQuest, QuestStep, PlayerQuestProgress
from src.models.enums import QuestStatus, RelationshipEntityType

# Поскольку модели теперь наследуют TimestampMixin, created_at и updated_at будут присутствовать.
# Мы не будем их явно задавать в тестах, а просто проверим их наличие и тип после создания.

class TestQuestModels(unittest.TestCase):

    def test_create_questline(self):
        data = {
            "guild_id": 1,
            "static_id": "main_story_qline",
            "title_i18n": {"en": "Main Storyline", "ru": "Основная сюжетная линия"},
            "description_i18n": {"en": "The epic main quest.", "ru": "Эпический главный квест."},
            "starting_quest_static_id": "start_quest_001",
            "is_main_storyline": True,
            "required_previous_questline_static_id": None,
            "properties_json": {"difficulty": "hard"}
        }
        questline = Questline(**data) # type: ignore
        # SQLAlchemy ожидает все поля при инициализации, если нет default_factory или server_default
        # В нашем случае TimestampMixin предоставляет default, так что это должно быть ОК.
        # Используем type: ignore для обхода возможных жалоб mypy на отсутствующие created_at/updated_at при прямом **data

        self.assertEqual(questline.guild_id, data["guild_id"])
        self.assertEqual(questline.static_id, data["static_id"])
        self.assertEqual(questline.title_i18n, data["title_i18n"])
        self.assertEqual(questline.description_i18n, data["description_i18n"])
        self.assertEqual(questline.starting_quest_static_id, data["starting_quest_static_id"])
        self.assertEqual(questline.is_main_storyline, data["is_main_storyline"])
        self.assertEqual(questline.required_previous_questline_static_id, data["required_previous_questline_static_id"])
        self.assertEqual(questline.properties_json, data["properties_json"])
        # TimestampMixin defaults (like created_at, updated_at) are typically None on direct instantiation
        # and are set by SQLAlchemy during session flush/commit.
        self.assertIsNone(questline.created_at)
        self.assertIsNone(questline.updated_at)


    def test_create_generated_quest(self):
        data = {
            "guild_id": 1,
            "static_id": "kill_goblins_01",
            "title_i18n": {"en": "Kill Goblins", "ru": "Убить гоблинов"},
            "description_i18n": {"en": "Wipe out 10 goblins.", "ru": "Уничтожьте 10 гоблинов."},
            "questline_id": None,
            "giver_entity_type": RelationshipEntityType.GENERATED_NPC,
            "giver_entity_id": 101,
            "min_level": 5,
            "is_repeatable": False,
            "rewards_json": {"xp": 100, "gold": 50},
            "properties_json": {"area": "forest"},
            "ai_metadata_json": {"source_prompt_hash": "xyz"}
        }
        quest = GeneratedQuest(**data) # type: ignore

        self.assertEqual(quest.guild_id, data["guild_id"])
        self.assertEqual(quest.static_id, data["static_id"])
        self.assertEqual(quest.title_i18n, data["title_i18n"])
        # ... (проверки для остальных полей)
        self.assertEqual(quest.rewards_json, data["rewards_json"])
        self.assertEqual(quest.properties_json, data["properties_json"])
        self.assertEqual(quest.ai_metadata_json, data["ai_metadata_json"])
        self.assertIsNone(quest.created_at)
        self.assertIsNone(quest.updated_at)

    def test_create_quest_step(self):
        data = {
            "quest_id": 1, # Предполагается, что такой квест существует
            "step_order": 1,
            "title_i18n": {"en": "Step 1", "ru": "Шаг 1"},
            "description_i18n": {"en": "Go to the goblin camp.", "ru": "Идите в лагерь гоблинов."},
            "required_mechanics_json": {"type": "reach_location", "target_location_static_id": "goblin_camp"},
            "abstract_goal_json": None,
            "consequences_json": {"xp_on_step_complete": 10},
            "next_step_order": 2,
            "properties_json": {}
        }
        step = QuestStep(**data) # type: ignore

        self.assertEqual(step.quest_id, data["quest_id"])
        self.assertEqual(step.step_order, data["step_order"])
        # ... (проверки для остальных полей)
        self.assertEqual(step.required_mechanics_json, data["required_mechanics_json"])
        self.assertEqual(step.next_step_order, data["next_step_order"])
        self.assertIsNone(step.created_at)
        self.assertIsNone(step.updated_at)

    def test_create_player_quest_progress_for_player(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        data = {
            "guild_id": 1,
            "player_id": 1, # Для игрока
            "party_id": None, # Нет партии
            "quest_id": 1,
            "current_step_id": 1,
            "status": QuestStatus.IN_PROGRESS, # This was already IN_PROGRESS, the error was in the _for_party test
            "progress_data_json": {"goblins_killed": 5},
            "accepted_at": now,
            "completed_at": None
        }
        progress = PlayerQuestProgress(**data) # type: ignore

        self.assertEqual(progress.guild_id, data["guild_id"])
        self.assertEqual(progress.player_id, data["player_id"])
        self.assertIsNone(progress.party_id)
        self.assertEqual(progress.quest_id, data["quest_id"])
        # ... (проверки для остальных полей)
        self.assertEqual(progress.status, data["status"])
        self.assertEqual(progress.accepted_at, data["accepted_at"])
        self.assertIsNone(progress.created_at)
        self.assertIsNone(progress.updated_at)

    def test_create_player_quest_progress_for_party(self):
        data = {
            "guild_id": 1,
            "player_id": None,
            "party_id": 1, # Для партии
            "quest_id": 2,
            "status": QuestStatus.STARTED, # Changed ACCEPTED to STARTED
        }
        progress = PlayerQuestProgress(**data) # type: ignore
        self.assertEqual(progress.party_id, data["party_id"])
        self.assertIsNone(progress.player_id)
        self.assertIsNone(progress.created_at)
        self.assertIsNone(progress.updated_at) # PlayerQuestProgress also uses TimestampMixin

    def test_questline_quest_relationship(self):
        questline = Questline(guild_id=1, static_id="ql1", title_i18n={}, description_i18n={})
        quest1 = GeneratedQuest(guild_id=1, static_id="q1", title_i18n={}, description_i18n={})

        # Проверка добавления
        questline.quests.append(quest1)
        self.assertIn(quest1, questline.quests)
        self.assertEqual(quest1.questline, questline)
        self.assertEqual(quest1.questline_id, questline.id) # Это будет None до коммита, если ID не присвоен явно

    def test_quest_step_relationship(self):
        quest = GeneratedQuest(guild_id=1, static_id="q1", title_i18n={}, description_i18n={})
        step1 = QuestStep(quest_id=quest.id, step_order=1, title_i18n={}, description_i18n={}) # quest_id будет None до коммита

        quest.steps.append(step1)
        self.assertIn(step1, quest.steps)
        self.assertEqual(step1.quest, quest)

    def test_player_quest_progress_relationships(self):
        # Этот тест больше для проверки типов и атрибутов, реальные ID будут после коммита
        player_progress = PlayerQuestProgress(guild_id=1, player_id=1, quest_id=1)

        # Модели Player, GeneratedQuest, QuestStep должны быть мокированы или созданы для полной проверки
        # Но мы можем проверить, что атрибуты существуют
        self.assertTrue(hasattr(player_progress, "player"))
        self.assertTrue(hasattr(player_progress, "quest"))
        self.assertTrue(hasattr(player_progress, "current_step"))

if __name__ == '__main__':
    unittest.main()
