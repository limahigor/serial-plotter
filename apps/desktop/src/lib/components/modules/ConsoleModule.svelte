<script lang="ts">
  import { ChevronsRight, Sliders, X } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import { appStore } from '$lib/stores/data.svelte';
  import { consoleStore } from '$lib/stores/consoleStore.svelte';
  import { listConsoleLogs } from '$lib/services/console';
  import {
    CONSOLE_LEVEL_LABELS,
    CONSOLE_SOURCE_KIND_TERMINAL_LABELS,
    type ConsoleAlertRule,
    type ConsoleAlertTarget,
    type ConsoleLogEntry,
    type ConsoleLogLevel,
    type ConsolePlantOption,
    type ConsoleSourceKind,
  } from '$lib/types/console';

  interface Props {
    theme: 'dark' | 'light';
    active?: boolean;
  }

  const LEVELS: ConsoleLogLevel[] = ['debug', 'info', 'warning', 'error'];
  const MAX_VISIBLE_ENTRIES = 120;
  const LIVE_RENDER_INTERVAL_MS = 72;
  const TAIL_LOCK_THRESHOLD = 28;
  const ALERT_TARGETS: Array<{ value: ConsoleAlertTarget['type']; label: string }> = [
    { value: 'app', label: 'Somente app' },
    { value: 'all_plants', label: 'Todas as plantas' },
    { value: 'selected_plants', label: 'Plantas específicas' },
  ];

  let { theme, active = true }: Props = $props();

  let entries = $state<ConsoleLogEntry[]>([]);
  let loading = $state(false);
  let errorMessage = $state<string | null>(null);
  let searchDraft = $state('');
  let appliedSearch = $state('');
  let selectedLevels = $state<ConsoleLogLevel[]>([]);
  let scopeFilter = $state<'all' | 'app' | 'plant'>('all');
  let selectedPlantId = $state('');
  let loadDebounce: ReturnType<typeof setTimeout> | null = null;
  let requestSequence = 0;
  let logViewport: HTMLDivElement | null = $state(null);
  let tailLocked = $state(true);
  let selectedEntryId = $state<string | null>(null);
  let selectedEntrySnapshot = $state<ConsoleLogEntry | null>(null);
  let copyFeedback = $state<'idle' | 'success' | 'error'>('idle');
  let showSidePanel = $state(true);
  let liveFlushTimer: ReturnType<typeof setTimeout> | null = null;
  let copyFeedbackTimer: ReturnType<typeof setTimeout> | null = null;
  let tailScrollFrame = 0;
  let forceTailScroll = false;
  let pendingLiveEntries: ConsoleLogEntry[] = [];

  let editingRuleId = $state<string | null>(null);
  let ruleName = $state('');
  let ruleEnabled = $state(true);
  let ruleLevels = $state<ConsoleLogLevel[]>([]);
  let ruleTargetType = $state<ConsoleAlertTarget['type']>('app');
  let rulePlantIds = $state<string[]>([]);
  let savingRule = $state(false);

  const rules = $derived(consoleStore.rules);
  const normalizedSearch = $derived(appliedSearch.trim().toLowerCase());
  const enabledRulesCount = $derived.by(() => rules.filter((rule) => rule.enabled).length);
  const isLightTheme = $derived(theme === 'light');
  const selectedEntry = $derived.by(() => {
    if (!selectedEntryId) {
      return null;
    }

    return entries.find((entry) => entry.id === selectedEntryId) ?? selectedEntrySnapshot;
  });

  const plantOptions = $derived.by<ConsolePlantOption[]>(() => {
    const merged = new Map<string, string>();

    for (const plant of consoleStore.knownPlants) {
      merged.set(plant.plantId, plant.plantName);
    }

    for (const plant of appStore.plotterPlants) {
      merged.set(plant.id, plant.name);
    }

    return Array.from(merged.entries())
      .map(([plantId, plantName]) => ({ plantId, plantName }))
      .sort((left, right) => left.plantName.localeCompare(right.plantName, 'pt-BR'));
  });

  const plantNameById = $derived.by<Map<string, string>>(
    () => new Map(plantOptions.map((plant) => [plant.plantId, plant.plantName])),
  );

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  function getDetailString(details: ConsoleLogEntry['details'], key: string): string | null {
    if (!isRecord(details)) return null;
    const value = details[key];
    return typeof value === 'string' && value.trim() ? value : null;
  }

  function formatTerminalTimestamp(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    const milliseconds = String(date.getMilliseconds()).padStart(3, '0');
    return `${hours}:${minutes}:${seconds}.${milliseconds}`;
  }

  function formatReadableDateTime(value: string | null) {
    if (!value) return 'Nunca';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString('pt-BR');
  }

  function terminalOriginLabel(sourceKind: ConsoleSourceKind) {
    return CONSOLE_SOURCE_KIND_TERMINAL_LABELS[sourceKind] ?? sourceKind.toUpperCase();
  }

  function levelClass(level: ConsoleLogLevel) {
    if (theme === 'light') {
      switch (level) {
        case 'debug':
          return 'text-slate-400';
        case 'info':
          return 'text-sky-700';
        case 'warning':
          return 'text-amber-700';
        case 'error':
          return 'text-rose-700';
      }
    }

    switch (level) {
      case 'debug':
        return 'text-zinc-500';
      case 'info':
        return 'text-sky-300';
      case 'warning':
        return 'text-amber-300';
      case 'error':
        return 'text-rose-300';
    }
  }

  function originClass(sourceKind: ConsoleSourceKind) {
    if (theme === 'light') {
      switch (sourceKind) {
        case 'frontend':
          return 'text-cyan-700';
        case 'backend':
          return 'text-violet-700';
        case 'runtime':
          return 'text-sky-700';
        case 'driver':
          return 'text-emerald-700';
        case 'controller':
          return 'text-fuchsia-700';
        case 'native_output':
          return 'text-slate-500';
      }
    }

    switch (sourceKind) {
      case 'frontend':
        return 'text-cyan-300';
      case 'backend':
        return 'text-violet-300';
      case 'runtime':
        return 'text-sky-300';
      case 'driver':
        return 'text-emerald-300';
      case 'controller':
        return 'text-fuchsia-300';
      case 'native_output':
        return 'text-zinc-400';
    }
  }

  function messageClass(entry: ConsoleLogEntry) {
    if (theme === 'light') {
      if (entry.sourceKind === 'native_output') {
        return entry.level === 'error' ? 'text-rose-700' : 'text-slate-700';
      }

      switch (entry.level) {
        case 'debug':
          return 'text-slate-600';
        case 'info':
          return 'text-slate-800';
        case 'warning':
          return 'text-amber-800';
        case 'error':
          return 'text-rose-800';
      }
    }

    if (entry.sourceKind === 'native_output') {
      return entry.level === 'error' ? 'text-rose-100' : 'text-zinc-200';
    }

    switch (entry.level) {
      case 'debug':
        return 'text-zinc-300';
      case 'info':
        return 'text-zinc-100';
      case 'warning':
        return 'text-amber-100';
      case 'error':
        return 'text-rose-100';
    }
  }

  function entryMetaTags(entry: ConsoleLogEntry) {
    const tags: string[] = [];

    if (entry.sourceScope === 'app') {
      tags.push('App');
    } else if (entry.plantName) {
      tags.push(entry.plantName);
    }

    if (entry.pluginName) tags.push(entry.pluginName);
    if (entry.controllerName) tags.push(entry.controllerName);
    if (entry.runtimeId) tags.push(entry.runtimeId);

    const channel = getDetailString(entry.details, 'channel');
    if (channel) tags.push(channel);

    return tags;
  }

  function formatEntryDetails(details: ConsoleLogEntry['details']) {
    if (details === null || details === undefined) return '';

    try {
      const serialized = JSON.stringify(details, null, 2);
      return serialized ?? String(details);
    } catch {
      return String(details);
    }
  }

  function formatInlineMeta(entry: ConsoleLogEntry) {
    const tags = entryMetaTags(entry);
    if (tags.length === 0) {
      return '';
    }

    return `[${tags.join(' · ')}]`;
  }

  function resetCopyFeedback() {
    copyFeedback = 'idle';
    if (!copyFeedbackTimer) {
      return;
    }

    clearTimeout(copyFeedbackTimer);
    copyFeedbackTimer = null;
  }

  function setCopyFeedback(status: 'success' | 'error') {
    resetCopyFeedback();
    copyFeedback = status;
    copyFeedbackTimer = setTimeout(() => {
      copyFeedback = 'idle';
      copyFeedbackTimer = null;
    }, 2200);
  }

  async function writeToClipboard(value: string) {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }

    if (typeof document === 'undefined') {
      throw new Error('Clipboard indisponível');
    }

    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', 'true');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);

    const copied = document.execCommand('copy');
    document.body.removeChild(textarea);

    if (!copied) {
      throw new Error('Falha ao copiar log');
    }
  }

  function formatEntryForClipboard(entry: ConsoleLogEntry) {
    const lines = [
      `Hora: ${formatReadableDateTime(entry.timestamp)}`,
      `Nivel: ${entry.level}`,
      `Origem: ${terminalOriginLabel(entry.sourceKind)}`,
    ];

    if (entry.sourceScope === 'app') {
      lines.push('Escopo: App');
    } else if (entry.plantName) {
      lines.push(`Escopo: Planta (${entry.plantName})`);
    } else {
      lines.push('Escopo: Planta');
    }

    const meta = formatInlineMeta(entry);
    if (meta) {
      lines.push(`Metadados: ${meta}`);
    }

    lines.push(`Mensagem: ${entry.message}`);

    if (entry.details !== null && entry.details !== undefined) {
      lines.push('');
      lines.push('Detalhes:');
      lines.push(formatEntryDetails(entry.details));
    }

    return lines.join('\n');
  }

  async function copySelectedEntryToClipboard() {
    if (!selectedEntry) {
      return;
    }

    try {
      await writeToClipboard(formatEntryForClipboard(selectedEntry));
      setCopyFeedback('success');
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Falha ao copiar log';
      setCopyFeedback('error');
    }
  }

  function selectEntry(entry: ConsoleLogEntry) {
    if (selectedEntryId === entry.id) {
      selectedEntryId = null;
      selectedEntrySnapshot = null;
      resetCopyFeedback();
      return;
    }

    selectedEntryId = entry.id;
    selectedEntrySnapshot = entry;
    resetCopyFeedback();
  }

  function closeInspector() {
    selectedEntryId = null;
    selectedEntrySnapshot = null;
    resetCopyFeedback();
  }

  function describeTarget(target: ConsoleAlertTarget) {
    if (target.type === 'app') return 'Somente app';
    if (target.type === 'all_plants') return 'Todas as plantas';

    const names = target.plantIds
      .map((plantId) => plantNameById.get(plantId) ?? plantId)
      .join(', ');
    return names || 'Plantas específicas';
  }

  function describeRuleLevels(rule: ConsoleAlertRule) {
    if (rule.levels.length === 0) {
      return 'Qualquer nível';
    }

    return rule.levels.map((level) => CONSOLE_LEVEL_LABELS[level]).join(', ');
  }

  function matchesCurrentFilters(entry: ConsoleLogEntry) {
    if (selectedLevels.length > 0 && !selectedLevels.includes(entry.level)) {
      return false;
    }

    if (scopeFilter === 'app' && entry.sourceScope !== 'app') {
      return false;
    }

    if (scopeFilter === 'plant' && entry.sourceScope !== 'plant') {
      return false;
    }

    if (scopeFilter === 'plant' && selectedPlantId && entry.plantId !== selectedPlantId) {
      return false;
    }

    if (normalizedSearch) {
      const haystack = [
        entry.message,
        entry.plantName ?? '',
        entry.pluginName ?? '',
        entry.controllerName ?? '',
      ]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(normalizedSearch)) {
        return false;
      }
    }

    return true;
  }

  function cancelTailScroll() {
    if (tailScrollFrame) {
      cancelAnimationFrame(tailScrollFrame);
      tailScrollFrame = 0;
    }
    forceTailScroll = false;
  }

  function scheduleTailScroll(force = false) {
    if (!logViewport) return;
    if (force) {
      forceTailScroll = true;
    }
    if (!forceTailScroll && !tailLocked) return;
    if (tailScrollFrame) return;

    tailScrollFrame = requestAnimationFrame(() => {
      tailScrollFrame = 0;
      const shouldScroll = forceTailScroll || tailLocked;
      forceTailScroll = false;
      if (!logViewport || !shouldScroll) return;
      logViewport.scrollTop = logViewport.scrollHeight;
    });
  }

  function handleViewportScroll() {
    if (!logViewport) return;

    const distanceToBottom =
      logViewport.scrollHeight - (logViewport.scrollTop + logViewport.clientHeight);
    tailLocked = distanceToBottom <= TAIL_LOCK_THRESHOLD;
  }

  function applyEntries(nextEntries: ConsoleLogEntry[]) {
    entries = nextEntries;

    if (!selectedEntryId) {
      return;
    }

    const updatedSelectedEntry = nextEntries.find((entry) => entry.id === selectedEntryId);
    if (updatedSelectedEntry) {
      selectedEntrySnapshot = updatedSelectedEntry;
    }
  }

  function cancelLiveFlush() {
    if (!liveFlushTimer) return;
    clearTimeout(liveFlushTimer);
    liveFlushTimer = null;
  }

  function flushPendingLiveEntries() {
    liveFlushTimer = null;

    if (pendingLiveEntries.length === 0) {
      return;
    }

    const visibleEntries = pendingLiveEntries.filter((entry) => matchesCurrentFilters(entry));
    pendingLiveEntries = [];
    if (visibleEntries.length === 0) {
      return;
    }

    applyEntries([...entries, ...visibleEntries].slice(-MAX_VISIBLE_ENTRIES));
    scheduleTailScroll();
  }

  function queueLiveEntries(batch: ConsoleLogEntry[]) {
    if (batch.length === 0) {
      return;
    }

    pendingLiveEntries.push(...batch);
    if (liveFlushTimer) {
      return;
    }

    liveFlushTimer = setTimeout(() => {
      flushPendingLiveEntries();
    }, LIVE_RENDER_INTERVAL_MS);
  }

  async function loadEntries() {
    if (!active) return;

    const currentRequest = ++requestSequence;
    loading = true;
    errorMessage = null;
    pendingLiveEntries = [];
    cancelLiveFlush();

    try {
      const response = await listConsoleLogs({
        levels: selectedLevels,
        sourceScope: scopeFilter === 'all' ? undefined : scopeFilter,
        plantId: scopeFilter === 'plant' ? selectedPlantId || undefined : undefined,
        search: appliedSearch,
        limit: MAX_VISIBLE_ENTRIES,
      });

      if (currentRequest !== requestSequence) return;

      const nextEntries = [...response].reverse();
      applyEntries(nextEntries);
      scheduleTailScroll(true);
    } catch (error) {
      if (currentRequest !== requestSequence) return;
      errorMessage = error instanceof Error ? error.message : 'Erro ao carregar logs do console';
    } finally {
      if (currentRequest === requestSequence) {
        loading = false;
      }
    }
  }

  function scheduleLoad(delay = 120) {
    if (loadDebounce) {
      clearTimeout(loadDebounce);
    }

    loadDebounce = setTimeout(() => {
      loadDebounce = null;
      void loadEntries();
    }, delay);
  }

  function applySearch() {
    appliedSearch = searchDraft;
    tailLocked = true;
    scheduleLoad(0);
  }

  function handleSearchKeydown(event: KeyboardEvent) {
    if (event.key !== 'Enter') {
      return;
    }

    event.preventDefault();
    applySearch();
  }

  function toggleFilterLevel(level: ConsoleLogLevel) {
    selectedLevels = selectedLevels.includes(level)
      ? selectedLevels.filter((item) => item !== level)
      : [...selectedLevels, level];
    scheduleLoad();
  }

  function toggleRuleLevel(level: ConsoleLogLevel) {
    ruleLevels = ruleLevels.includes(level)
      ? ruleLevels.filter((item) => item !== level)
      : [...ruleLevels, level];
  }

  function toggleRulePlant(plantId: string) {
    rulePlantIds = rulePlantIds.includes(plantId)
      ? rulePlantIds.filter((item) => item !== plantId)
      : [...rulePlantIds, plantId];
  }

  function resetRuleForm() {
    editingRuleId = null;
    ruleName = '';
    ruleEnabled = true;
    ruleLevels = [];
    ruleTargetType = 'app';
    rulePlantIds = [];
  }

  function editRule(rule: ConsoleAlertRule) {
    editingRuleId = rule.id;
    ruleName = rule.name;
    ruleEnabled = rule.enabled;
    ruleLevels = [...rule.levels];
    ruleTargetType = rule.target.type;
    rulePlantIds = rule.target.type === 'selected_plants' ? [...rule.target.plantIds] : [];
  }

  async function submitRule() {
    savingRule = true;
    errorMessage = null;

    try {
      await consoleStore.saveRule({
        id: editingRuleId ?? undefined,
        name: ruleName,
        enabled: ruleEnabled,
        levels: [...ruleLevels],
        target:
          ruleTargetType === 'selected_plants'
            ? { type: 'selected_plants', plantIds: [...rulePlantIds] }
            : { type: ruleTargetType },
      });
      resetRuleForm();
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Erro ao salvar regra';
    } finally {
      savingRule = false;
    }
  }

  async function removeRule(ruleId: string) {
    errorMessage = null;

    try {
      await consoleStore.deleteRule(ruleId);
      if (editingRuleId === ruleId) {
        resetRuleForm();
      }
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Erro ao remover regra';
    }
  }

  async function handleMarkRead() {
    errorMessage = null;

    try {
      await consoleStore.markAlertsRead();
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Erro ao marcar alertas';
    }
  }

  async function handleClearLogs() {
    errorMessage = null;

    try {
      await consoleStore.clearLogs();
      applyEntries([]);
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Erro ao limpar logs';
    }
  }

  onMount(() => {
    void consoleStore.initialize();

    return () => {
      if (loadDebounce) {
        clearTimeout(loadDebounce);
      }
      resetCopyFeedback();
      cancelLiveFlush();
      cancelTailScroll();
    };
  });

  $effect(() => {
    if (!active) return;

    const unsubscribeEntries = consoleStore.subscribeEntries((batch) => {
      queueLiveEntries(batch);
    });

    return () => {
      unsubscribeEntries();
    };
  });

  $effect(() => {
    if (active) return;
    pendingLiveEntries = [];
    cancelLiveFlush();
    cancelTailScroll();
    if (loadDebounce) {
      clearTimeout(loadDebounce);
      loadDebounce = null;
    }
  });

  $effect(() => {
    if (!active) return;
    tailLocked = true;
    scheduleLoad(0);
  });
</script>

<div class="flex h-full min-h-0 flex-col overflow-hidden bg-slate-50 dark:bg-zinc-950">
  <header class="flex-shrink-0 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur dark:border-white/5 dark:bg-zinc-900/90 sm:px-5">
    <div class="flex w-full flex-col gap-2.5">
      <div class="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 class="text-base font-semibold text-slate-800 dark:text-white">Console</h1>
        </div>

        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class={`p-2 rounded-lg border shadow-sm transition-all ${
              showSidePanel
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white dark:bg-[#18181b] text-slate-500 border-slate-200 dark:border-white/10 hover:bg-slate-50 dark:hover:bg-white/5'
            }`}
            onclick={() => (showSidePanel = !showSidePanel)}
            title={showSidePanel ? 'Ocultar painel lateral' : 'Mostrar painel lateral'}
          >
            <Sliders size={16} />
          </button>
          <button
            type="button"
            class="inline-flex items-center rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-600 shadow-sm transition hover:bg-slate-50 dark:border-white/10 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
            onclick={handleMarkRead}
          >
            Marcar alertas como lidos
          </button>
          <button
            type="button"
            class="inline-flex items-center rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-600 shadow-sm transition hover:bg-slate-50 dark:border-white/10 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
            onclick={handleClearLogs}
          >
            Limpar histórico
          </button>
        </div>
      </div>

      <div class="grid gap-2 lg:grid-cols-[minmax(0,1fr)_200px_auto]">
        <input
          bind:value={searchDraft}
          onkeydown={handleSearchKeydown}
          class="h-9 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700 outline-none transition focus:border-slate-400 focus:bg-white dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:border-zinc-500"
          placeholder="Buscar por mensagem, planta, plugin ou controlador (Enter para aplicar)"
        />

        <select
          bind:value={selectedPlantId}
          disabled={scopeFilter !== 'plant'}
          onchange={() => scheduleLoad()}
          class="h-9 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700 outline-none transition focus:border-slate-400 focus:bg-white disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:border-zinc-500"
        >
          <option value="">Todas as plantas</option>
          {#each plantOptions as plant}
            <option value={plant.plantId}>{plant.plantName}</option>
          {/each}
        </select>

        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[10px] uppercase tracking-[0.08em] text-slate-500 dark:text-zinc-500">
          <span class="font-mono">alertas: {consoleStore.badgeCount}</span>
          <span class="font-mono">regras: {enabledRulesCount}</span>
          <span class="font-mono">follow: {tailLocked ? 'on' : 'off'}</span>
        </div>
      </div>

      <div class="flex flex-wrap gap-1.5">
        <button
          type="button"
          class={`rounded-full px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.08em] transition ${scopeFilter === 'all' ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'}`}
          onclick={() => {
            scopeFilter = 'all';
            selectedPlantId = '';
            scheduleLoad();
          }}
        >
          Todos
        </button>
        <button
          type="button"
          class={`rounded-full px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.08em] transition ${scopeFilter === 'app' ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'}`}
          onclick={() => {
            scopeFilter = 'app';
            selectedPlantId = '';
            scheduleLoad();
          }}
        >
          Só app
        </button>
        <button
          type="button"
          class={`rounded-full px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.08em] transition ${scopeFilter === 'plant' ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'}`}
          onclick={() => {
            scopeFilter = 'plant';
            scheduleLoad();
          }}
        >
          Só plantas
        </button>

        {#each LEVELS as level}
          <button
            type="button"
            class={`rounded-full px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.08em] transition ${selectedLevels.includes(level) ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'}`}
            onclick={() => toggleFilterLevel(level)}
          >
            {CONSOLE_LEVEL_LABELS[level]}
          </button>
        {/each}
      </div>
    </div>
  </header>

  <div class="flex-1 min-h-0 overflow-hidden">
    <div class={`flex h-full min-h-0 flex-col xl:flex-row ${showSidePanel ? 'xl:gap-0' : 'xl:gap-0'}`}>
      <section class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden border-t border-slate-200 bg-white dark:border-white/10 dark:bg-zinc-900 xl:border-r">
        <div class={`border-b px-3 py-1.5 font-mono text-[10px] ${isLightTheme ? 'border-slate-200 bg-slate-100 text-slate-500' : 'border-white/10 bg-[#111318] text-zinc-500'}`}>
          <span class={isLightTheme ? 'text-emerald-600' : 'text-emerald-400'}>$</span>
          <span class="ml-2">console --follow --limit {MAX_VISIBLE_ENTRIES}</span>
          {#if normalizedSearch}
            <span class={isLightTheme ? 'text-slate-400' : 'text-zinc-600'}> | grep -i "{appliedSearch.trim()}"</span>
          {/if}
        </div>

        {#if errorMessage}
          <div class="border-b border-rose-200 bg-rose-50 px-3 py-1.5 text-[11px] text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-200">
            {errorMessage}
          </div>
        {/if}

        <div
          bind:this={logViewport}
          class={`min-h-0 flex-1 overflow-auto font-mono text-[12px] [scrollbar-gutter:stable] ${isLightTheme ? 'bg-[#fcfcfb] text-slate-700' : 'bg-[#0d1117] text-zinc-200'}`}
          aria-live="off"
          onscroll={handleViewportScroll}
        >
          {#if loading && entries.length === 0}
            <div class={isLightTheme ? 'px-3 py-5 text-[11px] text-slate-400' : 'px-3 py-5 text-[11px] text-zinc-500'}>
              sincronizando buffer...
            </div>
          {:else if entries.length === 0}
            <div class={isLightTheme ? 'px-3 py-5 text-[11px] text-slate-400' : 'px-3 py-5 text-[11px] text-zinc-500'}>
              nenhum log encontrado.
            </div>
          {:else}
            <div class="flex min-h-full flex-col justify-end">
              <div class={`grid grid-cols-[88px_58px_86px_minmax(0,1fr)] gap-2 border-b px-3 py-1.5 text-[10px] uppercase tracking-[0.12em] ${isLightTheme ? 'border-slate-200 bg-[#f2f4f7] text-slate-400' : 'border-white/10 bg-[#13171d] text-zinc-500'}`}>
                <span>hora</span>
                <span>nível</span>
                <span>origem</span>
                <span>mensagem</span>
              </div>

              {#each entries as entry (entry.id)}
                <button
                  type="button"
                  class={`grid w-full grid-cols-[88px_58px_86px_minmax(0,1fr)] gap-2 border-b px-3 py-1.5 text-left transition ${selectedEntryId === entry.id ? (isLightTheme ? 'bg-slate-100/90' : 'bg-white/[0.05]') : ''} ${isLightTheme ? 'border-slate-100 hover:bg-slate-50/80' : 'border-white/5 hover:bg-white/[0.02]'}`}
                  onclick={() => selectEntry(entry)}
                >
                  <div class={isLightTheme ? 'truncate text-slate-400' : 'truncate text-zinc-500'}>
                    {formatTerminalTimestamp(entry.timestamp)}
                  </div>
                  <div class={`truncate uppercase ${levelClass(entry.level)}`}>{entry.level}</div>
                  <div class={`truncate uppercase ${originClass(entry.sourceKind)}`}>{terminalOriginLabel(entry.sourceKind)}</div>

                  <div class={`min-w-0 truncate leading-[1.35] ${messageClass(entry)}`}>
                    <span>{entry.message}</span>
                    {#if formatInlineMeta(entry)}
                      <span class={isLightTheme ? 'ml-2 text-[10px] text-slate-400' : 'ml-2 text-[10px] text-zinc-500'}>
                        {formatInlineMeta(entry)}
                      </span>
                    {/if}
                  </div>
                </button>
              {/each}
            </div>
          {/if}
        </div>

        {#if selectedEntry}
          <div class={`border-t px-3 py-2 font-mono ${isLightTheme ? 'border-slate-200 bg-slate-50/90' : 'border-white/10 bg-[#0f1319]'}`}>
            <div class="flex items-center justify-between gap-3">
              <div class={isLightTheme ? 'text-[10px] uppercase tracking-[0.12em] text-slate-400' : 'text-[10px] uppercase tracking-[0.12em] text-zinc-500'}>
                inspector
              </div>
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class={`inline-flex h-7 items-center justify-center rounded-md border px-2 text-[10px] font-medium uppercase tracking-[0.08em] transition ${copyFeedback === 'success' ? 'border-emerald-500 bg-emerald-500 text-white hover:bg-emerald-500' : copyFeedback === 'error' ? 'border-rose-500 bg-rose-500 text-white hover:bg-rose-500' : isLightTheme ? 'border-slate-200 bg-white text-slate-500 hover:bg-slate-100 hover:text-slate-800' : 'border-white/10 bg-white/[0.03] text-zinc-400 hover:bg-white/[0.08] hover:text-zinc-100'}`}
                  onclick={copySelectedEntryToClipboard}
                  title="Copiar log"
                >
                  {copyFeedback === 'success' ? 'Copiado' : copyFeedback === 'error' ? 'Falhou' : 'Copy'}
                </button>
                <button
                  type="button"
                  class={`inline-flex h-7 w-7 items-center justify-center rounded-md border transition ${isLightTheme ? 'border-slate-200 bg-white text-slate-500 hover:bg-slate-100 hover:text-slate-800' : 'border-white/10 bg-white/[0.03] text-zinc-400 hover:bg-white/[0.08] hover:text-zinc-100'}`}
                  onclick={closeInspector}
                  title="Fechar inspector"
                  aria-label="Fechar inspector"
                >
                  <X size={14} />
                </button>
              </div>
            </div>
            <div class={`mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[10px] uppercase ${isLightTheme ? 'text-slate-500' : 'text-zinc-500'}`}>
              <span>{formatTerminalTimestamp(selectedEntry.timestamp)}</span>
              <span class={levelClass(selectedEntry.level)}>{selectedEntry.level}</span>
              <span class={originClass(selectedEntry.sourceKind)}>{terminalOriginLabel(selectedEntry.sourceKind)}</span>
              {#if formatInlineMeta(selectedEntry)}
                <span>{formatInlineMeta(selectedEntry)}</span>
              {/if}
            </div>
            <div class={`mt-1 text-[12px] leading-[1.4] ${messageClass(selectedEntry)}`}>
              {selectedEntry.message}
            </div>
            {#if selectedEntry.details}
              <pre class={`mt-2 max-h-36 overflow-auto rounded-lg border px-2 py-2 text-[10px] leading-4 ${isLightTheme ? 'border-slate-200 bg-white text-slate-700' : 'border-white/10 bg-black/25 text-zinc-300'}`}>{formatEntryDetails(selectedEntry.details)}</pre>
            {/if}
          </div>
        {/if}
      </section>

      <aside
        class={`${
          showSidePanel
            ? 'w-full max-h-[62vh] translate-y-0 xl:w-[300px] xl:h-full xl:max-h-full xl:translate-y-0'
            : 'pointer-events-none w-full max-h-0 translate-y-2 xl:w-0 xl:h-full xl:max-h-full xl:translate-y-0 xl:translate-x-full'
        } bg-white dark:bg-[#0c0c0e] border-t xl:border-t-0 xl:border-l border-slate-200 dark:border-white/5 flex flex-col min-h-0 overflow-hidden transition-[width,max-height,transform] duration-300 ease-in-out shadow-xl relative z-20`}
        aria-hidden={!showSidePanel}
      >
        <div class="h-12 border-b border-slate-100 dark:border-white/5 flex justify-between items-center px-4 bg-slate-50 dark:bg-white/[0.02]">
          <div class="min-w-0">
            <h2 class="truncate text-sm font-semibold text-slate-800 dark:text-white">Alertas e Regras</h2>
          </div>
          <button
            type="button"
            onclick={() => (showSidePanel = false)}
            class="text-slate-400 hover:text-slate-600 dark:hover:text-white"
            title="Recolher painel"
          >
            <ChevronsRight size={18} />
          </button>
        </div>

        <div class="flex-1 min-h-0 overflow-y-auto overscroll-y-contain p-3 space-y-3">
          <section class="rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 dark:border-white/10 dark:bg-[#121215]">
            <dl class="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px] text-slate-600 dark:text-zinc-300">
              <div class="flex items-center justify-between gap-2">
                <dt>Pendentes</dt>
                <dd class="font-mono text-slate-800 dark:text-zinc-100">{consoleStore.badgeCount}</dd>
              </div>
              <div class="flex items-center justify-between gap-2">
                <dt>Ativas</dt>
                <dd class="font-mono text-slate-800 dark:text-zinc-100">{enabledRulesCount}</dd>
              </div>
              <div class="col-span-2 flex items-start justify-between gap-3 border-t border-slate-200 pt-1.5 dark:border-white/10">
                <dt>Última leitura</dt>
                <dd class="max-w-[150px] text-right font-mono text-[10px] text-slate-500 dark:text-zinc-400">
                  {formatReadableDateTime(consoleStore.lastAlertReadAt)}
                </dd>
              </div>
            </dl>
          </section>

          <section class="rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-3 dark:border-white/10 dark:bg-[#121215]">
            <h3 class="text-sm font-semibold text-slate-800 dark:text-white">
              {editingRuleId ? 'Editar Regra' : 'Nova Regra'}
            </h3>

            <div class="mt-2 space-y-2">
              <input
                bind:value={ruleName}
                class="h-9 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-slate-400 dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:border-zinc-500"
                placeholder="Nome da regra"
              />

              <label class="flex items-center gap-2 text-[12px] text-slate-600 dark:text-zinc-300">
                <input
                  bind:checked={ruleEnabled}
                  type="checkbox"
                  class="rounded border-slate-300 text-blue-600 focus:ring-blue-500 dark:border-white/20"
                />
                Regra habilitada
              </label>

              <div>
                <div class="mb-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400 dark:text-zinc-500">Níveis</div>
                <div class="flex flex-wrap gap-1.5">
                  {#each LEVELS as level}
                    <button
                      type="button"
                      class={`rounded-full px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.08em] transition ${ruleLevels.includes(level) ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-100 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800'}`}
                      onclick={() => toggleRuleLevel(level)}
                    >
                      {CONSOLE_LEVEL_LABELS[level]}
                    </button>
                  {/each}
                </div>
              </div>

              <div>
                <div class="mb-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400 dark:text-zinc-500">Alvo</div>
                <div class="space-y-1.5 text-[12px] text-slate-600 dark:text-zinc-300">
                  {#each ALERT_TARGETS as target}
                    <label class="flex items-center gap-2">
                      <input
                        bind:group={ruleTargetType}
                        type="radio"
                        name="console-alert-target"
                        value={target.value}
                        class="border-slate-300 text-blue-600 focus:ring-blue-500 dark:border-white/20"
                      />
                      {target.label}
                    </label>
                  {/each}
                </div>
              </div>

              {#if ruleTargetType === 'selected_plants'}
                <div>
                  <div class="mb-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400 dark:text-zinc-500">Plantas</div>
                  <div class="max-h-28 space-y-1.5 overflow-auto pr-1 text-[12px] text-slate-600 dark:text-zinc-300">
                    {#if plantOptions.length === 0}
                      <div class="text-slate-500 dark:text-zinc-500">Nenhuma planta conhecida.</div>
                    {:else}
                      {#each plantOptions as plant}
                        <label class="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={rulePlantIds.includes(plant.plantId)}
                            onchange={() => toggleRulePlant(plant.plantId)}
                            class="rounded border-slate-300 text-blue-600 focus:ring-blue-500 dark:border-white/20"
                          />
                          {plant.plantName}
                        </label>
                      {/each}
                    {/if}
                  </div>
                </div>
              {/if}

              <div class="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  class="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/10 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
                  onclick={submitRule}
                  disabled={savingRule || !ruleName.trim()}
                >
                  {editingRuleId ? 'Atualizar' : 'Criar regra'}
                </button>

                {#if editingRuleId}
                  <button
                    type="button"
                    class="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-600 shadow-sm transition hover:bg-slate-50 dark:border-white/10 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
                    onclick={resetRuleForm}
                  >
                    Cancelar
                  </button>
                {/if}
              </div>
            </div>
          </section>

          <section class="rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-3 dark:border-white/10 dark:bg-[#121215]">
            <div class="flex items-center justify-between gap-3">
              <h3 class="text-sm font-semibold text-slate-800 dark:text-white">Regras Salvas</h3>
              <span class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-zinc-500">
                {rules.length}
              </span>
            </div>

            {#if rules.length === 0}
              <p class="mt-2 text-sm text-slate-500 dark:text-zinc-500">Nenhuma regra cadastrada.</p>
            {:else}
              <div class="mt-2 space-y-2">
                {#each rules as rule}
                  <article class="rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-white/10 dark:bg-black/20">
                    <div class="flex items-start justify-between gap-3">
                      <div class="min-w-0">
                        <div class="truncate text-sm font-medium text-slate-800 dark:text-zinc-100">{rule.name}</div>
                        <div class="mt-0.5 text-[11px] leading-4 text-slate-500 dark:text-zinc-400">
                          {rule.enabled ? 'Ativa' : 'Pausada'} · {describeRuleLevels(rule)} · {describeTarget(rule.target)}
                        </div>
                      </div>

                      <div class="flex gap-2 text-[10px] font-medium uppercase tracking-[0.08em] text-slate-500 dark:text-zinc-400">
                        <button type="button" class="transition hover:text-slate-800 dark:hover:text-zinc-200" onclick={() => editRule(rule)}>
                          Editar
                        </button>
                        <button type="button" class="transition hover:text-rose-600 dark:hover:text-rose-300" onclick={() => removeRule(rule.id)}>
                          Remover
                        </button>
                      </div>
                    </div>
                  </article>
                {/each}
              </div>
            {/if}
          </section>
        </div>
      </aside>
    </div>
  </div>
</div>
