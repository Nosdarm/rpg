// src/ui/src/types/quest.ts

/**
 * Общий интерфейс для пагинированных ответов API.
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

/**
 * Локализованные строки (ключ - код языка, значение - текст).
 */
export type LocaleRecord = Record<string, string>;

/**
 * Произвольные JSON данные.
 */
export type JsonData = Record<string, any>;

/**
 * Данные для цепочки квестов (Questline).
 */
export interface QuestlineData {
  id: number;
  guild_id: string; // В API guild_id часто строка из-за больших чисел Discord ID
  static_id: string;
  title_i18n: LocaleRecord;
  description_i18n?: LocaleRecord | null;
  starting_quest_static_id?: string | null;
  is_main_storyline: boolean;
  required_previous_questline_static_id?: string | null;
  properties_json?: JsonData | null;
  created_at: string; // ISO datetime string
  updated_at: string; // ISO datetime string
}

/**
 * Пейлоад для создания/обновления Questline.
 * Для команды update используется field_to_update и new_value,
 * но UI может собирать полный объект и отправлять только измененные поля,
 * или использовать более гранулярный подход.
 * Этот Payload больше для создания.
 */
export interface QuestlinePayload {
  static_id: string;
  title_i18n_json: string; // JSON string of LocaleRecord
  description_i18n_json?: string; // JSON string of LocaleRecord
  starting_quest_static_id?: string;
  is_main_storyline?: boolean;
  prev_questline_id?: string; // static_id of previous questline
  properties_json?: string; // JSON string of JsonData
}

/**
 * Данные для генерируемого квеста (GeneratedQuest).
 */
export interface GeneratedQuestData {
  id: number;
  guild_id: string;
  static_id: string;
  title_i18n: LocaleRecord;
  description_i18n?: LocaleRecord | null;
  questline_id?: number | null;
  // giver_entity_type и giver_entity_id не управляются напрямую через CRUD UI по задаче
  // min_level также
  is_repeatable: boolean;
  rewards_json?: JsonData | null;
  properties_json?: JsonData | null; // Может содержать quest_type, difficulty и др.
  ai_metadata_json?: JsonData | null;
  created_at: string;
  updated_at: string;
  // UI может захотеть загружать шаги отдельно или вместе с квестом
  steps?: QuestStepData[];
}

/**
 * Пейлоад для создания/обновления GeneratedQuest.
 */
export interface GeneratedQuestPayload {
  static_id: string;
  title_i18n_json: string; // JSON string
  description_i18n_json?: string; // JSON string
  quest_type?: string; // Будет помещен в properties_json.quest_type
  questline_id?: number;
  is_repeatable?: boolean;
  properties_json?: string; // JSON string
  rewards_json?: string; // JSON string
}

/**
 * Данные для шага квеста (QuestStep).
 */
export interface QuestStepData {
  id: number;
  quest_id: number;
  step_order: number;
  title_i18n: LocaleRecord;
  description_i18n: LocaleRecord; // В модели not nullable, default {}
  required_mechanics_json?: JsonData | null;
  abstract_goal_json?: JsonData | null;
  consequences_json?: JsonData | null;
  next_step_order?: number | null;
  properties_json?: JsonData | null;
  created_at: string;
  updated_at: string;
}

/**
 * Пейлоад для создания/обновления QuestStep.
 */
export interface QuestStepPayload {
  quest_id: number;
  step_order: number;
  title_i18n_json: string; // JSON string
  description_i18n_json: string; // JSON string
  required_mechanics_json?: string; // JSON string
  abstract_goal_json?: string; // JSON string
  consequences_json?: string; // JSON string
  next_step_order?: number;
  properties_json?: string; // JSON string
}

/**
 * Статусы квеста (должны соответствовать Enum в бэкенде).
 */
export enum UIQuestStatus {
  NOT_STARTED = "NOT_STARTED",
  IN_PROGRESS = "IN_PROGRESS",
  COMPLETED = "COMPLETED",
  FAILED = "FAILED",
  CANCELLED = "CANCELLED", // Если есть такой статус
  ON_HOLD = "ON_HOLD" // Если есть
}

/**
 * Данные о прогрессе выполнения квеста игроком/партией (PlayerQuestProgress).
 */
export interface PlayerQuestProgressData {
  id: number;
  guild_id: string;
  player_id?: number | null;
  party_id?: number | null;
  quest_id: number;
  current_step_id?: number | null;
  status: UIQuestStatus; // Используем UIQuestStatus Enum
  progress_data_json?: JsonData | null;
  accepted_at?: string | null; // ISO datetime string
  completed_at?: string | null; // ISO datetime string
  created_at: string;
  updated_at: string;
}

/**
 * Пейлоад для создания PlayerQuestProgress.
 */
export interface PlayerQuestProgressPayload {
  quest_id: number;
  player_id?: number;
  party_id?: number;
  status?: UIQuestStatus;
  current_step_id?: number;
  progress_data_json?: string; // JSON string
  accepted_at_iso?: string; // ISO datetime string
}

/**
 * Пейлоад для обновления PlayerQuestProgress (попольное).
 * Используется в команде /master_quest progress_update
 */
export interface PlayerQuestProgressUpdatePayload {
  field_to_update: "status" | "current_step_id" | "progress_data_json";
  new_value: string; // Имя Enum для status, число для ID, JSON-строка для json, "None"
}
