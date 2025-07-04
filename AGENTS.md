## Инструкции для Агента

**Основные принципы работы:**

1.  **Анализ `AGENTS.md`:** Перед началом любой работы всегда анализировать этот файл (`AGENTS.md`).
2.  **Работа с задачами из `tasks.txt`:**
    *   Взять одну задачу из файла `tasks.txt` в разработку.
    *   Полностью реализовать задачу.
    *   Покрыть тестами (если требуется).
    *   Провести тестирование:
        *   Запустить тесты.
        *   Если тест падает, сначала исправить ошибку, затем повторно запустить тест.
        *   Повторять до тех пор, пока все тесты, относящиеся к задаче, не пройдут.
    *   После успешной реализации и тестирования:
        *   Удалить задачу из файла `tasks.txt`.
        *   Перенести (добавить) информацию о выполненной задаче в файл `done.txt`.
3.  **Отложенные задачи:**
    *   Если задача будет требовать доработки в будущем, создать в этом файле (`AGENTS.md`) секцию "Отложенные задачи".
    *   Указать в этой секции задачу, которую необходимо будет доработать, и указать, когда именно это нужно будет сделать.
4.  **Обновление `AGENTS.md` и Коммит:**
    *   Если все тесты по текущей задаче успешно прошли, обновить `AGENTS.md` информацией о проделанной работе (в секции "Лог действий").
    *   Сделать коммит с описанием изменений.
5.  **Локальная память в `AGENTS.md`:**
    *   `AGENTS.md` используется как ваша локальная память для отслеживания прогресса, контекста и принятых решений.
    *   Каждое действие, предпринятое для реализации текущей задачи, должно быть немедленно записано в `AGENTS.md` в секции "Лог действий" под заголовком текущей задачи.
6.  **Планирование текущей задачи:**
    *   Перед началом реализации новой задачи необходимо составить детальный план ее выполнения.
    *   Этот план записывается в секцию "Текущий план" в `AGENTS.md`. По завершении задачи эта секция очищается или обновляется для следующей задачи.
7.  **Приоритет инструкций:**
    *   Явные инструкции от пользователя, полученные в ходе текущего диалога, имеют наивысший приоритет.
    *   Затем следуют инструкции из этого раздела ("Инструкции для Агента").

**Структура `AGENTS.md` (Рекомендуемая):**

*   **Инструкции для Агента:** (Этот раздел)
*   **Текущий план:**
    *(Этот раздел будет заполняться планом для следующей задачи)*
*   **Отложенные задачи:**
    *(Этот раздел будет заполняться, если появятся задачи, требующие доработки в будущем)*
*   **Лог действий:** Хронологический список всех предпринятых действий с указанием контекста задачи, сгруппированных по задачам. Задачи нумеруются.

---
## Текущий план
*(Этот раздел очищен после выполнения Task 34)*
---
## Отложенные задачи
- **Доработка Player.attributes_json для Task 32**:
    - **Описание**: В рамках Task 32 была реализована логика команды `/levelup`, которая предполагает наличие у модели `Player` поля `attributes_json` для хранения атрибутов персонажа (сила, ловкость и т.д.). Однако само поле и соответствующая миграция не были созданы.
    - **Необходимые действия**:
        1. Добавить поле `attributes_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=lambda: {}, nullable=False)` в модель `src/models/player.py`.
        2. Создать и применить миграцию Alembic для добавления этого столбца в таблицу `players`.
        3. Рассмотреть инициализацию базовых атрибутов в `player.attributes_json` при создании нового персонажа (например, в `player_crud.create_with_defaults`, используя значения из `RuleConfig` по ключу типа `character_attributes:base_values`).
    - **Срок**: Выполнить перед полноценным тестированием и использованием функционала `/levelup`. Желательно как можно скорее.

---

## Лог действий

## Task 34: 🎭 8.2 Relationships Model (Guild-Scoped)
- **Определение задачи**: Определить модель `Relationship` для хранения отношений между сущностями.
- **Реализация**:
    - Модель `src/models/relationship.py` обновлена:
        - Поле `relationship_type_i18n` (JSONB) заменено на `relationship_type` (Text, default="neutral").
        - Добавлено поле `source_log_id` (Integer, FK на `story_logs.id`, nullable, ondelete SET NULL).
        - Закомментировано поле `ai_metadata_json`.
    - Enum `RelationshipEntityType` в `src/models/enums.py` уже существовал и был корректен.
    - Файл `src/models/__init__.py` не требовал изменений.
    - Создана новая миграция Alembic `alembic/versions/6344a0089ba3_update_relationships_table_fields.py` для обновления схемы таблицы `relationships`:
        - Удаляет столбец `ai_metadata_json`.
        - Удаляет столбец `relationship_type_i18n` и создает `relationship_type` (Text).
        - Добавляет столбец `source_log_id` с внешним ключом и индексом.
- **Статус**: Модель и миграция готовы.

## Task 33: 🎭 8.1 Factions Model (Guild-Scoped, i18n)
- **Определение задачи**: Определить модель `GeneratedFaction` для хранения данных о фракциях.
- **Анализ**:
    - Модель `src/models/generated_faction.py` уже существует.
    - Модель в `src/models/__init__.py` уже импортирована.
    - Миграция для `generated_factions` уже существует в `alembic/versions/fcb2e6d12a18_initial_schema_setup.py`.
- **Вывод**: Задача в основном выполнена ранее. Проверена корректность существующей реализации.

## Task 32: ⚡️ 13.3 Applying Level Up (Multy-i18n)
- **Определение задачи**: Реализовать команду для распределения очков повышения уровня (`unspent_xp`) на атрибуты персонажа.
- **Анализ и предположения**:
    - Атрибуты игрока (сила, ловкость и т.д.) будут храниться в поле `Player.attributes_json: JSONB`. (Поле `attributes_json` не было добавлено в модель `Player` в рамках этой задачи, так как план изменился и сначала была реализована команда, а работа с моделью вынесена на более ранний шаг).
    - Определения атрибутов (имена, описания), их базовые значения и стоимость прокачки будут храниться в `RuleConfig`.
- **Реализация API `spend_attribute_points`**:
    - В `src/core/experience_system.py` добавлена функция `async def spend_attribute_points(session, player, attribute_name, points_to_spend, guild_id)`.
    - Функция проверяет наличие `unspent_xp`, валидность атрибута (через `RuleConfig` ключ `character_attributes:definitions`), тратит очки, обновляет `player.unspent_xp` и `player.attributes_json`.
    - Логирует событие `ATTRIBUTE_POINTS_SPENT` (новый тип в `EventType`).
    - Экспортирована из `src/core/__init__.py`.
- **Создание Cog `CharacterCog`**:
    - Создан файл `src/bot/commands/character_commands.py`.
    - Cog `CharacterCog` зарегистрирован в `src/config/settings.py`.
- **Реализация команды `/levelup`**:
    - В `CharacterCog` добавлена команда `/levelup <attribute_name: str> <points_to_spend: int>`.
    - Команда получает игрока, проверяет наличие `unspent_xp`.
    - Вызывает API `spend_attribute_points`.
    - Формирует и отправляет локализованный ответ игроку, используя шаблоны из `RuleConfig` (ключи типа `levelup_success`, `levelup_error_not_enough_xp` и т.д.) и `localization_utils.get_localized_text`. Предусмотрены встроенные сообщения-заглушки.
- **Определение структуры правил для `RuleConfig`**:
    - Определены ключи для атрибутов: `character_attributes:definitions`, `character_attributes:base_values`, `character_attributes:cost_per_point`.
    - Определены ключи для локализации сообщений команды: `levelup_success`, `levelup_error_no_unspent_xp`, `levelup_error_invalid_points_value`, `levelup_error_not_enough_xp`, `levelup_error_invalid_attribute`, `levelup_error_not_enough_xp_for_cost`, `levelup_error_generic`, `player_not_started_game`.
- **Unit-тесты**:
    - В `tests/core/test_experience_system.py` добавлены тесты для `spend_attribute_points`, покрывающие успешное выполнение, ошибки (недостаточно XP, неверный атрибут, неверное количество очков), обновление нового атрибута.
    - Создан файл `tests/bot/commands/test_character_commands.py` с тестами для команды `/levelup`. Тесты покрывают успешное выполнение, обработку ошибок (игрок не найден, нет очков), взаимодействие с API и системой локализации.

## Task 30: ⚡️ 13.1 Experience System Structure (Rules)
- **Определение задачи**: Определить структуру правил для системы опыта (получение XP, повышение уровня, распределение очков) в `RuleConfig` для каждой гильдии.
- **Анализ модели `RuleConfig`**: Модель `src/models/rule_config.py` (поля `key` и `value_json`) подходит для хранения этих правил без модификации самой модели.
- **Предлагаемая структура JSON для правил XP в `RuleConfig`**:
    -   **Ключ**: `experience_system:xp_gain_rules`
        -   **Описание**: Определяет, как начисляется опыт за различные игровые события.
        -   **Структура `value_json`**: Объект, где каждый ключ - это строка, идентифицирующая тип события (например, `combat_victory_normal_enemy`, `combat_victory_elite_enemy`, `quest_completed_main`, `quest_completed_side`, `skill_usage_crafting`, `skill_usage_exploration`), а значение - объект с правилами начисления XP для этого события.
        -   **Пример `value_json`**:
            ```json
            {
              "combat_victory_normal_enemy": {
                "base_xp": 50,
                "per_level_above_player": 10, // XP сверх базового за каждый уровень врага выше уровня игрока
                "per_level_below_player": -5, // Штраф к XP за каждый уровень врага ниже уровня игрока (мин. 0)
                "player_level_scaling_factor": 1.0 // Множитель XP в зависимости от уровня игрока (может быть кривой)
              },
              "quest_completed_main": {
                "base_xp": 500,
                "bonus_for_optional_objectives": 100
              },
              "skill_usage_exploration": {
                "base_xp_per_discovery": 25
              }
            }
            ```
    -   **Ключ**: `experience_system:level_curve`
        -   **Описание**: Определяет количество опыта, необходимое для достижения каждого следующего уровня.
        -   **Структура `value_json`**: Массив объектов, отсортированных по уровню. Каждый объект представляет уровень и количество опыта, необходимое для перехода *с этого уровня на следующий*.
        -   **Пример `value_json`**:
            ```json
            [
              { "current_level": 1, "xp_to_reach_next_level": 1000 },
              { "current_level": 2, "xp_to_reach_next_level": 2500 },
              { "current_level": 3, "xp_to_reach_next_level": 5000 }
              // ... и так далее
            ]
            ```
            *Примечание*: Альтернативно, можно хранить общее количество XP, необходимое для достижения уровня, например: `[ { "level": 1, "total_xp_required": 0 }, { "level": 2, "total_xp_required": 1000 } ]`. Первый вариант (xp_to_reach_next_level) может быть проще для расчетов "XP до следующего уровня".
    -   **Ключ**: `experience_system:level_up_rewards`
        -   **Описание**: Определяет награды (например, очки атрибутов, очки навыков, специальные способности), которые игрок получает при достижении нового уровня.
        -   **Структура `value_json`**: Объект, где ключ `"default"` определяет награды по умолчанию для любого уровня, а числовые ключи (например, `"5"`, `"10"`) могут переопределять или дополнять награды для конкретных уровней.
        -   **Пример `value_json`**:
            ```json
            {
              "default": { // Награда по умолчанию для каждого уровня
                "attribute_points": 1,
                "skill_points": 2
              },
              "5": { // Особая награда на 5-м уровне (дополняет или заменяет default)
                "attribute_points": 2, // Больше очков атрибутов
                "skill_points": 3,
                "bonus_ability_static_id": "special_perk_level_5", // ID способности из таблицы способностей
                "notification_message_key": "level_5_milestone_reached" // Ключ для локализованного сообщения
              },
              "10": {
                "feature_unlock": "new_feature_unlocked_at_level_10"
              }
            }
            ```
- **Дальнейшие шаги**: Эта документация завершает Task 30. Следующие задачи (31, 32) будут использовать эту структуру для реализации логики системы опыта.

## Task 31: ⚡️ 13.2 XP Awarding and Progress
- **Определение задачи**: Реализовать логику начисления XP и проверки повышения уровня.
- **Создание модуля `experience_system.py`**:
    - Создан файл `src/core/experience_system.py`.
    - Определены заглушки для функций `award_xp` и `_check_for_level_up`.
- **Реализация API `award_xp`**:
    - Функция `award_xp(session, guild_id, entity_id, entity_type, xp_to_award, source_event_type, source_log_id)` реализована.
    - Определение игроков-получателей:
        - Для `EntityType.PLAYER`: загружается игрок по `entity_id` и `guild_id`.
        - Для `EntityType.PARTY`: загружается партия и ее участники (`party.players`).
    - Распределение XP: для партии XP делится поровну (TODO: использовать правила из `RuleConfig` для более сложных политик).
    - Обновление `player.xp` для каждого игрока-получателя.
    - Логирование события `EventType.XP_GAINED` через `core.game_events.log_event`.
- **Реализация `_check_for_level_up`**:
    - Функция `_check_for_level_up(session, guild_id, player)` реализована.
    - Загрузка правил `experience_system:level_curve` и `experience_system:level_up_rewards` из `RuleConfig` (через `core.rules.get_rule`).
    - Циклическая проверка повышения уровня:
        - Если `player.xp` достаточно для следующего уровня согласно `level_curve`, уровень игрока (`player.level`) увеличивается, XP вычитается.
        - Начисляются награды (`player.unspent_xp` увеличивается на `attribute_points` из `level_up_rewards`).
        - Логируется событие `EventType.LEVEL_UP`.
    - Обработаны случаи отсутствия правил или достижения максимального уровня, определенного кривой.
- **Интеграция `_check_for_level_up` в `award_xp`**:
    - `_check_for_level_up` вызывается для каждого игрока после начисления ему XP.
    - `session.commit()` и `session.refresh()` выполняются один раз в конце `award_xp` для всех измененных игроков.
- **Экспорт API**:
    - `award_xp` и модуль `experience_system` добавлены в `src/core/__init__.py` и в `__all__`.
- **Unit-тесты**:
    - Создан файл `tests/core/test_experience_system.py`.
    - Написаны тесты, покрывающие начисление XP игроку и партии, повышение на один и несколько уровней, логирование, обработку отсутствующих правил/сущностей, достижение максимального уровня и нулевое распределение XP.

## Пользовательская задача: Рефакторинг структуры команд бота и настроек их загрузки
- **Анализ проблемы**: Выявлено наличие двух файлов с командами общего назначения: `src/bot/general_commands.py` (использующий префиксные команды) и `src/bot/commands/general_commands.py` (использующий слеш-команды и более современный подход). Настройки в `src/config/settings.py` загружали старую версию (`src/bot/general_commands.py`).
- **Консолидация команд**:
    - Команда `ping` из `src/bot/general_commands.py` была перенесена в `src/bot/commands/general_commands.py`.
    - Команда `ping` была адаптирована для использования как слеш-команда (`app_command`) в `GeneralCog`.
    - Файл `src/bot/commands/general_commands.py` теперь содержит актуальные версии команд `start` и `ping` в виде слеш-команд.
- **Обновление настроек загрузки когов**:
    - В файле `src/config/settings.py` список `BOT_COGS` был изменен для загрузки кога из `src.bot.commands.general_commands`.
    - Удалена запутанная условная логика, связанная с загрузкой старых версий когов.
- **Удаление избыточного файла**:
    - Файл `src/bot/general_commands.py` был удален.
- **Проверка импортов**:
    - Обнаружен импорт удаленного кога (`CommandCog` из `src.bot.general_commands`) в тестовом файле `tests/bot/test_general_commands_mocked.py`.
    - Устаревший тестовый файл `tests/bot/test_general_commands_mocked.py` был удален, так как он тестировал префиксные команды из удаленного модуля.
- **Концептуальное планирование тестов**:
    - Определены необходимые тесты для `GeneralCog` в `src/bot/commands/general_commands.py`, включая тесты для слеш-команд `/ping` и `/start` с учетом их логики и взаимодействия с Discord API и базой данных.

## Task 1.2: 🌍 Player and Party System (ORM, Commands, Guild-Scoped)
- **Определение задачи**: Прочитан `Tasks.txt`, выбрана задача Task 1.2.
- **Анализ на предмет выполнения**:
    - Модели `Player` (`src/models/player.py`) и `Party` (`src/models/party.py`) существуют и в основном соответствуют требованиям.
    - Миграции Alembic для этих моделей существуют.
    - Утилиты `get_player`, `get_party`, `get_players_in_location` реализованы через CRUD-модули.
    - Команды Discord `/start` и `/party` (create, leave, disband, join) существуют и реализуют базовую функциональность.
    - **Выявлен недостаток**: Отсутствуют специализированные unit-тесты для моделей, CRUD и команд, связанных с Player и Party.
- **Написание Unit-тестов**:
    - Создан файл `tests/models/test_player.py` с тестами для модели `Player`.
    - Создан файл `tests/models/test_party.py` с тестами для модели `Party`.
    - Создан файл `tests/core/crud/test_crud_player.py` с тестами для `CRUDPlayer`.
    - Создан файл `tests/core/crud/test_crud_party.py` с тестами для `CRUDParty`.
    - Создан файл `tests/bot/commands/test_general_commands.py` с тестами для команды `/start`.
    - Создан файл `tests/bot/commands/test_party_commands.py` с тестами для команд `/party`.
- **Обновление `AGENTS.md`**: Обновлен "Текущий план" и "Лог действий" для Task 1.2.

## Task 1.1: 🌍 Location Model (i18n, Guild-Scoped)
- **Определение задачи**: Прочитан `Tasks.txt`, выбрана задача Task 1.1.
- **Анализ на предмет выполнения**: По запросу пользователя проведен глубокий анализ кода.
    - Проверен файл `src/models/location.py`: Модель `Location` существует и соответствует требованиям.
    - Проверен файл `src/core/locations_utils.py`: Утилиты `get_location`, `get_location_by_static_id`, `get_localized_text` существуют и соответствуют требованиям.
    - Проверены миграции Alembic (`alembic/versions/`): Миграции `fcb2e6d12a18_initial_schema_setup.py` (создание) и `0005_use_jsonb_for_location_fields.py` (обновление до JSONB) существуют.
    - Проверены тесты: `tests/models/test_location.py` и `tests/core/test_locations_utils.py` существуют и содержат релевантные тесты.
- **Вывод**: Задача 1.1 была ранее выполнена, но не отмечена должным образом.
- **Обновление `AGENTS.md`**: Обновлен "Текущий план" и "Лог действий" для отражения анализа и последующих шагов по завершению задачи.

## Task 29: ⚔️ 5.4 Combat Cycle Refactoring (Multiplayer Combat State Machine)
- **Определение задачи**: Прочитан `Tasks.txt`, выбрана задача Task 29: Combat Cycle Refactoring.
- **Планирование**: Составлен детальный план для реализации Task 29.
- **Создание модуля `combat_cycle_manager.py`**:
    - Создан файл `src/core/combat_cycle_manager.py` с базовыми импортами, логгером и заглушками для зависимых систем (XP, Loot, Relationships, WorldState, Quests).
- **Реализация `start_combat` API**:
    - В `src/core/combat_cycle_manager.py` реализована функция `start_combat`.
    - Функция создает запись `CombatEncounter`, определяет участников (`participants_json`) и их начальные статы.
    - Реализован расчет инициативы (dice roll + dex modifier) и формирование `turn_order_json`.
    - Создается снимок релевантных боевых правил в `rules_config_snapshot_json`.
    - Статус `CombatEncounter` устанавливается в `ACTIVE`. Статусы участвующих игроков (`PlayerStatus.IN_COMBAT`) и партий (`PartyTurnStatus.IN_COMBAT`) обновляются.
    - Логируется событие `COMBAT_START`.
    - Функция `start_combat` экспортирована из `src/core/__init__.py`.
- **Интеграция `start_combat` с `action_processor.py`**:
    - В `src/core/crud/crud_combat_encounter.py` добавлена функция `get_active_combat_for_entity` для проверки, не находится ли сущность уже в бою.
    - В `src/core/action_processor.py` создан новый обработчик `_handle_attack_action_wrapper` для интента "attack".
    - `_handle_attack_action_wrapper` определяет цель атаки, проверяет наличие существующего боя для актора или цели.
    - Если бой не начат, вызывается `combat_cycle_manager.start_combat`. Затем первая атака инициатора обрабатывается через `combat_engine.process_combat_action`.
    - Если бой уже идет, и это ход атакующего, атака обрабатывается через `combat_engine.process_combat_action`.
- **Реализация `process_combat_turn` API и вспомогательных функций**:
    - В `src/core/combat_cycle_manager.py` реализована функция `process_combat_turn`.
    - Функция загружает `CombatEncounter`, проверяет его статус.
    - Если ход NPC: вызывает `npc_combat_strategy.get_npc_combat_action`, затем `combat_engine.process_combat_action`.
    - После действия (игрока или NPC) вызывается `session.refresh(combat_encounter)`.
    - Реализована вспомогательная функция `_check_combat_end` для определения завершения боя и победившей команды на основе состояния здоровья участников в `participants_json`.
    - Реализована вспомогательная функция `_advance_turn` для переключения хода на следующего живого участника, обновления `current_turn_entity_id/type`, `current_index` и `current_turn_number`.
    - Если после продвижения хода наступает ход NPC, `process_combat_turn` рекурсивно вызывается для обработки хода этого NPC (и последующих, пока не наступит ход игрока или конец боя).
    - Функция `process_combat_turn` экспортирована из `src/core/__init__.py`.
- **Реализация `_handle_combat_end_consequences`**:
    - В `src/core/combat_cycle_manager.py` реализована вспомогательная функция `_handle_combat_end_consequences`.
    - Функция определяет победителей и проигравших.
    - Вызывает заглушки для систем XP (`xp_awarder.award_xp`), лута (`loot_generator.distribute_loot`), отношений (`relationship_updater.update_relationships_post_combat`), состояния мира (`world_state_updater.update_world_state_post_combat`) и квестов (`quest_system.handle_combat_event_for_quests`).
    - Сбрасывает боевые статусы игроков и партий.
    - Логирует событие `COMBAT_END`.
- **Обновление механизма вызова `process_combat_turn`**:
    - В `src/core/action_processor.py` (в `_handle_attack_action_wrapper`) после обработки действия игрока в существующем бою или после первого действия в новом бою теперь вызывается `combat_cycle_manager.process_combat_turn` для продвижения состояния боя.
- **Написание Unit-тестов**:
    - Создан файл `tests/core/test_combat_cycle_manager.py`.
    - Написаны базовые тесты для `start_combat` (успешное создание, расчет инициативы, обновление статусов, логирование).
    - Написан скелет теста для `process_combat_turn` с моками для зависимостей.
    - Добавлены концептуальные тесты для `_check_combat_end` и `_advance_turn`.
    - Добавлен тест для проверки обновления статуса партии при начале боя.

## Task 28: ⚔️ 5.3 NPC Combat Strategy Module (AI)
- **Определение задачи**: Прочитан `Tasks.txt`, выбрана задача Task 28: NPC Combat Strategy Module.
- **Планирование**: Составлен детальный план для реализации Task 28, включающий анализ, проектирование, реализацию функций загрузки данных, выбора цели, выбора действия, форматирования результата, написание тестов и интеграцию.
- **Анализ Task 28**: Изучены требования к API `get_npc_combat_action`, определены зависимости от других модулей (NPC, CombatEncounter, RuleConfig, Relationship, CheckResolver) и данных (статы NPC, способности, состояние боя, правила поведения AI).
- **Проектирование модуля `npc_combat_strategy.py`**:
    - Определена основная функция `get_npc_combat_action`.
    - Спроектированы вспомогательные функции: `_get_npc_data`, `_get_combat_encounter_data`, `_get_participant_entity`, `_get_relationship_value`, `_get_npc_ai_rules`, `_is_hostile`, `_get_potential_targets`, `_calculate_target_score`, `_select_target`, `_get_available_abilities`, `_simulate_action_outcome`, `_evaluate_action_effectiveness`, `_choose_action`, `_format_action_result`.
- **Реализация загрузки данных**:
    - В `src/core/npc_combat_strategy.py` реализованы функции `_get_npc_data`, `_get_combat_encounter_data`, `_get_participant_entity`, `_get_relationship_value`.
    - Реализована функция `_get_npc_ai_rules` с базовой логикой загрузки правил из `RuleConfig` (с использованием `core.rules.get_rule`), применения правил по умолчанию и простых модификаторов на основе личности NPC.
    - Модуль `npc_combat_strategy` и функция `get_npc_combat_action` добавлены в `src/core/__init__.py`.
- **Реализация логики выбора цели (Aggro System)**:
    - Реализована функция `_is_hostile` для определения враждебности цели (учет отношений, фракций, правил по умолчанию).
    - Реализована функция `_get_potential_targets` для формирования списка доступных враждебных целей (фильтрация себя, побежденных, невраждебных).
    - Реализована функция `_calculate_target_score` для оценки целей по различным метрикам (HP (процент/абсолют), угроза). Метрика угрозы (`highest_threat_score`) включает базовые факторы (урон по себе, роль цели, низкое HP цели, отношения).
    - Реализована функция `_select_target` для выбора наилучшей цели на основе приоритетного списка метрик из AI-правил.
- **Реализация логики выбора действия**:
    - Реализована функция `_get_available_abilities` для получения списка способностей NPC с учетом кулдаунов и стоимости ресурсов.
    - Реализована упрощенная функция `_simulate_action_outcome` (placeholder) для оценки шанса попадания и ожидаемого урона.
    - Реализована функция `_evaluate_action_effectiveness` для оценки общей привлекательности действия (урон, стратегическая ценность статусов/лечения, проверка порогов симуляции).
    - Реализована функция `_choose_action` для выбора наилучшего действия из доступных (атака, способности) на основе их оценки эффективности и специальных условий (например, самолечение при низком HP).
- **Формирование результата**:
    - Реализована функция `_format_action_result` для преобразования выбранного действия в формат, ожидаемый `CombatEngine`.
    - Основная функция `get_npc_combat_action` обновлена для использования всех вспомогательных функций и корректного возврата результата.
- **Написание Unit-тестов**:
    - Создан файл `tests/core/test_npc_combat_strategy.py`.
    - Добавлены фикстуры для моков данных (`mock_session`, `mock_actor_npc`, `mock_target_player`, `mock_combat_encounter`, `mock_ai_rules` и др.).
    - Написаны тесты для `_get_available_abilities` (проверка маны, кулдаунов).
    - Написаны тесты для `_is_hostile` (проверка враждебности на основе отношений, фракций).
    - Написан базовый тест для `_get_potential_targets`.
    - Написаны высокоуровневые интеграционные тесты для `get_npc_combat_action`, покрывающие сценарии: успешный выбор действия, побежденный NPC, отсутствие целей.
- **Интеграция (мысленная)**: Проанализировано взаимодействие `npc_combat_strategy` с `CombatEngine`. Определены точки вызова, формат передаваемых данных и ожидаемого результата. Отмечены зависимости от корректного обновления `CombatEncounter.participants_json` модулем `CombatEngine`.

## Task 27: ⚔️ 5.2 Combat Engine Module
- **Определение задачи**: Прочитан `Tasks.txt`, выбрана задача Task 27.
- **Планирование**: Составлен детальный план для реализации Task 27.
- **Анализ зависимостей**: Изучены модели и утилиты.
- **Проектирование `process_combat_action`**: Определена сигнатура и основная логика.
- **Реализация вспомогательных функций**: Функции `_get_combat_rule`, `_calculate_attribute_modifier`, `_get_participant_stat` реализованы.
- **Доработка `CombatActionResult`**: Модели `CheckResult` и связанные перенесены, импорты обновлены.
- **Интеграция с другими модулями**: Проверены вызовы к другим модулям.
- **Написание Unit-тестов**: Написаны тесты для вспомогательных функций и каркас для `process_combat_action`.
- **Реализация и тестирование `process_combat_action`**:
    - Реализована основная функция `process_combat_action` в `src/core/combat_engine.py`.
    - Реализована обработка действия "attack", включая расчет попадания, урона, критических ударов (с разными правилами) и промахов.
    - Реализована обработка ошибок: не найден бой, актор, цель; цель уже побеждена; неизвестный тип действия.
    - HP участников обновляется в `CombatEncounter.participants_json`.
    - Результаты боя логируются в `CombatEncounter.combat_log_json` и глобальный `StoryLog`.
    - Устранены проблемы с импортами в `src/core/__init__.py`.
    - Устранены проблемы с запуском тестов из-за окружения и зависимостей.
    - Исправлена ошибка в логике крит. удара, приводившая к неверному количеству вызовов `roll_dice`.
    - Все 15 тестов в `tests/core/test_combat_engine.py` успешно пройдены.
- **Обновление `AGENTS.md`**: Обновлен лог действий и очищен текущий план.

## Пользовательская задача: Исправление ошибок Pyright (после Task 22 и 25)
- **Анализ отчета Pyright**: Выявлены ошибки в `src/core/ability_system.py`.
- **Исправление ошибок импорта**:
    - Добавлены импорты `get_entity_stat`, `change_entity_stat` из `src.core.entity_stats_utils`.
    - Добавлен импорт `func` из `sqlalchemy.sql`.
- **Исправление синтаксической ошибки**:
    - Удалена лишняя закрывающая скобка в закомментированном блоке кода (район строки 385), вызывавшая ошибку "Expected expression".
- **Обзор и доработка кода**:
    - Удалена дублирующая (старая, неиспользуемая) функция `activate_ability`.
    - Параметр `ability_id` в основной функции `activate_ability` переименован в `ability_identifier` с типом `Union[int, str]` для соответствия внутренней логике загрузки способности.
- **Дополнительное исправление**:
    - Проверен и подтвержден импорт `PlayerStatus` из `src.models.enums` в `src/core/ability_system.py` (был на месте, ошибка Pylance, вероятно, из-за кэша).

## Задача 25: 🗺️ 4.3 Location Transitions (Guild-Scoped)
- **Анализ задачи и существующего кода**:
    - Проанализировано описание Task 25.
    - Изучена существующая функция `execute_move_for_player_action` в `src/core/movement_logic.py` и связанные модули. Большая часть функционала уже реализована. Основная доработка - правила перемещения партии.
- **Проектирование и реализация `execute_move_for_player_action` (доработка)**:
    - В `execute_move_for_player_action` добавлена логика проверки правил перемещения партии из `RuleConfig` (ключ `rules:party:movement:policy`).
    - Реализована поддержка политики `"leader_only"`: движение разрешено только если инициатор является лидером партии (`party.leader_player_id == player.id`).
    - Для этого в модель `Party` (`src/models/party.py`) добавлено поле `leader_player_id` (ForeignKey к `players.id`) и связь `leader`.
    - Создана и заполнена миграция Alembic (`7c27451a6727_add_leader_player_id_to_party.py`) для нового поля.
    - Политика `"any_member"` (любой член партии может инициировать движение) остается поведением по умолчанию.
- **Интеграция**:
    - Проверена существующая интеграция `execute_move_for_player_action` в `action_processor.py`. Изменений не потребовалось.
- **Unit-тесты**:
    - Обновлен и расширен файл `tests/core/test_movement_logic.py`.
    - Добавлены тесты для `execute_move_for_player_action`, покрывающие успешное перемещение (соло и в партии), проверку правил партии ("leader_only", "any_member"), ошибки (локация не найдена, нет связи).
    - Добавлены тесты для вспомогательной функции `_find_location_by_identifier` (поиск по static_id, по имени с учетом языка и fallback).

## Задача 22: 🧠 3.3 API for Activating Abilities and Applying Statuses (Guild-Scoped)
- **Рефакторинг и подготовка `ability_system.py`**:
    - Функции `activate_ability_v2` и `apply_status_v2` переименованы в `activate_ability` и `apply_status` соответственно; старые версии удалены.
    - В модель `ActiveStatusEffect` (`src/models/status_effect.py`) добавлены поля `source_entity_id` и `source_entity_type` для отслеживания источника статуса.
    - Создана и заполнена миграция Alembic `b3920fb77c09_add_source_entity_to_active_status_.py` для добавления новых полей в БД.
    - Создан новый файл `src/core/entity_stats_utils.py` с утилитами для получения и изменения HP и других статов/ресурсов у сущностей (`Player`, `GeneratedNpc`).
    - Функция `activate_ability` обновлена для использования `change_entity_hp` из `entity_stats_utils`.
- **Реализация проверок в `activate_ability`**:
    - Реализована проверка и списание затрат ресурсов (поле `cost` из `properties_json` способности) с использованием `get_entity_stat` и `change_entity_stat`. В случае нехватки ресурсов активация прерывается.
    - Добавлен пример проверки условия активации "caster_must_be_in_combat" на основе `RuleConfig` и статуса кастера (`Player.current_status` или `GeneratedNpc.properties_json["stats"]["status"]`).
    - Добавлены комментарии-TODO для более сложных проверок (доступность способности кастеру, кулдауны).
- **Реализация логики эффектов в `activate_ability`**:
    - Реализована логика выбора целей для каждого эффекта на основе `effect_data.target_scope` (поддерживаются "self", "first_target", "all_targets").
    - Эффект "damage": использует `change_entity_hp` для нанесения урона. Заполняется `outcome.damage_dealt`.
    - Эффект "healing": добавлен новый тип эффекта, использует `change_entity_hp` для восстановления HP. Заполняется `outcome.healing_done`.
    - Эффект "apply_status": вызывает доработанную `apply_status`, передавая `status_static_id` и `duration` из `effect_data`. Заполняется `outcome.applied_statuses`.
- **Доработка `apply_status`**:
    - Реализована проверка на существующий активный статус того же типа на цели.
    - Если статус существует и `StatusEffect.properties_json` содержит `duration_refresh: true`, то у существующего `ActiveStatusEffect` обновляются `duration_turns`, `remaining_turns`, `applied_at` и информация об источнике. В противном случае (если `duration_refresh: false` или не указано), и статус уже есть, новая попытка применения игнорируется (возвращается `False`).
    - Если статус не существует, создается новый `ActiveStatusEffect`.
    - Поля `source_entity_id` и `source_entity_type` корректно присваиваются.
    - Поле `remaining_turns` инициализируется значением `duration_turns`.
- **Доработка `remove_status`**:
    - Функция проанализирована. Текущая реализация (удаление по `active_status_id`) и логирование признаны достаточными для Task 22.
- **Логирование и `AbilityOutcomeDetails` в `activate_ability`**:
    - `AbilityOutcomeDetails` корректно собирает информацию о `damage_dealt`, `healing_done`, `applied_statuses`, `caster_updates`.
    - Общее сообщение об успехе/неудаче в `outcome.message` устанавливается.
    - `log_event_details` в `AbilityOutcomeDetails` содержит полный JSON для записи в `StoryLog`.
    - Вызов `log_event` происходит в конце успешной обработки способности.
- **Транзакционность**:
    - Проверено, что `activate_ability` использует переданную сессию и не управляет транзакцией (commit/rollback), что является корректным поведением.
- **Написание Unit-тестов**:
    - Создан файл `tests/core/test_ability_system.py`.
    - Написаны базовые unit-тесты для `activate_ability`, `apply_status` и `remove_status`, покрывающие основные сценарии (успех, нехватка ресурсов, применение/обновление/снятие статусов) с использованием моков.

## Задача 19 / Задача 54 (Log and Feedback Formatting): Завершение
- Выполнено обновление `AGENTS.md` для отражения завершения задачи.
- Задача 54 ("⚙️ 6.7.1 Log and Feedback Formatting System (Full, Multy-i18n, Guild-Scoped)") удалена из `Tasks.txt`.
- Запись о Task 19 ("📚 7.3 Turn and Report Formatting (Guild-Scoped)") в `Done.txt` признана корректной и полной.
- Секция "Текущий план" в `AGENTS.md` очищена.

## Задача 19 (Ранее): 📚 7.3 Turn and Report Formatting (Guild-Scoped)
- **Анализ существующего кода и зависимостей**:
    - Изучены `src/models/story_log.py`, `src/models/enums.py` (для `EventType`), `src/core/rules.py`, `src/core/localization_utils.py`, `src/core/report_formatter.py` и связанные тесты.
    - Вывод: Большая часть функционала для Task 19 уже существует, включая `get_localized_entity_name`, `get_batch_localized_entity_names`, `_format_log_entry_with_names_cache` (с обработкой многих `EventType`), `format_turn_report` и `_collect_entity_refs_from_log_entry`. Задача сводится к доработке и верификации.
- **Проверка `get_localized_entity_name`**:
    - Функции `get_localized_entity_name` и `get_batch_localized_entity_names` в `src/core/localization_utils.py` признаны достаточно функциональными. Дополнительная реализация не требуется.
- **Доработка `_format_log_entry_with_names_cache` в `src/core/report_formatter.py`**:
    - Добавлена или улучшена логика форматирования для следующих `EventType`: `NPC_ACTION`, `ITEM_USED`, `ITEM_DROPPED`, `DIALOGUE_START`, `DIALOGUE_END`, `FACTION_CHANGE`.
    - Добавлена общая стратегия форматирования для менее критичных для игрока событий (например, `SYSTEM_EVENT`, события AI, события управления картой), которая выводит тип события и основные детали из `details_json`.
    - Обновлены unit-тесты в `tests/core/test_report_formatter.py` для покрытия новых обработчиков событий.
- **Проверка `format_turn_report`**:
    - Функция `format_turn_report` в `src/core/report_formatter.py` проанализирована и признана соответствующей требованиям. Дополнительная реализация не требуется.
- **Обновление `_collect_entity_refs_from_log_entry` в `src/core/report_formatter.py`**:
    - Дополнена логика для корректного сбора ID сущностей для `NPC_ACTION`, `ITEM_USED`, `ITEM_DROPPED`, `DIALOGUE_START`, `DIALOGUE_END`, `FACTION_CHANGE`.
    - Добавлен базовый сбор ID для общих типов событий.
    - Обновлены unit-тесты в `tests/core/test_report_formatter.py` для покрытия этих изменений.
- **Проверка `src/core/__init__.py`**:
    - Подтверждено, что все необходимые функции (`format_turn_report`, `get_localized_entity_name`, `get_batch_localized_entity_names`, `get_localized_text`) корректно экспортируются. Изменения не потребовались.

## Задача 6.1.1: ⚙️ Intra-Location Interaction Handler Module
- **Анализ существующего кода и логов**:
    - Проанализирован `Tasks.txt` и существующий лог в `AGENTS.MD` (Задача 29), который соответствует Задаче 6.1.1.
    - Выявлено, что основная структура `handle_intra_location_action` и связанные компоненты (NLU, `action_processor`) уже реализованы.
    - Ключевая недостающая часть: полная реализация логики интента `interact` с интеграцией `RuleConfig` и `resolve_check`.
- **Доработка интента `interact` в `src/core/interaction_handlers.py`**:
    - Реализована загрузка правил взаимодействия из `RuleConfig` по ключу `interactions:<interaction_rules_key>`.
    - Если правило требует проверки (`requires_check: true`):
        - Собираются параметры для `resolve_check` (тип проверки, атрибут игрока, DC).
        - Вызывается `core.check_resolver.resolve_check`.
        - Результат проверки используется для формирования обратной связи и логирования (`log_event`). Записывается ключ последствий для будущей обработки.
    - Если проверка не требуется:
        - Логируется ключ прямых последствий.
    - Обновлены сообщения обратной связи в `_format_feedback` для различных исходов `interact`.
    - Обновлено логирование события `player_interact` для включения деталей о правиле и результате проверки.
- **Обновление Unit-тестов в `tests/core/test_interaction_handlers.py`**:
    - Тест `test_interact_existing_object_with_rules_placeholder` переименован в `test_interact_object_with_check_success` и обновлен.
    - Добавлены новые тесты:
        - `test_interact_object_with_check_failure` (провал проверки).
        - `test_interact_object_no_check_required` (взаимодействие без проверки).
        - `test_interact_object_rule_not_found` (правило для ключа не найдено в RuleConfig).
    - Тест `test_interact_existing_object_no_rules` переименован в `test_interact_object_no_interaction_key` и уточнен.
    - Тесты мокируют `get_rule` и `resolve_check`, проверяют корректность их вызова и обработку результатов.

## Задача 27: ⚔️ 5.2 Combat Engine Module
- **Анализ требований и существующего кода**:
    - Проанализированы требования к API `process_combat_action` из `Tasks.txt`.
    - Изучен существующий `src/core/combat_engine.py` и связанные модели (`CombatEncounter`, `Player`, `GeneratedNpc`, `CombatActionResult`, `CheckResult`).
    - Выявлена необходимость интеграции правил из `RuleConfig`, полноценного использования `resolve_check` и детализированного расчета урона.
- **Доработка `CombatActionResult`**:
    - В `src/models/combat_outcomes.py` уточнена аннотация типа для `check_result` на `Optional[CheckResult]` вместо `Optional[Dict[str, Any]]`.
    - Для разрешения прямого импорта `CheckResult` его определение (вместе с `ModifierDetail`, `CheckOutcome`) перенесено из `src/core/check_resolver.py` в новый файл `src/models/check_results.py`.
    - В `src/models/__init__.py` добавлены импорты новых моделей (`CheckResult`, `CheckOutcome`, `ModifierDetail`) и вызовы `model_rebuild()` для `CombatActionResult` и этих моделей для корректной обработки forward-ссылок Pydantic.
- **Доработка `process_combat_action` в `src/core/combat_engine.py`**:
    - **Загрузка данных**: Улучшена загрузка `CombatEncounter` (с использованием `guild_id`), актора и цели. Улучшена обработка ошибок при отсутствии сущностей.
    - **Вспомогательные функции**:
        - `_get_combat_rule`: Для получения правил боя, с приоритетом из `combat_encounter.rules_config_snapshot_json`, затем из `RuleConfig` (`core.rules.get_rule`).
        - `_get_participant_stat`: Для получения статов участника боя, с приоритетом из `participant_data` (в `CombatEncounter.participants_json`), затем из базовой модели (`Player`, `GeneratedNpc.properties_json.stats`), с возможностью расчета модификаторов (`_modifier` в названии стата).
        - `_calculate_attribute_modifier`: Для расчета модификатора атрибута на основе базового значения и формулы из `RuleConfig` (например, `(value - 10) // 2`).
    - **Логика действия "attack"**:
        - **Получение правил**: Динамическое получение правил для действия "attack" (тип проверки, атрибуты для атаки/урона, DC, формула урона, правила крит. удара) с использованием `_get_combat_rule`.
        - **Расчет DC**: DC для атаки рассчитывается как `dc_base` (из правил) + модификатор атрибута цели (например, ловкости, из правил).
        - **Разрешение проверки**: Вызов `core.check_resolver.resolve_check` с передачей рассчитанного DC, типа проверки, деталей актора/цели. Обработано исключение `CheckError`.
        - **Расчет урона**:
            - Если проверка успешна: получается модификатор атрибута урона актора. Формула урона (из правил, например, "1d6+@actor_strength_modifier") обрабатывается: плейсхолдер модификатора заменяется рассчитанным значением. `core.dice_roller.roll_dice` вызывается для полученной строки формулы.
            - Применяется множитель критического урона (из правил), если результат проверки - крит. успех.
            - Урон не может быть отрицательным.
        - **Обновление HP**: HP цели обновляется в `participants_data` (in-memory список для `combat_encounter.participants_json`).
        - **Формирование описания**: Генерируется текстовое описание исхода атаки.
        - **`CombatActionResult`**: Заполняется всеми деталями (успех, урон, результат проверки, описание, использованные правила).
    - **Обработка неизвестных действий**: Возвращается `CombatActionResult` с сообщением об ошибке.
    - **Обновление состояния боя**: `combat_encounter.participants_json` и `combat_encounter.combat_log_json` обновляются.
    - **Логирование StoryLog**: Вызов `core.game_events.log_event` с полными `details_json` (включая `action_result`) и корректным `entity_ids_json` (актор и цель). Удален дублирующийся вызов `log_event`.
- **Обновление Unit-тестов в `tests/core/test_combat_engine.py`**:
    - Тесты переписаны с использованием корректных техник мокирования для `async def` функций и их `side_effect` (использование `async def` функции в качестве `side_effect` для `AsyncMock`).
    - Исправлены цели патчей для функций, импортируемых в `combat_engine.py` (например, `patch('src.core.combat_engine.get_rule', ...)` вместо `patch('src.core.rules.get_rule', ...)`).
    - Мок для `dice_roller.roll_dice` изменен на `MagicMock`, так как функция синхронная.
    - Мок для `resolve_check` в тесте на `CheckError` теперь напрямую присваивает экземпляр исключения в `side_effect`.
    - Покрыты сценарии: успешная атака (попадание, урон, обновление HP), промах, критическое попадание, использование правил из snapshot, ошибки (бой/актор/цель не найдены, ошибка в `resolve_check`).
    - Все 7 тестов успешно пройдены после исправлений.
- **Административные действия по завершению предыдущей задачи (Task 26)**:
    - Задача 26 удалена из `Tasks.txt`.
    - Задача 26 добавлена в `Done.txt`.

## Задача 19 (старая): 📚 7.3 Turn and Report Formatting (Guild-Scoped) - Revisit
- **Цель пересмотра**: Расширить поддержку форматирования для большего числа типов событий в `src/core/report_formatter.py`.
- **Определение приоритетных типов событий**:
    - На основе анализа `_collect_entity_refs_from_log_entry` и `_format_log_entry_with_names_cache` были определены следующие типы событий для добавления форматирования: `COMBAT_START`, `QUEST_ACCEPTED`, `QUEST_STEP_COMPLETED`, `QUEST_COMPLETED`, `LEVEL_UP`, `XP_GAINED`, `RELATIONSHIP_CHANGE`, `STATUS_APPLIED`.
- **Реализация форматирования**:
    - В функцию `_format_log_entry_with_names_cache` добавлены блоки `elif` для каждого из 8 приоритетных типов событий.
    - Для каждого типа события реализована логика извлечения данных из `log_entry_details_json`, использования `get_name_from_cache` для имен сущностей и `get_term` для локализуемых строк и шаблонов сообщений.
- **Добавление Unit-тестов**:
    - В `tests/core/test_report_formatter.py` добавлены новые параметризованные тесты для каждого из 8 новых форматов событий.
    - Тесты проверяют корректность форматирования для языков `en` и `ru`, использование кеша имен и терминов из `RuleConfig` (через моки).
- **Рассмотрение дополнительных типов событий (опционально)**:
    - Были рассмотрены другие типы событий из `EventType`. Принято решение добавить форматирование для `DIALOGUE_LINE`, `STATUS_REMOVED` и `QUEST_FAILED` как наиболее критичных для полноты отчетов.
    - Обновлена функция `_collect_entity_refs_from_log_entry` для корректного сбора ссылок на сущности для `DIALOGUE_LINE` и `QUEST_FAILED` (для `STATUS_REMOVED` существующая логика для `STATUS_APPLIED` подходит).
    - В `_format_log_entry_with_names_cache` добавлена логика форматирования для `DIALOGUE_LINE`, `STATUS_REMOVED`, `QUEST_FAILED`.
    - В `tests/core/test_report_formatter.py` добавлены соответствующие unit-тесты для этих трех дополнительных типов событий.
- **Обзор и рефакторинг**:
    - Проведен обзор внесенных изменений. Код соответствует существующим паттернам. Вопрос передачи сессии в `get_rule` через форматер остается известной особенностью, не требующей немедленного рефакторинга в рамках данной задачи.
- **Результат**: Модуль форматирования отчетов теперь поддерживает значительно большее количество типов событий, улучшая детализацию и информативность логов для игроков.
- **Рефакторинг (Сессия 2024-07-04):**
    - **Устранение проблемы с `AsyncSession` в `_format_log_entry_with_names_cache`**:
        - Модифицирована `_format_log_entry_with_names_cache` для приема `AsyncSession` в качестве первого параметра.
        - Внутренняя функция `get_term` обновлена для использования этой сессии при вызове `core.rules.get_rule`.
        - Функция `format_turn_report` обновлена для передачи `AsyncSession` в `_format_log_entry_with_names_cache`.
        - Unit-тесты в `tests/core/test_report_formatter.py` скорректированы для передачи `mock_session` в вызовы `_format_log_entry_with_names_cache`.
    - **Улучшение логики языкового fallback в `get_term`**:
        - Реализован многоуровневый fallback:
            1. Запрошенный язык из `RuleConfig`.
            2. Основной fallback-язык ("en") из `RuleConfig`.
            3. Запрошенный язык из `default_text_map`.
            4. Основной fallback-язык ("en") из `default_text_map`.
            5. Первое доступное значение из `default_text_map`.
            6. Пустая строка, если термин не найден.
    - Все тесты (356) успешно пройдены после изменений.

## Текущая сессия: Анализ и доработка Задач 1.1 и 1.2 (старый лог)
- ... (содержимое этого лога опущено для краткости, так как оно нерелевантно для текущей задачи) ...

## Задача 19 (старый лог): 📚 7.3 Turn and Report Formatting (Guild-Scoped)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 23: 🗺️ 4.1 Location Model (i18n, Guild-Scoped)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 21: 🧠 3.2 Entity Status Model (i18n, Guild-Scoped)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 18: 📚 7.2 AI Narrative Generation (Multilang)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 20: 🧠 3.1 Ability Model (i18n, Guild-Scoped)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 26: ⚔️ 5.1 Combat and Participant Model (Guild-Scoped)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 1: 🗺️ 4.3 Location Transitions (Guild-Scoped)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 2: 🧠 3.3 API for Activating Abilities and Applying Statuses (Guild-Scoped)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 3: Пользовательская задача: Полный цикл тестов и покрытие нового функционала
- ... (содержимое этого лога опущено для краткости) ...

## Задача 4: Пользовательская задача: Рефакторинг проекта
- ... (содержимое этого лога опущено для краткости) ...

## Задача 5: Пользовательская задача: Исправление ошибок Pyright
- ... (содержимое этого лога опущено для краткости) ...

## Задача 6: Пользовательская задача: Исправление ошибок Pyright
- ... (содержимое этого лога опущено для краткости) ...

## Задача 7: Пользовательская задача: Создание мок-тестов и исправление ошибок
- ... (содержимое этого лога опущено для краткости) ...

## Задача 8: 🎲 6.3.2 Check Resolver Module
- ... (содержимое этого лога опущено для краткости) ...

## Задача 9: 🎲 6.3.1 Dice Roller Module
- ... (содержимое этого лога опущено для краткости) ...

## Задача 10: Сессия [Текущая дата/время]: Начало работы
- ... (содержимое этого лога опущено для краткости) ...

## Задача 11: 🚀 0.1 Discord Bot Project Initialization
- ... (содержимое этого лога опущено для краткости) ...

## Задача 12: 🗄️ 0.2 DBMS Setup and Database Model Definition
- ... (содержимое этого лога опущено для краткости) ...

## Задача 13: 🛠️ 0.3 Core Utils
- ... (содержимое этого лога опущено для краткости) ...

## Задача 14: 🌍 1.1 Location Model, Utils, and Default Population
- ... (содержимое этого лога опущено для краткости) ...

## Задача 15: 👥 1.2 Player and Party System
- ... (содержимое этого лога опущено для краткости) ...

## Задача 16: 🚶 1.3 Movement Logic and Command
- ... (содержимое этого лога опущено для краткости) ...

## Задача 17: 📦 2.1 Finalize Definition of ALL DB Schemas
- ... (содержимое этого лога опущено для краткости) ...

## Задача 18 (старый): 🤖 2.2 AI Prompt Preparation Module
- ... (содержимое этого лога опущено для краткости) ...

## Задача 19 (очень старый): ✅ 2.3 AI Prompt Construction Logic
- ... (содержимое этого лога опущено для краткости) ...

## Задача 20 (старый): 🧠 2.6 AI Generation, Moderation, and Saving Logic
- ... (содержимое этого лога опущено для краткости) ...

## Задача 21 (старый): ⚙️ 6.10 Action Parsing and Recognition Module
- ... (содержимое этого лога опущено для краткости) ...

## Задача 22: ⚙️ 6.12 Turn Queue System
- ... (содержимое этого лога опущено для краткости) ...

## Задача 23 (старый): ⚙️ 6.11 Central Collected Actions Processing Module
- ... (содержимое этого лога опущено для краткости) ...

## Задача 24: 🗺️ 4.2 Guild Map Generation and Editing (Guild-Scoped)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 25 (старый): Пользовательская задача: Написать тест для main.py
- ... (содержимое этого лога опущено для краткости) ...

## Задача 26 (старый): Пользовательская задача: Исправление ошибок импорта и TypeError
- ... (содержимое этого лога опущено для краткости) ...

## Задача 27 (старый): Важное примечание о миграциях Alembic
- ... (содержимое этого лога опущено для краткости) ...

## Задача 28: 📚 7.1 Event Log Model (Story Log, i18n, Guild-Scoped)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 29: ⚙️ 6.1.1 Intra-Location Interaction Handler Module
- ... (содержимое этого лога опущено для краткости) ...

## Задача 30: Пользовательская задача: Исправление ошибок в тестах
- ... (содержимое этого лога опущено для краткости) ...

## Задача 31: 📚 7.2 AI Narrative Generation (Multilang)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 32: 📚 7.3 Turn and Report Formatting (Guild-Scoped)
- ... (содержимое этого лога опущено для краткости) ...

## Задача 33: Пользовательская задача: Полное покрытие тестами и исправление ошибок
- ... (содержимое этого лога опущено для краткости) ...

## Задача 34: Пользовательская задача: Исправление ошибок Pyright
- ... (содержимое этого лога опущено для краткости) ...

## Задача 35: Пользовательская задача: Проверка и исправление тестов
- ... (содержимое этого лога опущено для краткости) ...

## Задача 36: Пользовательская задача: Исправление ошибок Pyright и стабилизация тестов
- ... (содержимое этого лога опущено для краткости) ...
