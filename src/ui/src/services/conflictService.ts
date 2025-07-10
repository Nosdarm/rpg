import { PaginatedResponse } from "../types/entities";
import {
  UIConflictDetails,
  UIConflictListItem,
  UIConflictStatus,
  UIMasterOutcomeOption,
  UIResolveConflictPayload,
  UIConflictInvolvedUnit,
  UIConflictActionEntity,
  UIConflictParsedAction,
} from "../types/conflict";

// Mock data generators
const mockPlayerActionEntity = (id: number, name: string): UIConflictActionEntity => ({
  type: "player",
  id,
  name,
});

const mockNpcActionEntity = (id: number, name: string): UIConflictActionEntity => ({
  type: "generated_npc",
  id,
  name,
});

const mockParsedAction = (intent: string, entities: UIConflictActionEntity[], rawText?: string): UIConflictParsedAction => ({
  intent,
  entities,
  raw_text: rawText || `${intent} on ${entities.map(e => e.name).join(", ")}`,
  details_json: {
    target_id: entities[0]?.id, // Example detail
  }
});

const mockInvolvedUnit = (actor: UIConflictActionEntity, action: UIConflictParsedAction): UIConflictInvolvedUnit => ({
  actor,
  action,
  original_action_id: Math.floor(Math.random() * 1000),
});


// Mock service implementations
export const getPendingConflicts = async (
  guildId: string,
  status?: UIConflictStatus,
  page: number = 1,
  limit: number = 10
): Promise<PaginatedResponse<UIConflictListItem>> => {
  console.log(`Mock API: getPendingConflicts for guild ${guildId}, status ${status}, page ${page}, limit ${limit}`);

  const allItems: UIConflictListItem[] = [
    { id: 1, status: UIConflictStatus.PENDING_MASTER_RESOLUTION, created_at: new Date().toISOString(), involved_entities_summary: "Player1 vs Player2" },
    { id: 2, status: UIConflictStatus.PENDING_MASTER_RESOLUTION, created_at: new Date(Date.now() - 3600000).toISOString(), involved_entities_summary: "Player3, Player4 action conflict" },
    { id: 3, status: UIConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION1, created_at: new Date(Date.now() - 7200000).toISOString(), involved_entities_summary: "System vs Player1" },
    { id: 4, status: UIConflictStatus.PENDING_MASTER_RESOLUTION, created_at: new Date(Date.now() - 10800000).toISOString(), involved_entities_summary: "NPC Guard vs Player Rogue" },
    { id: 5, status: UIConflictStatus.RESOLVED_BY_MASTER_DISMISS, created_at: new Date(Date.now() - 86400000).toISOString(), involved_entities_summary: "Old conflict" },
  ];

  const filteredItems = status ? allItems.filter(item => item.status === status) : allItems;
  const total_items = filteredItems.length;
  const total_pages = Math.ceil(total_items / limit);
  const startIndex = (page - 1) * limit;
  const endIndex = page * limit;
  const items = filteredItems.slice(startIndex, endIndex);

  return Promise.resolve({
    items,
    current_page: page,
    total_pages,
    total_items,
    limit_per_page: limit,
  });
};

export const getConflictDetails = async (
  guildId: string,
  conflictId: number
): Promise<UIConflictDetails> => {
  console.log(`Mock API: getConflictDetails for guild ${guildId}, conflict ${conflictId}`);

  const player1 = mockPlayerActionEntity(101, "PlayerAlpha");
  const player2 = mockPlayerActionEntity(102, "PlayerBeta");
  const npc1 = mockNpcActionEntity(201, "Goblin Sneak");

  const action1 = mockParsedAction("attack", [npc1], "PlayerAlpha attacks Goblin Sneak");
  const action2 = mockParsedAction("cast_heal", [player1], "PlayerBeta casts Heal on PlayerAlpha");
  const action3 = mockParsedAction("loot_chest", [mockNpcActionEntity(301, "Treasure Chest")], "Goblin Sneak tries to loot Treasure Chest");


  const details: UIConflictDetails = {
    id: conflictId,
    guild_id: guildId,
    involved_entities: [
      mockInvolvedUnit(player1, action1),
      mockInvolvedUnit(player2, action2),
    ],
    conflicting_actions: [ // Often this might be the same as involved_entities or a subset
      mockInvolvedUnit(player1, action1),
      mockInvolvedUnit(player2, action2),
    ],
    status: UIConflictStatus.PENDING_MASTER_RESOLUTION,
    created_at: new Date(Date.now() - 3600000).toISOString(),
    resolution_notes: conflictId === 3 ? "Resolved by favoring action 1 as it was initiated first." : undefined,
    resolved_action: conflictId === 3 ? action1 : undefined,
    resolved_at: conflictId === 3 ? new Date().toISOString() : undefined,
  };

  if (conflictId === 4) {
    details.involved_entities = [mockInvolvedUnit(npc1, action3), mockInvolvedUnit(player1, mockParsedAction("interfere", [npc1], "PlayerAlpha interferes with Goblin Sneak"))];
    details.conflicting_actions = details.involved_entities;
  }


  return Promise.resolve(details);
};

export const getConflictResolutionOutcomeOptions = async (
  guildId: string
): Promise<UIMasterOutcomeOption[]> => {
  console.log(`Mock API: getConflictResolutionOutcomeOptions for guild ${guildId}`);
  // These correspond to the valid master resolution statuses from backend
  // Names would be localized in the UI using the name_key
  const options: UIMasterOutcomeOption[] = [
    { id: UIConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION1, name_key: "conflict_resolution:outcome_favor_action1" },
    { id: UIConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION2, name_key: "conflict_resolution:outcome_favor_action2" }, // Assuming there's always an action2 if action1
    { id: UIConflictStatus.RESOLVED_BY_MASTER_CUSTOM_ACTION, name_key: "conflict_resolution:outcome_custom_action" },
    { id: UIConflictStatus.RESOLVED_BY_MASTER_DISMISS, name_key: "conflict_resolution:outcome_dismiss_conflict" },
    // RESOLVED_BY_MASTER_APPROVED and RESOLVED_BY_MASTER_REJECTED might be too generic if not tied to specific actions.
    // The current backend command expects one of the above or custom/dismiss.
  ];
  return Promise.resolve(options);
};

export const resolveConflict = async (
  guildId: string,
  conflictId: number,
  payload: UIResolveConflictPayload
): Promise<{ success: boolean; message?: string }> => {
  console.log(`Mock API: resolveConflict for guild ${guildId}, conflict ${conflictId}, payload:`, payload);
  if (!payload.outcome_status) {
    return Promise.resolve({ success: false, message: "Outcome status is required." });
  }
  // Simulate success
  return Promise.resolve({ success: true, message: `Conflict ${conflictId} resolved with status ${payload.outcome_status}. Notes: ${payload.notes || "N/A"}` });
};
