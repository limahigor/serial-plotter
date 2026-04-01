<script lang="ts">
  import DraftNumberInput from './DraftNumberInput.svelte';
  import SimpleToggle from './SimpleToggle.svelte';
  import type { ParamType } from '$lib/types/controller';

  interface Props {
    label: string;
    type: ParamType;
    value: number | boolean | string;
    onChange?: (value: number | boolean | string) => void;
    onValidityChange?: (isValid: boolean) => void;
  }

  let { label, type, value, onChange, onValidityChange } = $props();
  const id = `param-${crypto.randomUUID().substring(0, 8)}`;

  let draftValue = $state('');
  let lastReportedValidity = $state<boolean | null>(null);

  function notifyValidity(isValid: boolean) {
    if (lastReportedValidity === isValid) {
      return;
    }

    lastReportedValidity = isValid;
    onValidityChange?.(isValid);
  }

  function syncDraft(nextValue: number | boolean | string) {
    const normalized = nextValue === null || nextValue === undefined ? '' : String(nextValue);
    if (draftValue !== normalized) {
      draftValue = normalized;
    }
  }

  $effect(() => {
    if (type === 'boolean') {
      notifyValidity(true);
      return;
    }

    if (type === 'string') {
      syncDraft(value);
      notifyValidity(true);
    }
  });

  function handleToggleChange() {
    notifyValidity(true);
    onChange?.(!(value as boolean));
  }

  function handleTextInput(event: Event) {
    const nextValue = (event.target as HTMLInputElement).value;
    draftValue = nextValue;
    notifyValidity(true);
    onChange?.(nextValue);
  }
</script>

{#if type === 'boolean'}
  <div class="flex items-center justify-between py-1">
    <label for={id} class="text-xs font-medium text-slate-600 dark:text-slate-400">{label}</label>
    <SimpleToggle
      checked={value as boolean}
      onchange={handleToggleChange}
      ariaLabel={label}
    />
  </div>
{:else}
  <div class="flex items-start justify-between gap-3 group">
    <label for={id} class="pt-2 text-xs font-medium text-slate-600 dark:text-slate-400 truncate flex-1">{label}</label>
    <div class="relative w-28">
      {#if type === 'number'}
        <DraftNumberInput
          inputId={id}
          value={typeof value === 'number' ? value : 0}
          inputClass="w-full bg-white dark:bg-zinc-800 border border-slate-300 dark:border-white/10 rounded-md px-2.5 py-1.5 text-xs text-slate-900 dark:text-zinc-200 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-all shadow-sm font-mono text-center"
          onCommit={(nextValue) => onChange?.(nextValue)}
          {onValidityChange}
        />
      {:else}
        <input
          {id}
          type="text"
          value={draftValue}
          oninput={handleTextInput}
          class="w-full bg-white dark:bg-zinc-800 border border-slate-300 dark:border-white/10 rounded-md px-2.5 py-1.5 text-xs text-slate-900 dark:text-zinc-200 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-all shadow-sm text-left"
        />
      {/if}
    </div>
  </div>
{/if}
