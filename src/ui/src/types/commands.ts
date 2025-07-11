// src/ui/src/types/commands.ts

export interface UICommandParameterInfo {
  name: string;
  description?: string | null;
  type: string; // e.g., 'string', 'integer', 'boolean', 'user', 'channel'
  required: boolean;
  // choices?: Array<{ name: string; value: string | number }>; // TODO: Future enhancement
}

export interface UICommandInfo {
  name: string; // e.g., 'ping' or 'group subcommand'
  description?: string | null;
  parameters: UICommandParameterInfo[];
  // permissions?: string[]; // TODO: Future enhancement
  // guild_only?: boolean; // TODO: Future enhancement
}

export interface UICommandListResponse {
  commands: UICommandInfo[];
  language_code?: string | null;
}
