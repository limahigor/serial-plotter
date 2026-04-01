<script lang="ts">
  import { onMount } from 'svelte';
  import { Plus, X } from 'lucide-svelte';

  export interface WorkspaceTabItem {
    id: string;
    name: string;
    closable?: boolean;
    indicatorClass?: string;
    placeholder?: boolean;
  }

  let {
    items,
    activeId,
    onSelect,
    onAdd,
    onReorder,
    onRemove,
    addLabel = 'Adicionar',
    addButtonRef = $bindable(),
  }: {
    items: WorkspaceTabItem[];
    activeId: string;
    onSelect: (id: string) => void;
    onAdd: () => void;
    onReorder?: (sourceId: string, targetId: string, position: 'before' | 'after') => void;
    onRemove?: (id: string) => void;
    addLabel?: string;
    addButtonRef?: HTMLButtonElement;
  } = $props();

  let tabsViewportRef = $state<HTMLDivElement | undefined>(undefined);
  let tabsTrackRef = $state<HTMLDivElement | undefined>(undefined);
  let tabsItemsRef = $state<HTMLDivElement | undefined>(undefined);
  let inlineAddButtonRef = $state<HTMLButtonElement | undefined>(undefined);
  let fixedAddButtonRef = $state<HTMLButtonElement | undefined>(undefined);
  let useFixedAddButton = $state(false);
  let draggedTabId = $state<string | null>(null);
  let dropTargetId = $state<string | null>(null);
  let dropPosition = $state<'before' | 'after'>('before');
  let dragPreviewElement = $state<HTMLDivElement | null>(null);

  function syncBoundAddButtonRef(): void {
    addButtonRef = useFixedAddButton ? fixedAddButtonRef : inlineAddButtonRef;
  }

  function updateAddButtonMode(): void {
    if (!tabsViewportRef || !tabsTrackRef || !tabsItemsRef) {
      useFixedAddButton = false;
      syncBoundAddButtonRef();
      return;
    }

    const addButtonWidth = (inlineAddButtonRef?.offsetWidth ?? fixedAddButtonRef?.offsetWidth ?? 32) + 8;
    useFixedAddButton = tabsItemsRef.scrollWidth + addButtonWidth > tabsViewportRef.clientWidth;
    syncBoundAddButtonRef();
  }

  onMount(() => {
    updateAddButtonMode();

    if (!tabsViewportRef || !tabsTrackRef || !tabsItemsRef || typeof ResizeObserver === 'undefined') {
      return;
    }

    const observer = new ResizeObserver(() => {
      updateAddButtonMode();
    });

    observer.observe(tabsViewportRef);
    observer.observe(tabsTrackRef);
    observer.observe(tabsItemsRef);

    return () => observer.disconnect();
  });

  $effect(() => {
    items.length;
    activeId;
    queueMicrotask(() => updateAddButtonMode());
  });

  $effect(() => {
    useFixedAddButton;
    inlineAddButtonRef;
    fixedAddButtonRef;
    tabsItemsRef;
    syncBoundAddButtonRef();
  });

  function resetDragState(): void {
    draggedTabId = null;
    dropTargetId = null;
    dropPosition = 'before';
    dragPreviewElement?.remove();
    dragPreviewElement = null;
  }

  function isReorderEnabled(item: WorkspaceTabItem): boolean {
    return !item.placeholder && typeof onReorder === 'function';
  }

  function resolveDropPosition(event: DragEvent, itemIndex: number): 'before' | 'after' {
    const target = event.currentTarget as HTMLElement | null;
    if (!target) return 'before';
    const rect = target.getBoundingClientRect();
    const threshold = itemIndex === 0 ? rect.width * 0.75 : rect.width / 2;
    return event.clientX >= rect.left + threshold ? 'after' : 'before';
  }

  function createDragPreview(label: string): HTMLDivElement | null {
    if (typeof document === 'undefined') return null;

    const preview = document.createElement('div');
    preview.textContent = label;
    preview.style.position = 'fixed';
    preview.style.left = '-9999px';
    preview.style.top = '-9999px';
    preview.style.pointerEvents = 'none';
    preview.style.maxWidth = '160px';
    preview.style.padding = '6px 10px';
    preview.style.borderRadius = '12px';
    preview.style.border = '1px solid rgba(148, 163, 184, 0.35)';
    preview.style.background = 'rgba(15, 23, 42, 0.92)';
    preview.style.color = '#f8fafc';
    preview.style.font = '600 12px system-ui, sans-serif';
    preview.style.whiteSpace = 'nowrap';
    preview.style.overflow = 'hidden';
    preview.style.textOverflow = 'ellipsis';
    preview.style.boxShadow = '0 8px 24px rgba(15, 23, 42, 0.22)';
    document.body.appendChild(preview);
    return preview;
  }

  function handleDragStart(event: DragEvent, item: WorkspaceTabItem): void {
    if (!isReorderEnabled(item)) return;

    draggedTabId = item.id;
    dragPreviewElement = createDragPreview(item.name);
    event.dataTransfer?.setData('text/plain', item.id);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
      if (dragPreviewElement) {
        event.dataTransfer.setDragImage(dragPreviewElement, 16, 16);
      }
    }
  }

  function handleDragOver(event: DragEvent, item: WorkspaceTabItem, itemIndex: number): void {
    if (!isReorderEnabled(item) || !draggedTabId || draggedTabId === item.id) return;

    event.preventDefault();
    dropTargetId = item.id;
    dropPosition = resolveDropPosition(event, itemIndex);
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move';
    }
  }

  function handleDrop(event: DragEvent, item: WorkspaceTabItem, itemIndex: number): void {
    if (!isReorderEnabled(item) || !draggedTabId || draggedTabId === item.id) {
      resetDragState();
      return;
    }

    event.preventDefault();
    const position = dropTargetId === item.id ? dropPosition : resolveDropPosition(event, itemIndex);
    onReorder?.(draggedTabId, item.id, position);
    resetDragState();
  }
</script>

<header class="flex h-11 items-end border-b border-slate-200 bg-white px-2 pt-1 select-none print:hidden dark:border-white/5 dark:bg-[#0c0c0e]">
  <div bind:this={tabsViewportRef} class="flex min-w-0 flex-1 overflow-x-auto">
    <div bind:this={tabsTrackRef} class="flex min-w-max items-end gap-1">
      <div bind:this={tabsItemsRef} class="flex min-w-max items-end gap-1">
        {#each items as item, itemIndex (item.id)}
          <div
            class="group relative flex h-9 min-w-[88px] max-w-[180px] items-center sm:min-w-[112px]"
            role="presentation"
            draggable={isReorderEnabled(item)}
            ondragstart={(event) => handleDragStart(event, item)}
            ondragover={(event) => handleDragOver(event, item, itemIndex)}
            ondrop={(event) => handleDrop(event, item, itemIndex)}
            ondragend={resetDragState}
          >
            {#if dropTargetId === item.id}
              <span
                class={`pointer-events-none absolute inset-y-1 z-10 w-0.5 rounded-full bg-blue-500 ${
                  dropPosition === 'after' ? 'right-0' : 'left-0'
                }`}
              ></span>
            {/if}
            <button
              onclick={() => !item.placeholder && onSelect(item.id)}
              class={`flex h-full w-full items-center gap-2 rounded-t-xl border-x border-t px-2.5 pr-7 text-xs font-semibold transition-all ${
                activeId === item.id
                  ? 'mb-[-1px] border-slate-300 border-b-slate-50 bg-slate-50 text-slate-800 dark:border-white/10 dark:border-b-[#18181b] dark:bg-[#18181b] dark:text-white'
                  : 'border-transparent bg-transparent text-slate-500 hover:bg-slate-100 dark:text-zinc-400 dark:hover:bg-white/5'
              } ${item.placeholder ? 'italic text-slate-400 dark:text-zinc-500' : ''}`}
            >
              {#if item.indicatorClass}
                <span class={`h-2 w-2 rounded-full ${item.indicatorClass}`}></span>
              {/if}
              <span class="truncate">{item.name}</span>
            </button>

            {#if item.closable && onRemove}
              <button
                onclick={(event: MouseEvent) => { event.stopPropagation(); onRemove(item.id); }}
                class="absolute right-1 top-1/2 -translate-y-1/2 rounded p-1 opacity-100 transition-all hover:bg-red-100 hover:text-red-600 sm:opacity-0 sm:group-hover:opacity-100 dark:hover:bg-red-900/30"
                aria-label={`Fechar ${item.name}`}
              >
                <X size={12} strokeWidth={2.5} />
              </button>
            {/if}
          </div>
        {/each}
      </div>

      {#if !useFixedAddButton}
        <button
          bind:this={inlineAddButtonRef}
          onclick={onAdd}
          class="mb-0.5 ml-1 flex h-8 w-8 shrink-0 items-center justify-center self-end rounded-lg border border-transparent text-slate-500 transition-colors hover:bg-slate-100 dark:text-zinc-400 dark:hover:bg-white/5"
          title={addLabel}
          aria-label={addLabel}
        >
          <Plus size={16} />
        </button>
      {/if}
    </div>
  </div>

  {#if useFixedAddButton}
    <button
      bind:this={fixedAddButtonRef}
      onclick={onAdd}
      class="mb-0.5 ml-1 flex h-8 w-8 shrink-0 items-center justify-center self-end rounded-lg border border-transparent text-slate-500 transition-colors hover:bg-slate-100 dark:text-zinc-400 dark:hover:bg-white/5"
      title={addLabel}
      aria-label={addLabel}
    >
      <Plus size={16} />
    </button>
  {/if}
</header>
