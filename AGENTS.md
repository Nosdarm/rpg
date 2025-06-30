## Инструкция для агента

1.  **Ознакомление с задачами:** Внимательно прочитать файл `tasks` для понимания всего объема работ.
2.  **Выбор задачи:** Взять одну задачу из файла `tasks` для реализации.
3.  **Планирование:**
    *   Создать детальный план для реализации выбранной задачи.
    *   Записать план в `AGENTS.md` в секцию "Текущий план".
4.  **Реализация:**
    *   Написать код для выполнения задачи.
    *   Создать или обновить необходимые файлы.
    *   Провести тестирование (если применимо).
5.  **Документирование действий:**
    *   Каждое значимое действие (создание файла, изменение функции, запуск тестов и т.д.) должно быть записано в `AGENTS.md` в секцию "Лог действий".
6.  **Завершение задачи:**
    *   После успешной реализации и тестирования, записать выполненную задачу в файл `done.txt`.
    *   Удалить выполненную задачу из файла `tasks`.
7.  **Повторение:** Вернуться к шагу 2, если в файле `tasks` остались невыполненные задачи.
8.  **Отправка изменений:** После выполнения всех задач, отправить изменения с соответствующим коммитом.

## Лог действий

(Здесь будут записываться действия)
- Попытка создать директории проекта (`src/bot`, `src/core`, `src/models`, `src/utils`, `src/config`, `tests/`) с помощью `mkdir`. (Неудачно, директории не создались).
- Принято решение создавать файлы напрямую, так как `create_file_with_block` должен создавать родительские директории.
- Созданы основные файлы проекта:
    - `src/main.py`
    - `src/bot/core.py`
    - `src/bot/events.py`
    - `src/bot/commands.py`
    - `src/config/settings.py`
    - `requirements.txt`
    - `.gitignore`
    - `src/bot/__init__.py`
    - `src/config/__init__.py`
    - `src/__init__.py`
    - `tests/__init__.py`
- Директории `src/core/`, `src/models/`, `src/utils/` пока не содержат файлов, но пути для них существуют благодаря созданию `src/__init__.py` и других файлов в `src/`. Они будут наполняться по мере реализации соответствующих задач.
- Реализована базовая структура `BotCore` в `src/bot/core.py`:
    - Конструктор `__init__` принимает `command_prefix` и `intents`.
    - Метод `setup_hook` для асинхронной настройки и загрузки расширений (когов).
    - Реализована загрузка когов `bot.events` и `bot.commands` с обработкой возможных ошибок.
    - Метод `on_ready` для логирования информации о подключении бота и серверах.
- Реализованы обработчики основных событий Discord в `src/bot/events.py` в виде `EventCog`:
    - `on_ready`: Логирование.
    - `on_message`: Базовая обработка (игнор самого себя).
    - `on_guild_join`: Логирование и попытка отправки приветственного сообщения.
    - `on_guild_remove`: Логирование.
    - `on_command_error`: Базовый обработчик ошибок команд.
- Реализована команда `/ping` (текстовая команда, префикс зависит от конфигурации) в `src/bot/commands.py` в виде `CommandCog`:
    - Команда `ping_command` отвечает задержкой бота.
    - Включает логирование вызова команды.
- Настроено логирование:
    - Базовая конфигурация `logging.basicConfig` в `src/main.py`.
    - Формат логирования: `%(asctime)s:%(levelname)s:%(name)s: %(message)s`.
    - Уровень логирования теперь устанавливается из переменной `LOG_LEVEL` в `src/config/settings.py` (по умолчанию INFO).
- Задача 0.1 (Discord Bot Project Initialization and Basic Guild Integration) записана как выполненная в `Done.txt`.
- Задача 0.1 удалена из файла `Tasks.txt`.
- **Задача 0.2 Шаг 1: Определена базовая модель `GuildConfig`**
    - Создан `src/models/base.py` с классом `Base(AsyncAttrs, DeclarativeBase)`.
    - Создан `src/models/guild.py` с моделью `GuildConfig`, включающей поля: `id` (PK, BigInteger), `master_channel_id` (BigInteger, nullable), `system_channel_id` (BigInteger, nullable), `notification_channel_id` (BigInteger, nullable), `main_language` (Text, default 'en').
    - Создан `src/models/__init__.py` для импорта `Base` и моделей (пока только `GuildConfig`), чтобы Alembic мог их обнаружить.
- **Задача 0.2 Шаг 2: Обновлен `requirements.txt`**
    - Добавлены зависимости: `SQLAlchemy>=2.0.20`, `asyncpg>=0.27.0`, `alembic>=1.11.0`.
- **Задача 0.2 Шаг 3: Настроено подключение к БД в `src/config/settings.py`**
    - Добавлены переменные окружения: `DB_TYPE`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` с значениями по умолчанию.
    - Сформирована строка `DATABASE_URL` для `postgresql+asyncpg`.
    - Добавлены информационные сообщения при отсутствии переменных окружения для БД.
    - Обновлен пример `.env` файла.
- **Задача 0.2 Шаг 4: Создан модуль `src/core/database.py` для управления БД**
    - Реализован асинхронный `engine` SQLAlchemy.
    - Реализована фабрика асинхронных сессий `AsyncSessionLocal`.
    - Реализована функция-генератор `get_db_session` для получения сессии с автоматическим commit/rollback/close.
    - Реализована функция `init_db` для создания таблиц на основе метаданных моделей (для первоначальной настройки).
    - Создан `src/core/__init__.py`.
- **Задача 0.2 Шаг 5: Интегрирована `init_db` в `src/main.py`**
    - `init_db()` теперь вызывается в функции `main()` перед запуском бота для создания таблиц, если они отсутствуют.
    - Добавлена обработка ошибок на случай проблем с инициализацией БД.
- **Задача 0.2 Шаг 6: Настроен Alembic для управления миграциями**
    - Выполнена команда `pip install -r requirements.txt` для установки зависимостей, включая `alembic`.
    - Инициализирован Alembic (`alembic init alembic`).
    - Настроен `alembic.ini`: `sqlalchemy.url` теперь будет браться из `env.py`.
    - Настроен `alembic/env.py`:
        - Добавлен путь к `src` в `sys.path`.
        - Импортирован `DATABASE_URL` из `src.config.settings` и установлен как `sqlalchemy.url`.
        - `target_metadata` установлен в `Base.metadata` из `src.models`.
        - Функция `run_migrations_online` адаптирована для работы с асинхронным движком SQLAlchemy.
    - Создана первая миграция `alembic/versions/init_0001_create_guild_configs_table.py` вручную для таблицы `guild_configs` из-за отсутствия БД в среде выполнения для автогенерации. Индекс для `id` сделан уникальным.
- **Задача 0.2 (DBMS Setup and Database Model Definition with Guild ID) записана как выполненная в `Done.txt`**.
- **Задача 0.2 удалена из файла `Tasks.txt`**.
- **Задача 0.3 Шаг 1: Анализ требований к Задаче 0.3** (Выполнено)
    - Проанализированы требования: низкоуровневые функции БД с учетом гильдии, управление сессиями ORM, декоратор транзакций, CRUD-утилиты, модель RuleConfig и утилиты для работы с ней (включая кеширование).
- **Задача 0.3 Шаг 2: Определена модель `RuleConfig`** (Выполнено)
    - Создан файл `src/models/rule_config.py` с моделью `RuleConfig`.
    - Модель включает поля: `id` (PK), `guild_id` (FK к `GuildConfig`), `key` (TEXT), `value_json` (JSONB).
    - Добавлен составной уникальный индекс для (`guild_id`, `key`).
    - Обновлен `src/models/__init__.py` для включения `RuleConfig`.
- **Задача 0.3 Шаг 3: Создана новая миграция Alembic для `RuleConfig`** (Выполнено)
    - Создан файл миграции `alembic/versions/0002_create_rule_configs_table.py`.
    - Миграция включает создание таблицы `rule_configs` с соответствующими полями, индексами и внешним ключом.
- **Задача 0.3 Шаг 4: Реализован декоратор `@transactional`** (Выполнено)
    - В `src/core/database.py` добавлен декоратор `@transactional`.
    - Декоратор использует `get_db_session` для управления жизненным циклом сессии (commit, rollback, close) и внедряет сессию в декорируемую функцию.
- **Задача 0.3 Шаг 5: Реализованы общие CRUD-утилиты** (Выполнено)
    - Создан файл `src/core/crud.py`.
    - Реализован класс `CRUDBase[ModelType]` с методами: `create`, `get`, `get_multi`, `update`, `delete`, `get_by_attribute`, `get_multi_by_attribute`.
    - Реализованы общие функции: `create_entity`, `get_entity_by_id`, `update_entity`, `delete_entity`, использующие `CRUDBase`.
    - Утилиты поддерживают `guild_id` для операций с моделями, имеющими это поле.
    - Обновлен `src/core/__init__.py` для включения модуля `crud`.
- **Задача 0.3 Шаг 6: Реализованы утилиты для `RuleConfig`** (Выполнено)
    - Создан файл `src/core/rules.py`.
    - Реализованы функции: `load_rules_config_for_guild` (загрузка и кеширование всех правил гильдии), `get_rule` (получение правила из кеша с загрузкой при необходимости), `update_rule_config` (обновление/создание правила в БД и обновление кеша), `get_all_rules_for_guild` (получение всех правил гильдии из кеша).
    - Используется простой внутрипроцессный словарь для кеширования правил (`_rules_cache`).
    - Обновлен `src/core/__init__.py` для включения модуля `rules`.
- **Задача 1.1 Шаг 1: Анализ требований для Location Model** (Выполнено)
    - Проанализированы поля модели `Location` (guild_id, static_id, i18n поля, JSONB поля), необходимость ENUM для типа локации, и утилиты (`get_location`, `get_static_location_id`, `get_localized_text`).
- **Задача 1.1 Шаг 2: Определена модель `Location`** (Выполнено)
    - Создан `src/models/location.py` с моделью `Location` и enum `LocationType`.
    - Включены все необходимые поля, JSONB для i18n и других структурированных данных, ForeignKey к `guild_configs`.
    - Добавлен уникальный индекс для `(guild_id, static_id)`.
- **Задача 1.1 Шаг 3: Обновлен `src/models/__init__.py`** (Выполнено)
    - Модель `Location` и enum `LocationType` добавлены в импорты и логгер в `src/models/__init__.py`.
- **Задача 1.1 Шаг 4: Создана миграция Alembic для `Location`** (Выполнено)
    - Создан файл миграции `alembic/versions/0003_create_locations_table.py`.
    - Миграция включает создание таблицы `locations`, соответствующих индексов, внешнего ключа, и обработку ENUM типа `locationtype`.
- **Задача 1.1 Шаг 5: Реализованы базовые CRUD-функции для `Location`** (Выполнено)
    - Создан `src/core/crud/crud_location.py` с классом `CRUDLocation(CRUDBase[Location])`.
    - Реализованы методы `get_by_static_id` и `get_locations_by_type`.
    - Создан `src/core/crud/__init__.py` для экспорта `location_crud`.
- **Задача 1.1 Шаг 6: Реализованы утилиты `get_location` и `get_static_location_id`** (Выполнено)
    - Создан `src/core/locations_utils.py`.
    - Реализованы функции `get_location` (обертка над `location_crud.get`) и `get_location_by_static_id` (обертка над `location_crud.get_by_static_id`).
    - Обновлен `src/core/__init__.py` для включения `locations_utils`.
- **Задача 1.1 Шаг 7: Реализована утилита для получения локализованного текста** (Выполнено)
    - Функция `get_localized_text` реализована в `src/core/locations_utils.py`.
    - Утилита обрабатывает поиск по языку, fallback-языку, и возвращает первый доступный перевод или пустую строку. Добавлено логирование.
- **Задача 1.1 Шаг 8: Обновлен обработчик `on_guild_join`** (Выполнено)
    - В `src/bot/events.py` обновлен метод `on_guild_join` и добавлен вспомогательный метод `_ensure_guild_config_exists` и `_populate_default_locations`.
    - Добавлена логика для создания записи `GuildConfig` (если не существует) и установки правила `guild_main_language` через `update_rule_config`.
    - Добавлена логика для создания дефолтных статичных локаций (`DEFAULT_STATIC_LOCATIONS`) для новой гильдии, если они еще не существуют.
    - Используется `get_db_session` для управления сессией БД.
- **Задача 1.2 Шаг 1: Анализ требований для Player and Party System** (Выполнено)
    - Проанализированы модели Player и Party, их поля, Enum-типы для статусов, логика команд `/start` и `/party`, а также необходимые утилиты.
    - Исправлена аннотация типа для `get_db_session` в `src/core/database.py`.
- **Задача 1.2 Шаг 2: Определены Enum'ы `PlayerStatus` и `PartyTurnStatus`** (Выполнено)
    - Создан `src/models/enums.py` с определениями `PlayerStatus` и `PartyTurnStatus`.
    - `src/models/__init__.py` обновлен для их экспорта.
- **Задача 1.2 Шаг 3: Определена модель `Player`** (Выполнено)
    - Создан `src/models/player.py` с моделью `Player`.
    - Включены все поля, FK, UniqueConstraint(`guild_id`, `discord_id`), Enum `PlayerStatus`, и отношения к `Location` и `Party`.
- **Задача 1.2 Шаг 4: Определена модель `Party`** (Выполнено)
    - Создан `src/models/party.py` с моделью `Party`.
    - Включены все поля, FK, Enum `PartyTurnStatus`, JSON-поле `player_ids_json`, и отношения к `Location` и `Player`.
- **Задача 1.2 Шаг 5: Обновлен `src/models/__init__.py`** (Выполнено)
    - Модели `Player` и `Party` добавлены в импорты `src/models/__init__.py`.
- **Задача 1.2 Шаг 6: Создана миграция Alembic для `Player` и `Party`** (Выполнено)
    - Создан файл миграции `alembic/versions/0004_create_players_and_parties_tables.py`.
    - Миграция включает создание таблиц `parties` и `players`, соответствующих ENUM-типов, индексов, FK и UniqueConstraint.
- **Задача 1.2 Шаг 7: Реализованы CRUD-классы `CRUDPlayer` и `CRUDParty`** (Выполнено)
    - Созданы `src/core/crud/crud_player.py` и `src/core/crud/crud_party.py`.
    - `CRUDPlayer` включает `get_by_discord_id`, `get_multi_by_location`, `get_multi_by_party_id`, `create_with_defaults`.
    - `CRUDParty` включает `get_by_name`, `add_player_to_party_json`, `remove_player_from_party_json`.
    - `src/core/crud/__init__.py` обновлен для их экспорта.
- **Задача 1.2 Шаг 8: Реализованы утилиты для Player и Party** (Выполнено)
    - Создан `src/core/player_utils.py` (с `get_player`, `get_player_by_discord_id`, `get_players_in_location`, `get_players_in_party`).
    - Создан `src/core/party_utils.py` (с `get_party`, `get_party_by_name`).
    - `src/core/__init__.py` обновлен для их экспорта.
- **Задача 1.2 Шаг 9: Реализована команда `/start`** (Выполнено)
    - Команда `/start` добавлена в `src/bot/commands.py` (в `CommandCog`).
    - Реализована логика проверки существующего игрока, создания нового игрока с дефолтной локацией и начальными параметрами.
- **Задача 1.2 Шаг 10: Реализованы команды для Party** (Выполнено)
    - Создан `src/bot/commands/party_commands.py` с `PartyCog`.
    - Реализованы команды: `/party create <название>`, `/party leave`, `/party disband`.
    - `src/bot/core.py` обновлен для загрузки `party_commands` Cog.

## Текущий план

Задача "🌍 1.2 Player and Party System (ORM, Commands, Guild-Scoped)" завершена.
Следующая задача согласно `Tasks.txt`: "🌍 1.3 Movement Logic (Player/Party, Guild-Scoped). (4, 5, 0.3, 14)"

1.  **Анализ требований Задачи 1.3 (Movement Logic):**
    *   API функция: `handle_move_action(guild_id: int, player_id: int, target_location_identifier: str)`.
        *   Принимает `guild_id`.
        *   Загружает `Player` (с `guild_id`).
        *   Определяет текущую локацию и целевую локацию (`target_location_identifier` может быть `static_id` или, возможно, локализованным именем).
        *   Проверяет связи между локациями (из `Location.neighbor_locations_json`).
        *   Если игрок в группе: проверяет правила движения группы (из `RuleConfig`).
        *   В ОДНОЙ ТРАНЗАКЦИИ (0.3), оперируя ТОЛЬКО ДАННЫМИ ВНУТРИ `guild_id`:
            *   Обновляет локацию игрока (и группы, если применимо).
            *   Логирует событие движения (19) С ЭТИМ `guild_id`.
        *   После коммита: Асинхронно вызывает `on_enter_location(guild_id, entity_id, entity_type, target_location_id)` (14 - это другая задача, пока что можно просто заглушку или лог).
    *   MVP: Связать с командой `/move`. NLU (10/12) будет передавать `guild_id`.
2.  **Создать API функцию `handle_move_action`** в новом файле, например, `src/core/movement_logic.py`.
    *   Эта функция будет использовать `get_db_session` и CRUD операции.
    *   Реализовать логику поиска текущей и целевой локации (сначала по `static_id`).
    *   Реализовать проверку `Location.neighbor_locations_json`.
    *   Реализовать обновление `Player.current_location_id`. Если игрок в партии, то обновить и `Party.current_location_id`.
    *   Обернуть обновление БД в транзакцию (можно использовать `@transactional`).
3.  **Реализовать команду `/move <target_location_static_id>`** в `src/bot/commands/general_commands.py` (или в новом Cog `movement_commands.py`).
    *   Команда должна вызывать `handle_move_action`.
    *   Предоставлять обратную связь пользователю (успех, ошибка, нет пути и т.д.).
4.  **Продумать правила движения для группы** (RuleConfig):
    *   Какие правила могут быть? (например, "все должны согласиться", "лидер решает", "любой может инициировать").
    *   Для MVP можно сделать просто: если игрок в группе, то вся группа перемещается.
5.  **Заглушка для `on_enter_location`**:
    *   Создать пустую async функцию `on_enter_location(guild_id, entity_id, entity_type, location_id)` в `src/core/game_events.py` (новый файл) и просто логировать вызов.
6.  **Обновить `AGENTS.md`**.
7.  **Записать выполненную задачу в `Done.txt`**.
8.  **Удалить выполненную задачу из `Tasks.txt`**.
