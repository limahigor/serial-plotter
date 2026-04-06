import type { ConsoleLogEntry, ConsoleOverview, ConsolePlantOption, SaveConsoleAlertRuleInput } from '$lib/types/console';
import {
  clearConsoleLogs,
  deleteConsoleAlertRule,
  getConsoleOverview,
  markConsoleAlertsRead,
  saveConsoleAlertRule,
  subscribeConsoleEvents,
} from '$lib/services/console';

const EVENT_FLUSH_INTERVAL_MS = 48;
const MAX_PENDING_ENTRY_BATCH = 64;

class ConsoleStore {
  initialized = $state(false);
  loading = $state(false);
  badgeCount = $state(0);
  rules = $state<ConsoleOverview['rules']>([]);
  knownPlants = $state<ConsolePlantOption[]>([]);
  lastAlertReadAt = $state<string | null>(null);
  private unlistenBadge: (() => void) | null = null;
  private unlistenEntries: (() => void) | null = null;
  private entryStreamPromise: Promise<void> | null = null;
  private entrySubscribers = new Set<(entries: ConsoleLogEntry[]) => void>();
  private pendingEntries: ConsoleLogEntry[] = [];
  private pendingBadgeCount: number | null = null;
  private flushTimer: ReturnType<typeof setTimeout> | null = null;

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

  private flushPendingEvents() {
    if (this.pendingBadgeCount !== null) {
      this.badgeCount = this.pendingBadgeCount;
      this.pendingBadgeCount = null;
    }

    if (this.pendingEntries.length === 0) {
      return;
    }

    const batch = this.pendingEntries;
    this.pendingEntries = [];
    for (const subscriber of this.entrySubscribers) {
      subscriber(batch);
    }
  }

  private cancelFlushTimer() {
    if (!this.flushTimer) return;
    clearTimeout(this.flushTimer);
    this.flushTimer = null;
  }

  private flushNow() {
    this.cancelFlushTimer();
    this.flushPendingEvents();
  }

  private scheduleFlush() {
    if (this.flushTimer) return;
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null;
      this.flushPendingEvents();
    }, EVENT_FLUSH_INTERVAL_MS);
  }

  private queueEntry(entry: ConsoleLogEntry) {
    this.queueEntries([entry]);
  }

  private queueEntries(entries: ConsoleLogEntry[]) {
    if (this.entrySubscribers.size === 0) {
      return;
    }

    if (entries.length === 0) {
      return;
    }

    this.pendingEntries.push(...entries);
    if (this.pendingEntries.length >= MAX_PENDING_ENTRY_BATCH) {
      this.flushNow();
      return;
    }

    this.scheduleFlush();
  }

  private queueBadgeCount(badgeCount: number) {
    this.pendingBadgeCount = badgeCount;
    this.scheduleFlush();
  }

  private async ensureEntryStream() {
    if (this.unlistenEntries || this.entryStreamPromise || this.entrySubscribers.size === 0) {
      return;
    }

    this.entryStreamPromise = (async () => {
      const unlisten = await subscribeConsoleEvents({
        onEntries: (entries) => {
          for (const entry of entries) {
            this.registerPlantFromEntry(entry);
          }
          this.queueEntries(entries);
        },
        onEntry: (entry) => {
          this.registerPlantFromEntry(entry);
          this.queueEntry(entry);
        },
      });

      if (this.entrySubscribers.size === 0) {
        unlisten();
        return;
      }

      this.unlistenEntries = unlisten;
    })();

    try {
      await this.entryStreamPromise;
    } finally {
      this.entryStreamPromise = null;
    }
  }

  private stopEntryStream() {
    this.unlistenEntries?.();
    this.unlistenEntries = null;
    this.pendingEntries = [];
  }

  async initialize() {
    if (this.initialized) return;
    this.loading = true;

    try {
      const overview = await getConsoleOverview();
      this.applyOverview(overview);
      this.unlistenBadge = await subscribeConsoleEvents({
        onBadge: (badgeCount) => {
          this.queueBadgeCount(badgeCount);
        },
      });
      this.initialized = true;
    } finally {
      this.loading = false;
    }
  }

  async refreshOverview() {
    this.flushNow();
    this.applyOverview(await getConsoleOverview());
  }

  subscribeEntries(handler: (entries: ConsoleLogEntry[]) => void) {
    this.entrySubscribers.add(handler);
    void this.initialize().then(() => this.ensureEntryStream());
    return () => {
      this.entrySubscribers.delete(handler);
      if (this.entrySubscribers.size === 0) {
        this.stopEntryStream();
      }
    };
  }

  async saveRule(input: SaveConsoleAlertRuleInput) {
    this.flushNow();
    const overview = await saveConsoleAlertRule(input);
    this.applyOverview(overview);
    return overview;
  }

  async deleteRule(id: string) {
    this.flushNow();
    const overview = await deleteConsoleAlertRule(id);
    this.applyOverview(overview);
    return overview;
  }

  async markAlertsRead() {
    this.flushNow();
    const overview = await markConsoleAlertsRead();
    this.applyOverview(overview);
    return overview;
  }

  async clearLogs() {
    this.flushNow();
    const overview = await clearConsoleLogs();
    this.applyOverview(overview);
    return overview;
  }

  destroy() {
    this.cancelFlushTimer();
    this.unlistenBadge?.();
    this.unlistenBadge = null;
    this.stopEntryStream();
    this.entrySubscribers.clear();
    this.pendingEntries = [];
    this.pendingBadgeCount = null;
    this.initialized = false;
  }
}

export const consoleStore = new ConsoleStore();
