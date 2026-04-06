<script lang="ts">
  import { onMount } from 'svelte';
  import { PanelLeft } from 'lucide-svelte';
  import { appStore } from '$lib/stores/data.svelte';
  import Sidebar from '$lib/components/layout/Sidebar.svelte';
  import PlotterWorkspaceModule from '$lib/components/modules/PlotterWorkspaceModule.svelte';
  import AnalyzerModule from '$lib/components/modules/AnalyzerModule.svelte';
  import PluginsModule from '$lib/components/modules/PluginsModule.svelte';
  import ConsoleModule from '$lib/components/modules/ConsoleModule.svelte';
  import GlobalSettingsModal from '$lib/components/modals/GlobalSettingsModal.svelte';
  import { appLogger, installAppLogger } from '$lib/services/appLogger';
  import { loadSystemPlugins } from '$lib/services/plugin';
  import { consoleStore } from '$lib/stores/consoleStore.svelte';

  let showControllerPanel = $state(false);
  let isMobileLayout = $state(false);
  let mobileSidebarOpen = $state(false);

  function updateLayoutState() {
    if (typeof window === 'undefined') return;
    isMobileLayout = window.innerWidth < 1024;
    if (!isMobileLayout) {
      mobileSidebarOpen = false;
    }
  }

  onMount(() => {
    updateLayoutState();
    const handleResize = () => updateLayoutState();
    window.addEventListener('resize', handleResize);
    const cleanupLogger = installAppLogger();

    void (async () => {
      try {
        await consoleStore.initialize();
        await loadSystemPlugins();
      } catch (error) {
        appLogger.error('Erro ao carregar plugins iniciais:', error);
      }
    })();

    return () => {
      cleanupLogger();
      window.removeEventListener('resize', handleResize);
    };
  });

  $effect(() => {
    const theme = appStore.state.theme || 'dark';
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    const body = document.body;
    const isDark = theme === 'dark';
    root.classList.toggle('dark', isDark);
    body.classList.toggle('dark', isDark);
    root.style.colorScheme = isDark ? 'dark' : 'light';
  });
</script>

<div class="h-dvh w-full select-none overflow-hidden">
  <div class="flex h-full w-full bg-slate-100 dark:bg-zinc-950 text-slate-800 dark:text-zinc-100 font-sans overflow-hidden transition-colors duration-300">
    {#if isMobileLayout && mobileSidebarOpen}
      <button
        type="button"
        class="fixed inset-0 z-40 bg-black/50 backdrop-blur-[1px] lg:hidden"
        aria-label="Fechar menu lateral"
        onclick={() => mobileSidebarOpen = false}
      ></button>
    {/if}

    <Sidebar
      theme={appStore.state.theme || 'dark'}
      sidebarCollapsed={appStore.state.sidebarCollapsed ?? true}
      activeModule={appStore.state.activeModule || 'plotter'}
      isMobile={isMobileLayout}
      mobileOpen={mobileSidebarOpen}
      onRequestClose={() => mobileSidebarOpen = false}
      onNavigate={() => {
        if (isMobileLayout) mobileSidebarOpen = false;
      }}
    />

    {#if isMobileLayout}
      <button
        type="button"
        class="fixed left-3 top-3 z-30 inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white/95 text-slate-700 shadow-sm backdrop-blur dark:border-white/10 dark:bg-zinc-900/95 dark:text-zinc-200 lg:hidden"
        aria-label="Abrir menu lateral"
        onclick={() => mobileSidebarOpen = true}
      >
        <PanelLeft size={18} />
      </button>
    {/if}

    <main class="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <div class="flex-1 flex flex-col min-w-0 min-h-0" style:display={appStore.state.activeModule === 'plotter' ? 'flex' : 'none'}>
        <PlotterWorkspaceModule
          plants={appStore.plotterPlants}
          activePlantId={appStore.activePlotterPlantId ?? appStore.plotterPlants[0]?.id ?? ''}
          theme={appStore.state.theme || 'dark'}
          active={appStore.state.activeModule === 'plotter'}
          bind:showControllerPanel
        />
      </div>
      <div class="flex-1 flex flex-col min-w-0 min-h-0" style:display={appStore.state.activeModule === 'analyzer' ? 'flex' : 'none'}>
        <AnalyzerModule
          theme={appStore.state.theme || 'dark'}
          active={appStore.state.activeModule === 'analyzer'}
        />
      </div>
      <div class="flex-1 flex flex-col min-w-0 min-h-0" style:display={appStore.state.activeModule === 'plugins' ? 'flex' : 'none'}>
        <PluginsModule
          theme={appStore.state.theme || 'dark'}
          active={appStore.state.activeModule === 'plugins'}
        />
      </div>
      <div class="flex-1 flex flex-col min-w-0 min-h-0" style:display={appStore.state.activeModule === 'console' ? 'flex' : 'none'}>
        <ConsoleModule
          theme={appStore.state.theme || 'dark'}
          active={appStore.state.activeModule === 'console'}
        />
      </div>

      <GlobalSettingsModal showGlobalSettings={appStore.state.showGlobalSettings || false} />
    </main>
  </div>
</div>
