export type ConsoleLogLevel = 'debug' | 'info' | 'warning' | 'error';

export type ConsoleSourceScope = 'app' | 'plant';

export type ConsoleSourceKind =
  | 'frontend'
  | 'backend'
  | 'runtime'
  | 'driver'
  | 'controller'
  | 'native_output';

export interface ConsoleLogEntry {
  id: string;
  timestamp: string;
  level: ConsoleLogLevel;
  message: string;
  sourceScope: ConsoleSourceScope;
  sourceKind: ConsoleSourceKind;
  plantId?: string | null;
  plantName?: string | null;
  runtimeId?: string | null;
  pluginId?: string | null;
  pluginName?: string | null;
  controllerId?: string | null;
  controllerName?: string | null;
  details?: Record<string, unknown> | string | number | boolean | null;
}

export type ConsoleAlertTarget =
  | { type: 'app' }
  | { type: 'all_plants' }
  | { type: 'selected_plants'; plantIds: string[] };

export interface ConsoleAlertRule {
  id: string;
  name: string;
  enabled: boolean;
  levels: ConsoleLogLevel[];
  target: ConsoleAlertTarget;
}

export interface ConsolePlantOption {
  plantId: string;
  plantName: string;
}

export interface ConsoleOverview {
  badgeCount: number;
  rules: ConsoleAlertRule[];
  knownPlants: ConsolePlantOption[];
  lastAlertReadAt: string | null;
}

export interface AppendConsoleLogInput {
  level: ConsoleLogLevel;
  message: string;
  sourceScope: ConsoleSourceScope;
  sourceKind: ConsoleSourceKind;
  plantId?: string | null;
  plantName?: string | null;
  runtimeId?: string | null;
  pluginId?: string | null;
  pluginName?: string | null;
  controllerId?: string | null;
  controllerName?: string | null;
  details?: Record<string, unknown> | string | number | boolean | null;
}

export interface SaveConsoleAlertRuleInput {
  id?: string;
  name: string;
  enabled: boolean;
  levels: ConsoleLogLevel[];
  target: ConsoleAlertTarget;
}

export interface ListConsoleLogsFilters {
  levels?: ConsoleLogLevel[];
  sourceScope?: ConsoleSourceScope;
  plantId?: string;
  search?: string;
  limit?: number;
}

export const CONSOLE_LEVEL_LABELS: Record<ConsoleLogLevel, string> = {
  debug: 'Debug',
  info: 'Info',
  warning: 'Warning',
  error: 'Error',
};

export const CONSOLE_SOURCE_KIND_LABELS: Record<ConsoleSourceKind, string> = {
  frontend: 'Frontend',
  backend: 'Backend',
  runtime: 'Runtime',
  driver: 'Driver',
  controller: 'Controller',
  native_output: 'Externo',
};

export const CONSOLE_SOURCE_KIND_TERMINAL_LABELS: Record<ConsoleSourceKind, string> = {
  frontend: 'FRONTEND',
  backend: 'BACKEND',
  runtime: 'RUNTIME',
  driver: 'DRIVER',
  controller: 'CONTROLLER',
  native_output: 'EXTERNO',
};
