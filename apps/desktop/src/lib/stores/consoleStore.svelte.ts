import type { ConsoleLogEntry, ConsoleOverview, ConsolePlantOption, SaveConsoleAlertRuleInput } from '$lib/types/console';
import {
  clearConsoleLogs,
  deleteConsoleAlertRule,
  getConsoleOverview,
  markConsoleAlertsRead,
  saveConsoleAlertRule,
  subscribeConsoleEvents,
} from '$lib/services/console';

class ConsoleStore {
  initialized = $state(false);
  loading = $state(false);
  badgeCount = $state(0);
  rules = $state<ConsoleOverview['rules']>([]);
  knownPlants = $state<ConsolePlantOption[]>([]);
  lastAlertReadAt = $state<string | null>(null);
  private unlisten: (() => void) | null = null;
  private entrySubscribers = new Set<(entry: ConsoleLogEntry) => void>();

  private applyOverview(overview: ConsoleOverview) {
    this.badgeCount = overview.badgeCount;
    this.rules = overview.rules;
    this.knownPlants = overview.knownPlants;
    this.lastAlertReadAt = overview.lastAlertReadAt;
  }

  private registerPlantFromEntry(entry: ConsoleLogEntry) {
    if (!entry.plantId || !entry.plantName) return;
    if (this.knownPlants.some((plant) => plant.plantId === entry.plantId)) {
      return;
    }

    this.knownPlants = [...this.knownPlants, {
      plantId: entry.plantId,
      plantName: entry.plantName,
    }].sort((left, right) => left.plantName.localeCompare(right.plantName, 'pt-BR'));
  }

  async initialize() {
    if (this.initialized) return;
    this.loading = true;

    try {
      const overview = await getConsoleOverview();
      this.applyOverview(overview);
      this.unlisten = await subscribeConsoleEvents({
        onBadge: (badgeCount) => {
          this.badgeCount = badgeCount;
        },
        onEntry: (entry) => {
          this.registerPlantFromEntry(entry);
          for (const subscriber of this.entrySubscribers) {
            subscriber(entry);
          }
        },
      });
      this.initialized = true;
    } finally {
      this.loading = false;
    }
  }

  async refreshOverview() {
    this.applyOverview(await getConsoleOverview());
  }

  subscribeEntries(handler: (entry: ConsoleLogEntry) => void) {
    this.entrySubscribers.add(handler);
    return () => {
      this.entrySubscribers.delete(handler);
    };
  }

  async saveRule(input: SaveConsoleAlertRuleInput) {
    const overview = await saveConsoleAlertRule(input);
    this.applyOverview(overview);
    return overview;
  }

  async deleteRule(id: string) {
    const overview = await deleteConsoleAlertRule(id);
    this.applyOverview(overview);
    return overview;
  }

  async markAlertsRead() {
    const overview = await markConsoleAlertsRead();
    this.applyOverview(overview);
    return overview;
  }

  async clearLogs() {
    const overview = await clearConsoleLogs();
    this.applyOverview(overview);
    return overview;
  }

  destroy() {
    this.unlisten?.();
    this.unlisten = null;
    this.entrySubscribers.clear();
    this.initialized = false;
  }
}

export const consoleStore = new ConsoleStore();
