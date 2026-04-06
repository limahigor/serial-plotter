import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { extractServiceErrorMessage } from '$lib/services/shared/errorMessage';
import type {
  AppendConsoleLogInput,
  ConsoleAlertRule,
  ConsoleAlertTarget,
  ConsoleLogEntry,
  ConsoleLogLevel,
  ConsoleOverview,
  ConsolePlantOption,
  ListConsoleLogsFilters,
  SaveConsoleAlertRuleInput,
} from '$lib/types/console';

type ConsoleAlertTargetDto =
  | { type: 'app' }
  | { type: 'all_plants' }
  | { type: 'selected_plants'; plant_ids: string[] };

type ConsoleLogEntryDto = {
  id: string;
  timestamp: string;
  level: ConsoleLogLevel;
  message: string;
  source_scope: ConsoleLogEntry['sourceScope'];
  source_kind: ConsoleLogEntry['sourceKind'];
  plant_id?: string | null;
  plant_name?: string | null;
  runtime_id?: string | null;
  plugin_id?: string | null;
  plugin_name?: string | null;
  controller_id?: string | null;
  controller_name?: string | null;
  details?: ConsoleLogEntry['details'];
};

type ConsoleAlertRuleDto = {
  id: string;
  name: string;
  enabled: boolean;
  levels: ConsoleLogLevel[];
  target: ConsoleAlertTargetDto;
};

type ConsolePlantOptionDto = {
  plant_id: string;
  plant_name: string;
};

type ConsoleOverviewDto = {
  badge_count: number;
  rules: ConsoleAlertRuleDto[];
  known_plants: ConsolePlantOptionDto[];
  last_alert_read_at?: string | null;
};

type ConsoleBadgeEventDto = {
  badge_count: number;
};

type ConsoleEntriesEventDto = ConsoleLogEntryDto[];

function mapAlertTargetDto(target: ConsoleAlertTargetDto): ConsoleAlertTarget {
  if (target.type === 'selected_plants') {
    return {
      type: 'selected_plants',
      plantIds: target.plant_ids ?? [],
    };
  }

  return { type: target.type };
}

function mapAlertTargetToDto(target: ConsoleAlertTarget): ConsoleAlertTargetDto {
  if (target.type === 'selected_plants') {
    return {
      type: 'selected_plants',
      plant_ids: target.plantIds ?? [],
    };
  }

  return { type: target.type };
}

function mapLogEntry(dto: ConsoleLogEntryDto): ConsoleLogEntry {
  return {
    id: dto.id,
    timestamp: dto.timestamp,
    level: dto.level,
    message: dto.message,
    sourceScope: dto.source_scope,
    sourceKind: dto.source_kind,
    plantId: dto.plant_id ?? null,
    plantName: dto.plant_name ?? null,
    runtimeId: dto.runtime_id ?? null,
    pluginId: dto.plugin_id ?? null,
    pluginName: dto.plugin_name ?? null,
    controllerId: dto.controller_id ?? null,
    controllerName: dto.controller_name ?? null,
    details: dto.details ?? null,
  };
}

function mapAlertRule(dto: ConsoleAlertRuleDto): ConsoleAlertRule {
  return {
    id: dto.id,
    name: dto.name,
    enabled: dto.enabled,
    levels: dto.levels ?? [],
    target: mapAlertTargetDto(dto.target),
  };
}

function mapPlantOption(dto: ConsolePlantOptionDto): ConsolePlantOption {
  return {
    plantId: dto.plant_id,
    plantName: dto.plant_name,
  };
}

function mapOverview(dto: ConsoleOverviewDto): ConsoleOverview {
  return {
    badgeCount: dto.badge_count ?? 0,
    rules: (dto.rules ?? []).map(mapAlertRule),
    knownPlants: (dto.known_plants ?? []).map(mapPlantOption),
    lastAlertReadAt: dto.last_alert_read_at ?? null,
  };
}

export async function getConsoleOverview(): Promise<ConsoleOverview> {
  const response = await invoke<ConsoleOverviewDto>('get_console_overview');
  return mapOverview(response);
}

export async function listConsoleLogs(
  filters: ListConsoleLogsFilters = {},
): Promise<ConsoleLogEntry[]> {
  const response = await invoke<ConsoleLogEntryDto[]>('list_console_logs', {
    request: {
      levels: filters.levels ?? [],
      source_scope: filters.sourceScope ?? null,
      plant_id: filters.plantId ?? null,
      search: filters.search ?? null,
      limit: filters.limit ?? null,
    },
  });

  return response.map(mapLogEntry);
}

export async function appendConsoleLog(input: AppendConsoleLogInput): Promise<ConsoleLogEntry | null> {
  try {
    const response = await invoke<ConsoleLogEntryDto>('append_console_log', {
      request: {
        level: input.level,
        message: input.message,
        source_scope: input.sourceScope,
        source_kind: input.sourceKind,
        plant_id: input.plantId ?? null,
        plant_name: input.plantName ?? null,
        runtime_id: input.runtimeId ?? null,
        plugin_id: input.pluginId ?? null,
        plugin_name: input.pluginName ?? null,
        controller_id: input.controllerId ?? null,
        controller_name: input.controllerName ?? null,
        details: input.details ?? null,
      },
    });

    return mapLogEntry(response);
  } catch {
    return null;
  }
}

export async function saveConsoleAlertRule(input: SaveConsoleAlertRuleInput): Promise<ConsoleOverview> {
  try {
    const response = await invoke<ConsoleOverviewDto>('save_console_alert_rule', {
      request: {
        id: input.id ?? null,
        name: input.name,
        enabled: input.enabled,
        levels: input.levels ?? [],
        target: mapAlertTargetToDto(input.target),
      },
    });
    return mapOverview(response);
  } catch (error) {
    throw new Error(extractServiceErrorMessage(error, 'Erro ao salvar regra de alerta'));
  }
}

export async function deleteConsoleAlertRule(id: string): Promise<ConsoleOverview> {
  try {
    const response = await invoke<ConsoleOverviewDto>('delete_console_alert_rule', {
      request: { id },
    });
    return mapOverview(response);
  } catch (error) {
    throw new Error(extractServiceErrorMessage(error, 'Erro ao remover regra de alerta'));
  }
}

export async function markConsoleAlertsRead(): Promise<ConsoleOverview> {
  try {
    const response = await invoke<ConsoleOverviewDto>('mark_console_alerts_read');
    return mapOverview(response);
  } catch (error) {
    throw new Error(extractServiceErrorMessage(error, 'Erro ao marcar alertas como lidos'));
  }
}

export async function clearConsoleLogs(): Promise<ConsoleOverview> {
  try {
    const response = await invoke<ConsoleOverviewDto>('clear_console_logs');
    return mapOverview(response);
  } catch (error) {
    throw new Error(extractServiceErrorMessage(error, 'Erro ao limpar logs do console'));
  }
}

export async function subscribeConsoleEvents(handlers: {
  onEntries?: (entries: ConsoleLogEntry[]) => void;
  onEntry?: (entry: ConsoleLogEntry) => void;
  onBadge?: (badgeCount: number) => void;
}): Promise<() => void> {
  const unlisteners: UnlistenFn[] = [];

  if (handlers.onEntries) {
    unlisteners.push(
      await listen<ConsoleEntriesEventDto>('console://entries', (event) => {
        handlers.onEntries?.((event.payload ?? []).map(mapLogEntry));
      }),
    );
  }

  if (handlers.onEntry) {
    unlisteners.push(
      await listen<ConsoleLogEntryDto>('console://entry', (event) => {
        handlers.onEntry?.(mapLogEntry(event.payload));
      }),
    );
  }

  if (handlers.onBadge) {
    unlisteners.push(
      await listen<ConsoleBadgeEventDto>('console://badge', (event) => {
        handlers.onBadge?.(event.payload.badge_count ?? 0);
      }),
    );
  }

  return () => {
    for (const unlisten of unlisteners) {
      unlisten();
    }
  };
}
