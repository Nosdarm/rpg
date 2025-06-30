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

## Текущий план

Задачи из "Phase 0: Architecture and Initialization (Foundation MVP)" завершены.
Следующая задача согласно `Tasks.txt`: "🌍 Phase 1: Game World (Static & Generated) - 🌍 1.1 Location Model (i18n, Guild-Scoped). (0.2)"

1.  **Анализ требований Задачи 1.1 (Location Model):**
    *   Модель `Location` привязана к гильдии (`guild_id`).
    *   Поддержка i18n для `name` и `descriptions` (JSONB).
    *   Поля: `id` (PK), `guild_id` (FK), `static_id` (TEXT, уникальный в пределах гильдии), `name_i18n` (JSONB), `descriptions_i18n` (JSONB), `type` (TEXT enum), `coordinates_json` (JSONB), `neighbor_locations_json` (JSONB - список `{location_id: connection_type_i18n}`), `generated_details_json` (JSONB), `ai_metadata_json` (JSONB).
    *   Популяция статическими данными при `on_guild_join` (ссылка на задачу 0.1).
    *   Утилиты: `get_location(guild_id, location_id)`, `get_static_location_id(guild_id, static_id)`.
    *   Утилита для получения локализованного текста (используя поля `_i18n` и fallback-языки из 0.1).
2.  **Определить модель `Location` в `src/models/location.py`**:
    *   Реализовать все перечисленные поля с соответствующими типами SQLAlchemy.
    *   Обеспечить корректные внешние ключи и индексы.
    *   Определить ENUM для поля `type` (например, `LocationType(Enum)`).
3.  **Обновить `src/models/__init__.py`** для включения модели `Location`.
4.  **Создать новую миграцию Alembic для модели `Location`**:
    *   Сгенерировать (или создать вручную) файл миграции.
    *   Добавить команды для создания таблицы `locations` и ее индексов.
5.  **Реализовать базовые CRUD-функции для `Location`**:
    *   Можно создать `CRUDLocation` класс, наследуемый от `CRUDBase` в `src/core/crud/crud_location.py` (или аналогичном месте).
    *   Реализовать специфичные для `Location` методы, если необходимо, например, `get_by_static_id_and_guild`.
6.  **Реализовать утилиты `get_location` и `get_static_location_id`**:
    *   Эти функции, вероятно, будут использовать CRUD-методы. Разместить их можно в `src/core/locations.py` или подобном модуле.
7.  **Реализовать утилиту для получения локализованного текста**:
    *   Функция `get_localized_text(entity_with_i18n_fields, field_name_base: str, language: str, fallback_language: str = 'en') -> str`.
    *   Эта утилита должна уметь извлекать текст из JSONB полей вида `name_i18n`, `description_i18n`.
8.  **Обновить обработчик `on_guild_join` (из Задачи 0.1, файл `src/bot/events.py`)**:
    *   Добавить логику для начального заполнения БД статическими данными о локациях для новой гильдии. (Это может потребовать определения этих статических данных где-то).
9.  **Обновить `AGENTS.md`**:
    *   Записать выполненные действия в "Лог действий".
    *   Установить следующий текущий план.
10. **Записать выполненную задачу в `Done.txt`**.
11. **Удалить выполненную задачу из `Tasks.txt`**.
