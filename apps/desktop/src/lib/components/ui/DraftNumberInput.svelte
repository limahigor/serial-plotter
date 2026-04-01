<script lang="ts">
  interface Props {
    value: number;
    integer?: boolean;
    inputId?: string;
    placeholder?: string;
    disabled?: boolean;
    min?: number;
    max?: number;
    inputClass?: string;
    invalidMessage?: string;
    onCommit?: (value: number) => void;
    onValidityChange?: (isValid: boolean) => void;
  }

  let {
    value,
    integer = false,
    inputId,
    placeholder = '',
    disabled = false,
    min,
    max,
    inputClass = '',
    invalidMessage = 'Informe um numero valido',
    onCommit,
    onValidityChange,
  }: Props = $props();

  let draftValue = $state('');
  let error = $state<string | null>(null);
  let focused = $state(false);
  let lastReportedValidity = $state<boolean | null>(null);

  function reportValidity(isValid: boolean) {
    if (lastReportedValidity === isValid) {
      return;
    }

    lastReportedValidity = isValid;
    onValidityChange?.(isValid);
  }

  function formatCommittedValue(nextValue: number): string {
    if (!Number.isFinite(nextValue)) {
      return '';
    }

    return String(integer ? Math.trunc(nextValue) : nextValue);
  }

  function normalizeRawValue(rawValue: string): string {
    return rawValue.trim().replace(',', '.');
  }

  function parseDraftValue(rawValue: string): number | null {
    const normalized = normalizeRawValue(rawValue);
    if (!normalized) {
      return null;
    }

    if (integer) {
      if (!/^[+-]?\d+$/.test(normalized)) {
        return null;
      }

      const parsed = Number.parseInt(normalized, 10);
      return Number.isFinite(parsed) ? parsed : null;
    }

    if (!/^[+-]?(?:\d+\.?\d*|\.\d+)$/.test(normalized)) {
      return null;
    }

    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function isTransientDraftValue(rawValue: string): boolean {
    const normalized = normalizeRawValue(rawValue);
    if (normalized === '') {
      return true;
    }

    if (integer) {
      return /^[+-]?$/.test(normalized);
    }

    return /^(?:[+-]?|[+-]?\d+[.]?|[+-]?[.]?)$/.test(normalized);
  }

  function respectsBounds(parsedValue: number): boolean {
    if (min != null && parsedValue < min) {
      return false;
    }

    if (max != null && parsedValue > max) {
      return false;
    }

    return true;
  }

  function syncDraftFromValue(nextValue: number) {
    const formattedValue = formatCommittedValue(nextValue);
    if (!focused && draftValue !== formattedValue) {
      draftValue = formattedValue;
    }

    if (!focused) {
      error = null;
      reportValidity(true);
    }
  }

  function revertToCommittedValue() {
    draftValue = formatCommittedValue(value);
    error = null;
    reportValidity(true);
  }

  function commitDraftValue() {
    const parsedValue = parseDraftValue(draftValue);
    if (parsedValue == null || !respectsBounds(parsedValue)) {
      revertToCommittedValue();
      return;
    }

    error = null;
    reportValidity(true);

    if (!Object.is(parsedValue, integer ? Math.trunc(value) : value)) {
      onCommit?.(parsedValue);
    }

    draftValue = formatCommittedValue(parsedValue);
  }

  function handleInput(event: Event) {
    const nextValue = (event.target as HTMLInputElement).value;
    draftValue = nextValue;

    if (isTransientDraftValue(nextValue)) {
      error = null;
      reportValidity(false);
      return;
    }

    const parsedValue = parseDraftValue(nextValue);
    if (parsedValue == null || !respectsBounds(parsedValue)) {
      error = invalidMessage;
      reportValidity(false);
      return;
    }

    error = null;
    reportValidity(true);
  }

  function handleFocus() {
    focused = true;
  }

  function handleBlur() {
    focused = false;
    commitDraftValue();
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      event.preventDefault();
      (event.currentTarget as HTMLInputElement).blur();
      return;
    }

    if (event.key === 'Escape') {
      event.preventDefault();
      revertToCommittedValue();
      (event.currentTarget as HTMLInputElement).blur();
    }
  }

  $effect(() => {
    syncDraftFromValue(value);
  });
</script>

<div>
  <input
    id={inputId}
    type="text"
    inputmode={integer ? 'numeric' : 'decimal'}
    value={draftValue}
    placeholder={placeholder}
    disabled={disabled}
    spellcheck="false"
    autocomplete="off"
    onfocus={handleFocus}
    oninput={handleInput}
    onblur={handleBlur}
    onkeydown={handleKeyDown}
    aria-invalid={error ? 'true' : 'false'}
    class={`${inputClass} ${error ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : ''}`.trim()}
  />

  {#if error}
    <div class="mt-1 text-[10px] text-red-500 dark:text-red-400 text-right">
      {error}
    </div>
  {/if}
</div>
