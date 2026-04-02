<script lang="ts">
  import type { ComponentType } from 'svelte';

  interface Props {
    icon: ComponentType;
    label: string;
    active?: boolean;
    collapsed?: boolean;
    badgeCount?: number;
    onclick?: () => void;
  }

  let { icon: Icon, label, active = false, collapsed = false, badgeCount = 0, onclick }: Props = $props();
</script>

<button
  {onclick}
  aria-current={active ? 'page' : 'false'}
  title={collapsed ? label : ''}
  class={`
    w-full flex items-center rounded-xl transition-all relative group
    ${collapsed ? 'justify-center p-2.5' : 'gap-3 px-3.5 py-2.5'}
    ${active
      ? 'bg-blue-50 text-blue-700 shadow-sm ring-1 ring-blue-100 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20'
      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/5 hover:text-slate-900 dark:hover:text-zinc-200'
    }
    focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:ring-offset-2 dark:focus:ring-offset-zinc-900
  `}
>
  <div class={`flex-shrink-0 ${active ? 'text-blue-600 dark:text-blue-400' : 'text-slate-500 dark:text-slate-500'}`}>
    <Icon size={20} />
  </div>
  {#if !collapsed}
    <span class="text-sm font-medium truncate">{label}</span>
  {/if}
  {#if badgeCount > 0}
    <span
      class={`absolute rounded-full bg-rose-500 text-white text-[10px] font-semibold min-w-5 h-5 px-1 flex items-center justify-center shadow-sm ${collapsed ? 'right-1 top-1' : 'right-2 top-1/2 -translate-y-1/2'}`}
      aria-label={`${badgeCount} alertas pendentes`}
    >
      {badgeCount > 99 ? '99+' : badgeCount}
    </span>
  {/if}
</button>
