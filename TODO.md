# TODO List

This file tracks all the TODO comments found in the project.

## Backend TODOs

### Core System TODOs

*   `backend/core/ability_system.py:83`: Implement checks (resources, cooldowns, conditions based on RuleConfig)
*   `backend/core/ability_system.py:84`: Implement effects (damage, healing, status application based on db_ability.properties_json and RuleConfig)
*   `backend/core/ability_system.py:85`: Update caster and target states
*   `backend/core/ability_system.py:86`: Call log_event
*   `backend/core/ability_system.py:271`: Implement check for ability availability for the caster (e.g., learned abilities)
*   `backend/core/ability_system.py:272`: Implement cooldown checks
*   `backend/core/ability_system.py:273`: Implement resource checks (mana, stamina, etc.)
*   `backend/core/ability_system.py:274`: Implement target validation (e.g., range, line of sight, target type) based on `db_ability.properties_json` and `RuleConfig`.
*   `backend/core/ability_system.py:275`: Implement checks for prerequisites (e.g., character state, equipment).
*   `backend/core/ability_system.py:431`: Add stackable logic here if db_status_effect.properties_json.get("stackable", False)
*   `backend/core/action_processor.py:512`: Implement NPC name to ID lookup if NLU provides name
*   `backend/core/action_processor.py:516`: Implement NPC name to ID lookup
*   `backend/core/action_processor.py:977`: Send feedback reports to players/master based on processed_actions_results
*   `backend/core/ai_orchestrator.py:573`: More robust logic: check if there are OTHER pending_generations for this player.
*   `backend/core/combat_cycle_manager.py:483`: Here, process round-based effects (e.g., status effect durations, cooldowns decrement)
*   `backend/core/command_utils.py:17`: For localization (import get_localized_text)
*   `backend/core/command_utils.py:18`: For localization context (import get_rule)
*   `backend/core/command_utils.py:68`: Обработать choices, если они есть (param.choices)
*   `backend/core/command_utils.py:81`: Add `choices` to CommandParameterInfo model if needed
*   `backend/core/command_utils.py:116`: Обработка информации о guild_only / nsfw / default_permissions / dm_permission
*   `backend/core/dialogue_system.py:164`: Проверка, не занят ли NPC другим диалогом (если NPC могут говорить только с одним)
*   `backend/core/global_entity_manager.py:146`: Trigger goal reached logic (e.g., set new goal, go idle)
*   `backend/core/global_entity_manager.py:413`: Expand MobileGroup members into participants list if one of the entities was a MobileGroup
*   `backend/core/interaction_handlers.py:229`: Implement actual application of consequences based on consequences_key
*   `backend/core/interaction_handlers.py:244`: Implement actual application of direct consequences
*   `backend/core/movement_logic.py:285`: Consider searching other keys in name_i18n if no match in priority languages, though this might be too broad.
*   `backend/core/npc_combat_strategy.py:407`: Log this malformed participant entry
*   `backend/core/npc_memory_system.py:54`: Optional: Validate existence of guild_id, npc_id, player_id/party_id
*   `backend/core/quest_system.py:285`: Provide feedback to player about new step
*   `backend/core/quest_system.py:307`: Check for next quest in questline if quest.questline_id is set and quest.questline relationship is loaded.
*   `backend/core/relationship_system.py:15`: Implement the API and helper functions as per the plan.
*   `backend/core/relationship_system.py:263`: Consider if this function should return the updated/created Relationship object.
*   `backend/core/relationship_system.py:264`: Advanced: Handle rules that might trigger changes between factions of entities, not just direct entities.
*   `backend/core/trade_system.py:229`: Implement actual logic based on the plan

### Bot Command TODOs

*   `backend/bot/api/commands_api.py:118`: Этот роутер нужно будет добавить в основное приложение FastAPI в main.py
*   `backend/bot/commands/general_commands.py:40`: Вывести более подробную информацию об игроке, если он уже существует
*   `backend/bot/commands/master_admin_commands.py:604`: Add `resolved_action_json` later if needed for custom resolved action.
*   `backend/bot/commands/master_admin_commands.py:611`: `resolved_action_json: Optional[str] = None`
*   `backend/bot/commands/master_admin_commands.py:676`: Parse `resolved_action_json` if provided and `outcome_status` is `RESOLVED_BY_MASTER_CUSTOM_ACTION`
*   `backend/bot/commands/master_admin_commands.py:1629`: Consider showing inventory items if relevant and if InventoryItem CRUD exists and is easy to integrate.
*   `backend/bot/commands/master_admin_commands.py:2067`: Consider related data for Character view.
*   `backend/bot/commands/master_admin_commands.py:3731`: Consider other dependencies like Relationships involving this faction.
*   `backend/bot/commands/master_admin_commands.py:4021`: Validate `source_log_id` if provided (check if StoryLog entry exists)
*   `backend/bot/commands/master_admin_commands.py:4675`: Optionally list QuestSteps associated with this quest.
*   `backend/bot/commands/master_admin_commands.py:6765`: Add checks for dependencies (e.g., if ability is used in RuleConfig, by characters, etc.)
*   `backend/bot/commands/master_ai_commands.py:213`: More robust check if this was the *only* pending item for the player.
*   `backend/bot/commands/turn_commands.py:106`: Implement RuleConfig check for who can end party turn (e.g., leader_only or any_member)

### Model TODOs

*   `backend/models/command_info.py:11`: Add localized descriptions if available/needed
*   `backend/models/command_info.py:12`: Consider choices for parameters
*   `backend/models/command_info.py:20`: Add localized name/description if available/needed
*   `backend/models/command_info.py:21`: Consider how to represent subcommands/groups
*   `backend/models/command_info.py:22`: Add information about whether the command is guild_only or global
*   `backend/models/enums.py:115`: Add more event types as needed for other modules

## Frontend TODOs

*   `frontend/src/app/router.tsx:57`: Добавить маршруты для других разделов
*   `frontend/src/pages/DashboardPage.tsx:36`: Загрузить и отобразить количество активных игроков
*   `frontend/src/pages/DashboardPage.tsx:62`: Загрузить и отобразить количество NPC
*   `frontend/src/pages/DashboardPage.tsx:82`: Загрузить и отобразить количество активных квестов
*   `frontend/src/pages/DashboardPage.tsx:94`: Добавить кнопки для частых действий, например, "Создать NPC", "Просмотреть логи"

## Testing TODOs

*   `tests/bot/commands/master_commands/test_master_conflict_commands.py:254`: Add more tests for other aspects of conflict_resolve, list, view commands
*   `tests/core/test_ability_system.py:312`: Many TODOs from previous block still apply and will be implemented incrementally
*   `tests/core/test_combat_cycle_manager.py:312`: Add tests for player party status updates during start_combat
*   `tests/core/test_combat_cycle_manager.py:415`: test_process_combat_turn_player_action_advances_turn (if player action already processed)
*   `tests/core/test_combat_cycle_manager.py:416`: test_process_combat_turn_combat_ends
*   `tests/core/test_combat_cycle_manager.py:417`: test_process_combat_turn_active_entity_defeated_skips_action
*   `tests/core/test_combat_cycle_manager.py:418`: test_process_combat_turn_recursive_npc_turns
*   `tests/core/test_global_entity_manager.py:262`: Add more tests for global entity manager.
*   `tests/core/test_movement_logic.py:725`: Add test for name search once implemented

## Documentation / Update Notes TODOs

*   `updates.txt:189` (Action Processor Gaps): Pre-execution conflict analysis for the *current batch* of actions is missing. Mechanism for quest system to get `StoryLog` ID of the action is potentially fragile. Aggregated feedback/report generation is a TODO.
*   `updates.txt:194` (Interaction System Gaps): Does not handle all specified interaction intents. Critical: Application of consequences from `RuleConfig` is **not implemented** (TODOs exist). Prerequisite checks missing. Feedback not localized via main i18n system.
*   `updates.txt:279` (Quest System Gaps): Detailed mechanic matching via `RuleConfig` not implemented. Abstract goal evaluation logic (LLM/rule-based) is placeholder. Item/WorldState consequence application is placeholder. Quest failure/abandonment handling missing. Triggering next quest in questline is TODO.
*   `updates.txt:335` (Experience System Gaps): `award_xp` expects pre-calculated XP amount, doesn't use `RuleConfig:experience_system:xp_gain_rules`. Party XP distribution is basic even split. Level up rewards limited to `unspent_xp` (no direct skill/ability grants). Player notifications for level up are TODOs.
*   `updates.txt:355` (Global Entity Manager Gaps): Periodic multi-guild worker mechanism not in this module. `GlobalEvent` lifecycle management missing. Movement simulation is basic (no pathfinding/speed/time). Goal update logic basic. Complex interaction outcomes (quests, full dialogue) are placeholders. `MobileGroup` member handling in combat/interactions is TODO.

## History TODOs (Potentially Obsolete - Review Needed)

*   `.history/AGENTS_20250703110228.md:219`: `target_location_identifier` по `static_id`. Добавлен `TODO` для поиска по имени.
*   `.history/AGENTS_20250703110228.md:228`: В `execute_move_for_player_action` добавлен комментарий `TODO` для будущей интеграции `RuleConfig` для политик движения партии.
*   `.history/AGENTS_20250703110228.md:451`: Документация (docstrings, комментарии) добавлена в `src/core/check_resolver.py`, отмечены TODO для будущих улучшений.
*   `.history/AGENTS_20250703115246.md:236`: `target_location_identifier` по `static_id`. Добавлен `TODO` для поиска по имени.
*   `.history/AGENTS_20250703115246.md:245`: В `execute_move_for_player_action` добавлен комментарий `TODO` для будущей интеграции `RuleConfig` для политик движения партии.
*   `.history/AGENTS_20250703115246.md:468`: Документация (docstrings, комментарии) добавлена в `src/core/check_resolver.py`, отмечены TODO для будущих улучшений.
*   `.history/AGENTS_20250704142953.md:115`: Добавлены комментарии-TODO для более сложных проверок (доступность способности кастеру, кулдауны).
*   `.history/AGENTS_20250709203538.md:878`: Сформулированы TODO и подходы для интеграции влияния отношений в эти системы.
*   `.history/AGENTS_20250709203538.md:1203`: Распределение XP: для партии XP делится поровну (TODO: использовать правила из `RuleConfig`).
*   `.history/AGENTS_20250709203538.md:1453`: Добавлены комментарии-TODO для более сложных проверок (доступность способности кастеру, кулдауны).
*   `.history/AGENTS_20250710020931.md:1033`: Сформулированы TODO и подходы для интеграции влияния отношений в эти системы.
*   `.history/AGENTS_20250710020931.md:1358`: Распределение XP: для партии XP делится поровну (TODO: использовать правила из `RuleConfig`).
*   `.history/AGENTS_20250710020931.md:1608`: Добавлены комментарии-TODO для более сложных проверок (доступность способности кастеру, кулдауны).
*   `.history/AGENTS_20250710020939.md:1033`: Сформулированы TODO и подходы для интеграции влияния отношений в эти системы.
*   `.history/AGENTS_20250710020939.md:1358`: Распределение XP: для партии XP делится поровну (TODO: использовать правила из `RuleConfig`).
*   `.history/AGENTS_20250710020939.md:1608`: Добавлены комментарии-TODO для более сложных проверок (доступность способности кастеру, кулдауны).
*   `.history/src/bot/api/commands_api_20250704203856.py:100`: Этот роутер нужно будет добавить в основное приложение FastAPI в main.py
*   `.history/src/bot/api/commands_api_20250704204119.py:100`: Этот роутер нужно будет добавить в основное приложение FastAPI в main.py
*   `.history/src/bot/commands/general_commands_20250703102257.py:36`: Вывести более подробную информацию об игроке, если он уже существует
*   `.history/src/bot/commands/general_commands_20250703102447.py:37`: Вывести более подробную информацию об игроке, если он уже существует
*   `.history/src/bot/commands/master_admin_commands_20250706195023.py:342`: `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706195023.py:349`: `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706195023.py:391`: Parse `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706195151.py:343`: `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706195151.py:350`: `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706195151.py:392`: Parse `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706195216.py:393`: `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706195216.py:406`: `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706195216.py:452`: Parse `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706200346.py:577`: `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706200346.py:584`: `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706200346.py:641`: Parse `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706210824.py:584`: `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706210824.py:591`: `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706210824.py:653`: Parse `resolved_action_json`
*   `.history/src/bot/commands/master_admin_commands_20250706210824.py:1528`: Consider showing inventory items.
*   `.history/src/bot/commands/master_admin_commands_20250706210824.py:1940`: Consider related data.
*   `.history/src/bot/commands/master_admin_commands_20250706210824.py:3538`: Consider other dependencies like Relationships.
*   `.history/src/bot/commands/master_admin_commands_20250706210824.py:3818`: Validate `source_log_id`.
*   `.history/src/bot/commands/master_admin_commands_20250706210824.py:4442`: Optionally list QuestSteps.
*   `.history/src/bot/commands/master_admin_commands_20250706210824.py:6485`: Add checks for dependencies for ability deletion.
*   `.history/src/bot/commands/master_ai_commands_20250701185028.py:204`: More robust check if this was the *only* pending item for the player.
*   `.history/src/bot/commands/turn_commands_20250701185017.py:113`: Implement RuleConfig check for who can end party turn.
*   `.history/src/bot/commands/turn_commands_20250701185050.py:97`: Implement RuleConfig check for who can end party turn.
*   `.history/src/core/ability_system_20250703230220.py:83`: Implement checks (resources, cooldowns, conditions).
*   `.history/src/core/ability_system_20250703230220.py:84`: Implement effects (damage, healing, status application).
*   `.history/src/core/ability_system_20250703230220.py:85`: Update caster and target states.
*   `.history/src/core/ability_system_20250703230220.py:86`: Call log_event.
*   `.history/src/core/ability_system_20250703230220.py:267`: Implement check for ability availability.
*   `.history/src/core/ability_system_20250703230220.py:268`: Implement cooldown checks.
