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

## Текущий план

Задача "🌍 1.1 Location Model (i18n, Guild-Scoped)" завершена.
Следующая задача согласно `Tasks.txt`: "🌍 1.2 Player and Party System (ORM, Commands, Guild-Scoped). (0.2, 0.3, 0.1)"

1.  **Анализ требований Задачи 1.2 (Player and Party System):**
    *   **Player Model:**
        *   Поля: `id` (PK, INTEGER), `guild_id` (BIGINT, Indexed, FK), `discord_id` (BIGINT, Indexed), `name` (TEXT), `current_location_id` (INTEGER FK to Location), `selected_language` (TEXT), `xp` (INT), `level` (INT), `unspent_xp` (INT), `gold` (INT), `current_status` (TEXT - enum), `collected_actions_json` (JSONB), `current_party_id` (INTEGER FK to Party, Nullable).
        *   Составной уникальный индекс: (`guild_id`, `discord_id`).
        *   Enum для `current_status` (e.g., "exploring", "combat", "dialogue").
    *   **Party Model:**
        *   Поля: `id` (PK, INTEGER), `guild_id` (BIGINT, Indexed, FK), `name` (TEXT), `player_ids_json` (JSONB - list of player PKs), `current_location_id` (INTEGER FK to Location), `turn_status` (TEXT - enum).
        *   Enum для `turn_status` (e.g., "pending_actions", "processing", "waiting_turn").
    *   **`/start` command:**
        *   Получает `guild_id` из контекста.
        *   Создает `Player` с этим `guild_id` (используя утилиты 0.3).
        *   Назначает стартовую локацию (ссылка на задачу 4 - Location Model, вероятно `static_id`).
        *   Устанавливает дефолтные статы, XP, уровень, статус 'exploring'.
    *   **`/party create/join/leave/disband` commands:**
        *   Управление `Party` в контексте гильдии.
        *   Все операции загрузки/изменения `Player`/`Party` должны использовать `guild_id` (утилиты 0.3).
    *   **Utilities:** `get_player(guild_id, player_id)`, `get_party(guild_id, party_id)`, `get_players_in_location(guild_id, location_id)`.
2.  **Определить Enum'ы** для `Player.current_status` и `Party.turn_status` в соответствующих файлах моделей или в общем файле enums.
3.  **Определить модель `Player` в `src/models/player.py`**:
    *   Реализовать все поля, FK, индексы.
4.  **Определить модель `Party` в `src/models/party.py`**:
    *   Реализовать все поля, FK, индексы.
5.  **Обновить `src/models/__init__.py`** для включения `Player` и `Party`.
6.  **Создать новые миграции Alembic** для моделей `Player` и `Party` (можно одной или двумя отдельными миграциями).
7.  **Реализовать CRUD-классы `CRUDPlayer` и `CRUDParty`** в `src/core/crud/` (например, `crud_player.py`, `crud_party.py`).
    *   Наследовать от `CRUDBase`.
    *   Добавить специфичные методы, если нужны (например, `get_player_by_discord_id`).
8.  **Реализовать утилиты `get_player`, `get_party`, `get_players_in_location`** (например, в `src/core/player_utils.py`, `src/core/party_utils.py`).
9.  **Реализовать команду `/start`** в `src/bot/commands/general_commands.py` (или создать новый Cog):
    *   Использовать `get_db_session`, CRUD операции, `location_crud` для поиска стартовой локации.
10. **Реализовать команды для управления Party** (`/party create`, `/party join`, `/party leave`, `/party disband`) в `src/bot/commands/party_commands.py` (или новом Cog).
11. **Обновить `AGENTS.md`**.
12. **Записать выполненную задачу в `Done.txt`**.
13. **Удалить выполненную задачу из `Tasks.txt`**.
