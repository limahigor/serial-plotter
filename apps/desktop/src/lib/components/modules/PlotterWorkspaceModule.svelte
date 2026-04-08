<script lang="ts">
  import { onMount } from 'svelte';
  import { untrack } from 'svelte';
  import { appStore } from '$lib/stores/data.svelte';
  import {
    clearPlant,
    getPlantData,
    getPlantSeriesCatalog,
    getPlantStats,
    getRecommendedPlantBufferConfig,
    getVariableStats,
    seedPlantSeriesCatalog,
    setPlantBufferConfig,
    setPlantSeriesCatalog,
    setPlantStats,
  } from '$lib/stores/plantData';
  import { exportPlantDataCSV, exportPlantDataJSON } from '$lib/services/export';
  import { formatTime } from '$lib/utils/format';
  import VariableGrid from '../charts/VariableGrid.svelte';
  import PlantTabs from '../plotter/PlantTabs.svelte';
  import PlotterToolbar from '../plotter/PlotterToolbar.svelte';
  import ChartContextMenu from '../plotter/ChartContextMenu.svelte';
  import ControllerPanel from '../plotter/ControllerPanel.svelte';
  import ControllerLibraryModal from '../modals/ControllerLibraryModal.svelte';
  import ControllerBindingsModal from '../modals/ControllerBindingsModal.svelte';
  import PlantRemovalModal from '../modals/PlantRemovalModal.svelte';
  import CreatePlantModal from '../modals/CreatePlantModal.svelte';
  import GenericModal from '../modals/GenericModal.svelte';
  import type { Plant, PlantVariable } from '$lib/types/plant';
  import { buildPlantSeriesCatalog, type Controller } from '$lib/types/plant';
  import type { PluginDefinition, PluginInstance } from '$lib/types/plugin';
  import {
    type ChartConfig,
    type ChartScaleState,
    type ChartViewState,
    type XAxisMode,
    defaultChartScaleState,
    defaultChartViewState,
    nextViewState,
    resetToGridView,
  } from '$lib/types/chart';
  import {
    closePlant,
    connectPlant,
    disconnectPlant,
    pausePlant,
    removeController,
    resumePlant,
    saveController,
    saveSetpoint,
    subscribePlantRuntimeEvents,
    type PlantRuntimeErrorEvent,
    type PlantRuntimeStatusEvent,
    type PlantRuntimeTelemetryEvent,
  } from '$lib/services/plant';
  import { createConfiguredController } from '$lib/services/plugin';
  import {
    isRegistryJsonFile,
    openDroppedRegistryFile,
    openPlantFromDialog,
  } from './plotter/openPlantFlow';
  import {
    buildChartConfigsByVariableIndex,
    hasDraggedFiles,
    resolveContextMenuPosition,
    resetPlantZoomState,
    resetScaleStatesForPlant,
    syncChartStateMaps,
    updateScaleStateMap,
  } from './plotter/chartState.js';
  import { createRuntimeTelemetryManager } from './plotter/runtimeTelemetry';
  import { getControllerActivationConflict } from '$lib/utils/controllerAssignments';
  import { buildContextSeriesControls, buildSeriesStyles, type SeriesStyle } from '$lib/utils/plotterSeries';
  import { appLogger } from '$lib/services/appLogger';
  import PluginInstanceConfigModal from '../modals/PluginInstanceConfigModal.svelte';

  let { plants, activePlantId, theme, active = true, showControllerPanel = $bindable(false) } = $props();

  interface ActiveVariableGroups {
    sensorEntries: Array<{ variable: PlantVariable; index: number }>;
    sensorVariables: PlantVariable[];
    actuatorVariables: PlantVariable[];
  }

  type EditableControllerField = 'name' | 'active' | 'inputVariableIds' | 'outputVariableIds';

  const EMPTY_VARIABLE_GROUPS: ActiveVariableGroups = {
    sensorEntries: [],
    sensorVariables: [],
    actuatorVariables: [],
  };

  let chartViewStatesByPlant: Record<string, ChartViewState> = $state({});
  let chartScaleStatesByPlant: Record<string, Record<number, ChartScaleState>> = $state({});

  $effect(() => {
    const next = syncChartStateMaps(
      plants,
      chartViewStatesByPlant,
      chartScaleStatesByPlant,
    );

    if (next.chartViewStatesByPlant !== chartViewStatesByPlant) {
      chartViewStatesByPlant = next.chartViewStatesByPlant;
    }

    if (next.chartScaleStatesByPlant !== chartScaleStatesByPlant) {
      chartScaleStatesByPlant = next.chartScaleStatesByPlant;
    }
  });

  const chartViewState = $derived(chartViewStatesByPlant[activePlantId] ?? defaultChartViewState());
  const activeChartScaleStates = $derived(chartScaleStatesByPlant[activePlantId] ?? {});
  const plantsById = $derived.by<Map<string, Plant>>(
    () => new Map(plants.map((plant: Plant) => [plant.id, plant]))
  );

  let seriesStyles = $state<Record<string, SeriesStyle>>({});

  let contextMenu = $state({ visible: false, x: 0, y: 0 });
  let contextSensorIndex = $state(0);
  let graphContainerRef = $state<HTMLDivElement | undefined>(undefined);

  let removeModal = $state({
    visible: false,
    plantId: '',
    plantName: '',
    reason: '' as 'confirm' | 'min-units'
  });

  let createPlantModal = $state(false);
  let editPlantModal = $state(false);
  let controllerLibraryModal = $state(false);
  let controllerConfigModal = $state(false);
  let controllerPluginToConfig = $state<PluginDefinition | null>(null);
  let controllerBindingsModal = $state(false);
  let controllerToEditBindings = $state<Controller | null>(null);
  let openPlantLoading = $state(false);
  let dragOverlay = $state(false);
  let dragDepth = $state(0);
  let plantActionLoading = $state<'connect' | 'pause' | 'remove' | null>(null);
  let feedbackModal = $state({
    visible: false,
    type: 'error' as 'info' | 'error' | 'warning' | 'success',
    title: '',
    message: '',
    confirmLabel: 'Entendi',
  });
  let controllerRestartModal = $state({
    visible: false,
    plantId: '',
    controllerName: '',
  });

  const activePlant = $derived(plants.find((p: Plant) => p.id === activePlantId));
  const connectDisabledReason = $derived.by(() => {
    if (!activePlant || activePlant.connected) return '';
    if (activePlant.driver?.pluginId) return '';
    if (activePlant.driverId) {
      return 'O driver vinculado à planta não está carregado. Vincule um novo driver para ligar.';
    }
    return 'Configure um driver de comunicação antes de ligar a planta.';
  });
  const connectDisabled = $derived(connectDisabledReason.length > 0);
  const editDisabled = $derived(!!activePlant?.connected);

  $effect(() => {
    for (const plant of plants) {
      seedPlantSeriesCatalog(buildPlantSeriesCatalog(plant.id, plant.variables));
    }
  });

  const activeVariableGroups = $derived.by<ActiveVariableGroups>(() => {
    if (!activePlant) return EMPTY_VARIABLE_GROUPS;

    const sensorEntries: ActiveVariableGroups['sensorEntries'] = [];
    const sensorVariables: PlantVariable[] = [];
    const actuatorVariables: PlantVariable[] = [];

    for (const [index, variable] of activePlant.variables.entries()) {
      if (variable.type === 'sensor') {
        sensorEntries.push({ variable, index });
        sensorVariables.push(variable);
      } else if (variable.type === 'atuador') {
        actuatorVariables.push(variable);
      }
    }

    return { sensorEntries, sensorVariables, actuatorVariables };
  });

  const sensorVariables = $derived(activeVariableGroups.sensorEntries);
  const controllerSensorVariables = $derived(activeVariableGroups.sensorVariables);
  const controllerActuatorVariables = $derived(activeVariableGroups.actuatorVariables);

  const activeSeriesCatalog = $derived.by(() => {
    _displayTick;
    return activePlant ? getPlantSeriesCatalog(activePlant.id) : [];
  });

  const activeSeriesCatalogByKey = $derived.by(
    () => new Map(activeSeriesCatalog.map((entry) => [entry.key, entry]))
  );

  const contextSensor = $derived.by(() => {
    if (sensorVariables.length === 0) return null;
    const safeIndex = Math.max(0, Math.min(contextSensorIndex, sensorVariables.length - 1));
    return sensorVariables[safeIndex];
  });

  const contextChartScaleState = $derived.by<ChartScaleState>(() => {
    if (!contextSensor) return defaultChartScaleState();
    return activeChartScaleStates[contextSensor.index] ?? defaultChartScaleState();
  });

  $effect(() => {
    if (!activePlant) return;

    seriesStyles = buildSeriesStyles(activePlant, untrack(() => seriesStyles), activeSeriesCatalogByKey);
  });

  const contextSeriesControls = $derived.by(() => {
    if (!activePlant || !contextSensor) return [];

    return buildContextSeriesControls({
      plant: activePlant,
      contextSensor,
      seriesStyles,
      catalogByKey: activeSeriesCatalogByKey,
    });
  });

  const contextSeriesTitle = $derived(
    contextSensor ? `Linhas - ${contextSensor.variable.name}` : 'Linhas'
  );

  function toggleSeriesVisibility(key: string) {
    const current = seriesStyles[key];
    if (!current) return;
    seriesStyles = {
      ...seriesStyles,
      [key]: {
        ...current,
        visible: !current.visible,
      },
    };
  }

  function updateSeriesColor(key: string, color: string) {
    const current = seriesStyles[key];
    if (!current) return;
    seriesStyles = {
      ...seriesStyles,
      [key]: {
        ...current,
        color,
      },
    };
  }

  function showFeedbackModal(options: {
    type?: 'info' | 'error' | 'warning' | 'success';
    title: string;
    message: string;
    confirmLabel?: string;
  }) {
    feedbackModal = {
      visible: true,
      type: options.type ?? 'error',
      title: options.title,
      message: options.message,
      confirmLabel: options.confirmLabel ?? 'Entendi',
    };
  }

  function hideFeedbackModal() {
    feedbackModal.visible = false;
  }

  function showActionFailure(title: string, error: string | undefined, fallback: string) {
    showFeedbackModal({
      type: 'error',
      title,
      message: error || fallback,
    });
  }

  function getActivePlant(): Plant | null {
    return activePlant ?? null;
  }

  function isEditableControllerField(field: string): field is EditableControllerField {
    return (
      field === 'name' ||
      field === 'active' ||
      field === 'inputVariableIds' ||
      field === 'outputVariableIds'
    );
  }

  function findActiveController(controllerId: string): Controller | undefined {
    return activePlant?.controllers.find((controller: Controller) => controller.id === controllerId);
  }

  const telemetryManager = createRuntimeTelemetryManager({
    findPlantById: (plantId) => plantsById.get(plantId),
    updatePlantRuntimeState: (plantId, runtimeState) =>
      appStore.updatePlantRuntimeState(plantId, runtimeState),
  });

  function handleRuntimeTelemetry(event: PlantRuntimeTelemetryEvent) {
    telemetryManager.handleRuntimeTelemetry(event);
  }

  function handleRuntimeStatus(event: PlantRuntimeStatusEvent) {
    telemetryManager.handleRuntimeStatus(event);
  }

  function handleRuntimeError(event: PlantRuntimeErrorEvent) {
    if (plantActionLoading === 'connect') {
      return;
    }

    const plant = plantsById.get(event.plant_id);
    const title = plant ? `Falha na planta "${plant.name}"` : 'Falha na runtime da planta';
    showActionFailure(title, event.message, 'Falha na runtime da planta.');
  }

  onMount(() => {
    let unsubscribe: (() => void) | undefined;
    let disposed = false;
    const handleGlobalPointerDown = (event: PointerEvent) => {
      if (!contextMenu.visible) return;

      const target = event.target as HTMLElement | null;
      if (target?.closest('[data-chart-context-menu]')) {
        return;
      }

      closeContextMenu();
    };
    const handleGlobalScroll = () => {
      if (contextMenu.visible) {
        closeContextMenu();
      }
    };
    const handleWindowBlur = () => {
      if (contextMenu.visible) {
        closeContextMenu();
      }
    };

    window.addEventListener('pointerdown', handleGlobalPointerDown);
    window.addEventListener('scroll', handleGlobalScroll, true);
    window.addEventListener('blur', handleWindowBlur);

    void subscribePlantRuntimeEvents({
      onTelemetry: handleRuntimeTelemetry,
      onStatus: handleRuntimeStatus,
      onError: handleRuntimeError,
    })
      .then((cleanup) => {
        if (disposed) {
          cleanup();
          return;
        }

        unsubscribe = cleanup;
      })
      .catch((error) => {
        appLogger.error('Falha ao registrar listeners de runtime da planta:', error);
      });

    return () => {
      disposed = true;
      telemetryManager.dispose();
      unsubscribe?.();
      window.removeEventListener('pointerdown', handleGlobalPointerDown);
      window.removeEventListener('scroll', handleGlobalScroll, true);
      window.removeEventListener('blur', handleWindowBlur);
    };
  });

  async function handleOpenFile() {
    openPlantLoading = true;
    try {
      const result = await openPlantFromDialog();
      if (result.cancelled) {
        return;
      }

      if (result.warning) {
        showFeedbackModal({
          type: 'error',
          title: 'Driver ausente',
          message: result.warning,
        });
      }
    } catch (e) {
      appLogger.error('Erro ao abrir planta:', e);
      showActionFailure(
        'Falha ao abrir planta',
        e instanceof Error ? e.message : undefined,
        'Erro ao abrir planta',
      );
    } finally {
      openPlantLoading = false;
    }
  }

  function handleCreateNew() {
    createPlantModal = true;
  }

  function handleEditPlant() {
    if (!activePlant) return;
    if (activePlant.connected) {
      showFeedbackModal({
        type: 'warning',
        title: 'Edição bloqueada',
        message: 'Desligue a planta antes de editar suas configurações.',
      });
      return;
    }
    editPlantModal = true;
  }

  function handlePlantSaved(plant: Plant) {
    appStore.upsertPlant(plant);
    appStore.setActivePlantId(plant.id);
    setPlantSeriesCatalog(buildPlantSeriesCatalog(plant.id, plant.variables));
    setPlantStats(plant.id, plant.stats);
    setPlantBufferConfig(plant.id, getRecommendedPlantBufferConfig(plant.sampleTimeMs));
    createPlantModal = false;
    editPlantModal = false;
  }

  function handleRemovePlant(plantId: string) {
    removeModal = {
      visible: true,
      plantId,
      plantName: plantsById.get(plantId)?.name || '',
      reason: 'confirm'
    };
  }

  async function confirmRemovePlant() {
    if (removeModal.reason === 'confirm') {
      plantActionLoading = 'remove';
      const result = await closePlant(removeModal.plantId);
      if (result.success) {
        appStore.removePlant(removeModal.plantId);
        clearPlant(removeModal.plantId);
        telemetryManager.forgetRuntimeSession(removeModal.plantId);
        chartViewStatesByPlant = Object.fromEntries(
          Object.entries(chartViewStatesByPlant).filter(([plantId]) => plantId !== removeModal.plantId),
        );
        chartScaleStatesByPlant = Object.fromEntries(
          Object.entries(chartScaleStatesByPlant).filter(([plantId]) => plantId !== removeModal.plantId),
        );
      } else {
        showActionFailure(
          'Falha ao fechar planta',
          result.error,
          'Erro ao descarregar a planta do backend',
        );
      }

      plantActionLoading = null;
    }
    removeModal.visible = false;
  }

  function cancelRemovePlant() {
    removeModal.visible = false;
  }

  async function handleToggleConnect() {
    const plant = getActivePlant();
    if (!plant) return;

    if (!plant.connected && !plant.driver?.pluginId) {
      showActionFailure(
        'Driver obrigatório',
        connectDisabledReason,
        'Configure um driver de comunicação antes de ligar a planta.',
      );
      return;
    }

    const wasConnected = plant.connected;
    plantActionLoading = 'connect';
    const result = plant.connected
      ? await disconnectPlant(plant.id)
      : await connectPlant(plant.id);

    if (result.success && result.plant) {
      if (!wasConnected) {
        telemetryManager.preparePlantSessionStart(result.plant);
        chartScaleStatesByPlant = resetPlantZoomState(chartScaleStatesByPlant, result.plant.id);
      } else {
        telemetryManager.forgetRuntimeSession(result.plant.id);
      }

      appStore.upsertPlant(result.plant);
    } else {
      showActionFailure(
        plant.connected ? 'Falha ao desligar planta' : 'Falha ao iniciar planta',
        result.error,
        'Erro ao atualizar driver da planta',
      );
    }

    plantActionLoading = null;
  }

  async function handleTogglePause() {
    const plant = getActivePlant();
    if (!plant) return;

    const wasPaused = plant.paused;
    plantActionLoading = 'pause';
    const result = plant.paused
      ? await resumePlant(plant.id)
      : await pausePlant(plant.id);

    if (result.success && result.plant) {
      appStore.upsertPlant(result.plant);
      if (wasPaused) {
        telemetryManager.flushTelemetryBacklog(result.plant.id, result.plant);
      }
    } else {
      showActionFailure(
        plant.paused ? 'Falha ao retomar planta' : 'Falha ao pausar planta',
        result.error,
        'Erro ao atualizar pausa da planta',
      );
    }

    plantActionLoading = null;
  }

  async function handleExportCSV() {
    if (!activePlant) return;
    const data = getPlantData(activePlantId);
    if (data.length === 0) {
      showFeedbackModal({
        type: 'info',
        title: 'Nada para exportar',
        message: 'Sem dados para exportar em CSV.',
      });
      return;
    }

    const exported = await exportPlantDataCSV(activePlant, data);
    if (!exported) {
      showFeedbackModal({
        type: 'info',
        title: 'Exportação não concluída',
        message: 'A exportação de CSV foi cancelada ou falhou.',
      });
    }
  }

  async function handleExportJSON() {
    if (!activePlant) return;
    const data = getPlantData(activePlantId);
    if (data.length === 0) {
      showFeedbackModal({
        type: 'info',
        title: 'Nada para exportar',
        message: 'Sem dados para exportar em JSON.',
      });
      return;
    }

    const exported = await exportPlantDataJSON(activePlant, data);
    if (!exported) {
      showFeedbackModal({
        type: 'info',
        title: 'Exportação não concluída',
        message: 'A exportação de JSON foi cancelada ou falhou.',
      });
    }
  }

  function handlePrint() {
    window.print();
  }

  function resetZoom() {
    chartScaleStatesByPlant = resetScaleStatesForPlant(chartScaleStatesByPlant, activePlantId);
  }

  function setXAxisMode(mode: XAxisMode) {
    if (!contextSensor) {
      return;
    }

    chartScaleStatesByPlant = updateScaleStateMap(chartScaleStatesByPlant, activePlantId, contextSensor.index, (state) => ({
      ...state,
      xMode: mode,
      xMin: mode === 'manual' ? state.xMin : null,
      xMax: mode === 'manual' ? state.xMax : null,
    }));
  }

  let _displayTick = $state(0);

  function handleContextMenu(e: MouseEvent) {
    e.preventDefault();
    if (!graphContainerRef) return;

    let target = e.target as HTMLElement | null;
    while (target && target !== graphContainerRef) {
      const idx = target.dataset?.sensorIndex;
      if (idx !== undefined) {
        contextSensorIndex = parseInt(idx, 10);
        break;
      }
      target = target.parentElement;
    }

    const nextPosition = resolveContextMenuPosition(graphContainerRef, e);
    if (!nextPosition) return;

    contextMenu = { visible: true, x: nextPosition.x, y: nextPosition.y };
  }

  function closeContextMenu() {
    contextMenu.visible = false;
  }

  function addController() {
    if (!activePlant) return;
    controllerLibraryModal = true;
  }

  function handleControllerTemplateSelected(plugin: PluginDefinition) {
    if (!activePlant) return;

    controllerPluginToConfig = plugin;
    controllerConfigModal = true;
  }

  async function handleControllerConfigured(
    instance: PluginInstance,
    bindings?: { inputVariableIds: string[]; outputVariableIds: string[] }
  ) {
    if (!activePlant || !controllerPluginToConfig) return;

    const controller = createConfiguredController(
      controllerPluginToConfig,
      instance.config,
      {
        name: `${controllerPluginToConfig.name} ${activePlant.controllers.length + 1}`,
        active: false,
      }
    );

    const nextController = {
      ...controller,
      inputVariableIds: bindings?.inputVariableIds ?? [],
      outputVariableIds: bindings?.outputVariableIds ?? [],
    };

    if (activePlant.source === 'backend') {
      const response = await saveController({
        plantId: activePlant.id,
        controller: nextController,
        source: activePlant.source,
      });

      if (response.success && response.plant) {
        appStore.upsertPlant(response.plant);
      } else {
        showFeedbackModal({
          type: 'error',
          title: 'Falha ao adicionar controlador',
          message: response.error ?? 'Não foi possível persistir o controlador na planta.',
        });
        return;
      }
    } else {
      const { id: _id, ...localController } = nextController;
      appStore.addController(activePlant.id, localController);
    }

    controllerConfigModal = false;
    controllerPluginToConfig = null;
  }

  async function deleteController(controllerId: string) {
    const plant = getActivePlant();
    if (!plant) return;

    if (plant.source === 'backend') {
      const response = await removeController({
        plantId: plant.id,
        controllerId,
      });

      if (response.success && response.plant) {
        appStore.upsertPlant(response.plant);
        return;
      }

      showActionFailure(
        'Falha ao remover controlador',
        response.error,
        'Não foi possível remover o controlador da planta.',
      );
      return;
    }

    appStore.deleteController(plant.id, controllerId);
  }

  function updateControllerMeta(controllerId: string, field: string, value: unknown) {
    const plant = getActivePlant();
    if (!plant || !isEditableControllerField(field)) return;

    if (field === 'name' && typeof value === 'string') {
      appStore.updateControllerMeta(plant.id, controllerId, field, value);
      return;
    }

    if (field === 'active' && typeof value === 'boolean') {
      appStore.updateControllerMeta(plant.id, controllerId, field, value);
      return;
    }

    if (
      (field === 'inputVariableIds' || field === 'outputVariableIds') &&
      Array.isArray(value) &&
      value.every((item) => typeof item === 'string')
    ) {
      appStore.updateControllerMeta(plant.id, controllerId, field, value);
    }
  }

  function openControllerBindingsEditor(controllerId: string) {
    const controller = findActiveController(controllerId);
    if (!controller) return;

    controllerToEditBindings = controller;
    controllerBindingsModal = true;
  }

  function toggleControllerActive(controllerId: string, nextActive: boolean) {
    const plant = getActivePlant();
    if (!plant) return;

    const controller = plant.controllers.find((entry: Controller) => entry.id === controllerId);
    if (!controller) return;

    if (nextActive) {
      const conflict = getControllerActivationConflict(
        {
          ...controller,
          active: true,
        },
        plant.controllers,
        plant.variables
      );

      if (conflict) {
        showFeedbackModal({
          type: 'warning',
          title: 'Conflito de controlador',
          message: conflict,
        });
        return;
      }
    }

    appStore.updateControllerMeta(plant.id, controllerId, 'active', nextActive);
  }

  function updateControllerBindings(
    controllerId: string,
    bindings: { inputVariableIds: string[]; outputVariableIds: string[] }
  ): string | null {
    const plant = getActivePlant();
    if (!plant) return 'Planta ativa não encontrada';

    const controller = plant.controllers.find((entry: Controller) => entry.id === controllerId);
    if (!controller) return 'Controlador não encontrado';

    const nextController: Controller = {
      ...controller,
      inputVariableIds: bindings.inputVariableIds,
      outputVariableIds: bindings.outputVariableIds,
    };

    if (controller.active) {
      const conflict = getControllerActivationConflict(
        nextController,
        plant.controllers,
        plant.variables,
      );
      if (conflict) {
        return conflict;
      }
    }

    appStore.updateControllerMeta(plant.id, controllerId, 'inputVariableIds', bindings.inputVariableIds);
    appStore.updateControllerMeta(plant.id, controllerId, 'outputVariableIds', bindings.outputVariableIds);
    return null;
  }

  function updateControllerParam(controllerId: string, paramKey: string, value: any) {
    const plant = getActivePlant();
    if (!plant) return;
    appStore.updateControllerParam(plant.id, controllerId, paramKey, value);
  }

  async function handleSaveControllerConfig(controllerId: string) {
    const plant = getActivePlant();
    if (!plant) {
      return { success: false, error: 'Planta ativa nao encontrada' };
    }

    const controller = plant.controllers.find((entry: Controller) => entry.id === controllerId);
    if (!controller) {
      return { success: false, error: 'Controlador nao encontrado' };
    }

    const response = await saveController({
      plantId: plant.id,
      controller,
      source: plant.source,
    });

    if (response.success && response.plant) {
      appStore.upsertPlant(response.plant);
      const savedController = response.plant.controllers.find((entry: Controller) => entry.id === controllerId);
      const deferred = savedController?.runtimeStatus === 'pending_restart';

      if (deferred) {
        controllerRestartModal = {
          visible: true,
          plantId: response.plant.id,
          controllerName: savedController?.name ?? controller.name,
        };
      }

      return {
        ...response,
        deferred,
      };
    }

    return response;
  }

  async function handleRestartPendingController() {
    const plantId = controllerRestartModal.plantId;
    controllerRestartModal.visible = false;
    if (!plantId) return;

    plantActionLoading = 'connect';

    const disconnectResult = await disconnectPlant(plantId);
    if (!disconnectResult.success || !disconnectResult.plant) {
      showActionFailure(
        'Falha ao desligar planta',
        disconnectResult.error,
        'Não foi possível desligar a planta para aplicar o controlador.',
      );
      plantActionLoading = null;
      return;
    }

    telemetryManager.forgetRuntimeSession(plantId);
    appStore.upsertPlant(disconnectResult.plant);

    const connectResult = await connectPlant(plantId);
    if (connectResult.success && connectResult.plant) {
      telemetryManager.preparePlantSessionStart(connectResult.plant);
      chartScaleStatesByPlant = resetPlantZoomState(chartScaleStatesByPlant, connectResult.plant.id);
      appStore.upsertPlant(connectResult.plant);
    } else {
      showActionFailure(
        'Falha ao religar planta',
        connectResult.error,
        'Não foi possível religar a planta para aplicar o controlador.',
      );
    }

    plantActionLoading = null;
  }

  async function updateSetpoint(varIndex: number, value: number) {
    const plant = getActivePlant();
    if (!plant) return;

    appStore.updateVariableSetpoint(plant.id, varIndex, value);

    const variable = plant.variables[varIndex];
    if (!variable || plant.source !== 'backend') return;

    const response = await saveSetpoint({
      plantId: plant.id,
      variableId: variable.id,
      setpoint: value,
    });

    if (response.success && response.plant) {
      appStore.upsertPlant(response.plant);
      return;
    }

    showActionFailure(
      'Falha ao salvar setpoint',
      response.error,
      'Não foi possível sincronizar o setpoint com o backend.',
    );
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
      return;
    }
    
    const state = chartViewStatesByPlant[activePlantId];
    if (!state) return;
    
    if (event.code === 'Space') {
      event.preventDefault();
      nextViewState(state);
    } else if (event.code === 'KeyH') {
      event.preventDefault();
      resetToGridView(state);
    }
  }

  $effect(() => {
    if (!active) return;
    const timer = setInterval(() => _displayTick++, 250);
    return () => clearInterval(timer);
  });

  $effect(() => {
    if (!active) return;
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  });

  const currentStats = $derived.by(() => {
    _displayTick;
    return getPlantStats(activePlantId);
  });

  const displayDt = $derived.by(() => {
    _displayTick;
    return activePlant?.connected ? currentStats.dt : 0;
  });
  const plantData = $derived(getPlantData(activePlantId));
  
  const variableStatsArray = $derived.by(() => {
    _displayTick;
    if (!activePlant) return [];
    return activePlant.variables.map((_: unknown, idx: number) => getVariableStats(activePlantId, idx));
  });

  const chartConfigsByVariableIndex = $derived.by<Record<number, { pvConfig: ChartConfig; mvConfig: ChartConfig }>>(() => {
    return buildChartConfigsByVariableIndex(sensorVariables, activeChartScaleStates);
  });

  function handleRangeChange(variableIndex: number, xMin: number, xMax: number) {
    chartScaleStatesByPlant = updateScaleStateMap(chartScaleStatesByPlant, activePlantId, variableIndex, (state) => ({
      ...state,
      xMode: 'manual',
      xMin: Math.min(xMin, xMax),
      xMax: Math.max(xMin, xMax),
    }));
  }

  function handleViewportChange(
    variableIndex: number,
    viewport: { xMin: number; xMax: number; yMin: number; yMax: number },
  ) {
    chartScaleStatesByPlant = updateScaleStateMap(chartScaleStatesByPlant, activePlantId, variableIndex, (state) => ({
      ...state,
      xMode: 'manual',
      xMin: Math.min(viewport.xMin, viewport.xMax),
      xMax: Math.max(viewport.xMin, viewport.xMax),
      sensorYMode: 'manual',
      sensorYMin: Math.min(viewport.yMin, viewport.yMax),
      sensorYMax: Math.max(viewport.yMin, viewport.yMax),
    }));
  }

  function handleActuatorViewportChange(
    variableIndex: number,
    viewport: { xMin: number; xMax: number; yMin: number; yMax: number },
  ) {
    chartScaleStatesByPlant = updateScaleStateMap(chartScaleStatesByPlant, activePlantId, variableIndex, (state) => ({
      ...state,
      xMode: 'manual',
      xMin: Math.min(viewport.xMin, viewport.xMax),
      xMax: Math.max(viewport.xMin, viewport.xMax),
      actuatorYMode: 'manual',
      actuatorYMin: Math.min(viewport.yMin, viewport.yMax),
      actuatorYMax: Math.max(viewport.yMin, viewport.yMax),
    }));
  }

  function handleResetViewport(variableIndex: number) {
    chartScaleStatesByPlant = updateScaleStateMap(chartScaleStatesByPlant, activePlantId, variableIndex, (state) => ({
      ...defaultChartScaleState(),
      windowSize: state.windowSize,
    }));
  }

  function handleDragEnter(event: DragEvent) {
    if (!active || !hasDraggedFiles(event)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
    dragDepth += 1;
    dragOverlay = true;
  }

  function handleDragOver(event: DragEvent) {
    if (!active || !hasDraggedFiles(event)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
    dragOverlay = true;
  }

  function handleDragLeave(event: DragEvent) {
    if (!active || !hasDraggedFiles(event)) return;
    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) {
      dragOverlay = false;
    }
  }

  async function handleDrop(event: DragEvent) {
    if (!active || !hasDraggedFiles(event)) return;
    event.preventDefault();
    dragDepth = 0;
    dragOverlay = false;

    const file = event.dataTransfer?.files?.[0];
    if (!file) return;

    if (!isRegistryJsonFile(file)) {
      showFeedbackModal({
        type: 'warning',
        title: 'Arquivo inválido',
        message: 'Apenas arquivos registry.json podem ser soltos no Plotter.',
      });
      return;
    }

    openPlantLoading = true;
    try {
      const { warning } = await openDroppedRegistryFile(file);
      if (warning) {
        showFeedbackModal({
          type: 'error',
          title: 'Driver ausente',
          message: warning,
        });
      }
    } catch (error) {
      appLogger.error('Erro ao abrir arquivo arrastado:', error);
      showFeedbackModal({
        type: 'error',
        title: 'Falha ao abrir planta',
        message: error instanceof Error ? error.message : 'Erro ao abrir planta',
      });
    } finally {
      openPlantLoading = false;
    }
  }
</script>

<svelte:window
  ondragenter={handleDragEnter}
  ondragover={handleDragOver}
  ondragleave={handleDragLeave}
  ondrop={handleDrop}
/>

<div
  class="flex flex-col h-full w-full min-h-0 bg-white dark:bg-[#09090b] text-slate-900 dark:text-white relative"
  role="presentation"
>
  {#if dragOverlay}
    <div class="pointer-events-none absolute inset-4 z-40 flex items-center justify-center rounded-[28px] border-2 border-dashed border-blue-500 bg-blue-500/10 backdrop-blur-sm">
      <div class="text-center">
        <svg class="mx-auto h-10 w-10 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M7 16l5-5 5 5M12 11v10M5 4h14" />
        </svg>
        <p class="mt-3 text-sm font-semibold text-blue-700 dark:text-blue-300">Solte um JSON exportado para abrir a planta no Plotter</p>
      </div>
    </div>
  {/if}

  <PlantTabs
    {plants}
    {activePlantId}
    onSelect={(id) => appStore.setActivePlantId(id)}
    onOpenFile={handleOpenFile}
    onCreateNew={handleCreateNew}
    onReorder={(sourceId, targetId, position) => appStore.reorderPlants(sourceId, targetId, position)}
    onRemove={handleRemovePlant}
  />

  {#if plants.length === 0}
    <div class="flex-1 flex items-center justify-center bg-slate-50 p-8 dark:bg-[#09090b]">
      <div
        class="flex w-full max-w-3xl flex-col items-center justify-center gap-6 rounded-[28px] border border-slate-200 bg-white p-12 shadow-sm transition-colors hover:border-blue-300 dark:border-white/10 dark:bg-[#0c0c0e] dark:hover:border-blue-500/40"
        role="region"
        aria-label="Área para criar ou abrir uma planta"
      >
        <div class="w-20 h-20 rounded-2xl bg-slate-100 dark:bg-zinc-800 flex items-center justify-center">
          <svg class="w-10 h-10 text-slate-400 dark:text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        
        <div class="text-center space-y-2">
          <h2 class="text-2xl font-semibold text-slate-700 dark:text-zinc-200">
            Nenhuma planta ativa
          </h2>
          <p class="max-w-md text-sm text-slate-500 dark:text-zinc-400">
            Crie uma nova planta ou abra um arquivo <code class="px-1 py-0.5 bg-slate-200 dark:bg-zinc-700 rounded text-xs">.json</code> para começar a plotar dados
          </p>
        </div>

        <div class="mt-2 flex flex-wrap justify-center gap-3">
          <button
            type="button"
            onclick={handleCreateNew}
            class="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors shadow-sm"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            Nova Planta
          </button>
          <button
            type="button"
            onclick={handleOpenFile}
            disabled={openPlantLoading}
            class="flex items-center gap-2 px-5 py-2.5 bg-slate-200 dark:bg-zinc-700 hover:bg-slate-300 dark:hover:bg-zinc-600 text-slate-700 dark:text-zinc-200 font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z" />
            </svg>
            {openPlantLoading ? 'Abrindo...' : 'Abrir Arquivo'}
          </button>
        </div>
      </div>
    </div>
  {:else}
  <div class="plotter-workspace-shell flex-1 flex min-h-0 flex-col md:flex-row overflow-hidden bg-slate-50 dark:bg-[#09090b] relative">
    <div class="flex-1 flex min-h-0 flex-col min-w-0 relative">
      <PlotterToolbar
        plant={activePlant}
        {currentStats}
        dt={displayDt}
        {connectDisabled}
        connectDisabledReason={connectDisabledReason}
        {editDisabled}
        bind:showControllerPanel
        onToggleConnect={handleToggleConnect}
        onTogglePause={handleTogglePause}
        onEditPlant={handleEditPlant}
        onResetZoom={resetZoom}
        onExportCSV={handleExportCSV}
        onExportJSON={handleExportJSON}
        onPrint={handlePrint}
        {formatTime}
      />

      <div
        bind:this={graphContainerRef}
        class="plotter-graph-area flex-1 flex min-h-0 flex-col p-3 gap-3 overflow-hidden relative"
        oncontextmenu={handleContextMenu}
        role="application"
        aria-label="Área de gráficos"
      >
        <ChartContextMenu
          bind:visible={contextMenu.visible}
          x={contextMenu.x}
          y={contextMenu.y}
          chartState={contextChartScaleState}
          onSetXAxisMode={setXAxisMode}
          seriesControls={contextSeriesControls}
          seriesTitle={contextSeriesTitle}
          onToggleSeries={toggleSeriesVisibility}
          onChangeSeriesColor={updateSeriesColor}
          onClose={closeContextMenu}
        />

        {#if activePlant}
          <VariableGrid
            variables={activePlant.variables}
            data={plantData}
            {chartConfigsByVariableIndex}
            {theme}
            viewMode={chartViewState.viewMode}
            focusedIndex={chartViewState.focusedVariableIndex}
            lineStyles={seriesStyles}
            variableStats={variableStatsArray}
            onRangeChange={handleRangeChange}
            onViewportChange={handleViewportChange}
            onActuatorViewportChange={handleActuatorViewportChange}
            onResetViewport={handleResetViewport}
          />
        {/if}
      </div>
    </div>

    <ControllerPanel
      bind:visible={showControllerPanel}
      plant={activePlant}
      onAddController={addController}
      onDeleteController={deleteController}
      onEditControllerBindings={openControllerBindingsEditor}
      onSaveControllerConfig={handleSaveControllerConfig}
      onToggleControllerActive={toggleControllerActive}
      onUpdateControllerMeta={updateControllerMeta}
      onUpdateControllerParam={updateControllerParam}
      onUpdateSetpoint={updateSetpoint}
    />
  </div>
  {/if}

  <PlantRemovalModal
    bind:visible={removeModal.visible}
    plantName={removeModal.plantName}
    reason={removeModal.reason}
    onConfirm={confirmRemovePlant}
    onCancel={cancelRemovePlant}
  />

  <ControllerLibraryModal
    bind:visible={controllerLibraryModal}
    onClose={() => controllerLibraryModal = false}
    onSelect={handleControllerTemplateSelected}
  />

  <PluginInstanceConfigModal
    visible={controllerConfigModal}
    plugin={controllerPluginToConfig}
    instanceLabel={controllerPluginToConfig?.name}
    showVariableBindings={true}
    sensorVariables={controllerSensorVariables}
    actuatorVariables={controllerActuatorVariables}
    submitLabel="Adicionar controlador"
    onClose={() => {
      controllerConfigModal = false;
      controllerPluginToConfig = null;
    }}
    onConfigured={handleControllerConfigured}
  />

  <ControllerBindingsModal
    visible={controllerBindingsModal}
    controllerName={controllerToEditBindings?.name ?? 'Controlador'}
    sensorVariables={controllerSensorVariables}
    actuatorVariables={controllerActuatorVariables}
    initialInputVariableIds={controllerToEditBindings?.inputVariableIds ?? []}
    initialOutputVariableIds={controllerToEditBindings?.outputVariableIds ?? []}
    onClose={() => {
      controllerBindingsModal = false;
      controllerToEditBindings = null;
    }}
    onSave={(bindings) => {
      if (!controllerToEditBindings) {
        return 'Controlador não encontrado';
      }

      const result = updateControllerBindings(controllerToEditBindings.id, bindings);
      if (!result) {
        controllerBindingsModal = false;
        controllerToEditBindings = null;
      }

      return result;
    }}
  />

  <GenericModal
    visible={controllerRestartModal.visible}
    type="warning"
    title="Restart necessário"
    message={`O controlador "${controllerRestartModal.controllerName}" foi salvo, mas precisa de um restart da planta para entrar em execução.\n\nDeseja religar a planta agora?`}
    confirmLabel="Religar agora"
    onConfirm={handleRestartPendingController}
    onClose={() => {
      controllerRestartModal.visible = false;
    }}
  />

  <GenericModal
    visible={feedbackModal.visible}
    type={feedbackModal.type}
    title={feedbackModal.title}
    message={feedbackModal.message}
    confirmLabel={feedbackModal.confirmLabel}
    onConfirm={hideFeedbackModal}
  />

  <CreatePlantModal
    bind:visible={createPlantModal}
    onPlantSaved={handlePlantSaved}
    onClose={() => createPlantModal = false}
  />

  <CreatePlantModal
    visible={editPlantModal}
    initialPlant={activePlant ?? null}
    onPlantSaved={handlePlantSaved}
    onClose={() => editPlantModal = false}
  />
</div>

<style>
  @media (max-height: 900px) {
    .plotter-graph-area {
      padding: 0.625rem;
      gap: 0.625rem;
    }
  }

  @media (max-height: 760px) {
    .plotter-graph-area {
      padding: 0.5rem;
      gap: 0.5rem;
    }
  }

  @media (max-height: 620px) {
    .plotter-workspace-shell {
      min-height: 0;
    }

    .plotter-graph-area {
      padding: 0.375rem;
      gap: 0.375rem;
    }
  }
</style>
