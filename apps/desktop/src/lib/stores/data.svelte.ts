import type { Plant, PlantVariable } from '$lib/types/plant';
import { createDefaultVariable } from '$lib/types/plant';
import { normalizeControllerParamValue, type Controller, type ControllerParam } from '$lib/types/controller';
import type { TabKey } from '$lib/types/ui';
import type { AppState } from '$lib/types/app';
import {
  movePlantTab,
  openPlantTabs,
  removePlantTabs,
  resolveActivePlantId,
} from '$lib/services/plant/tabState.js';

type ControllerMetaShape = Pick<
  Controller,
  'name' | 'type' | 'active' | 'inputVariableIds' | 'outputVariableIds' | 'pluginId' | 'pluginName' | 'runtimeStatus'
>;

type ControllerMetaField = keyof ControllerMetaShape;

type ControllerMetaValue<K extends ControllerMetaField> = ControllerMetaShape[K];

class AppStore {
  state = $state<AppState>({
    theme: 'dark',
    activeModule: 'plotter',
    sidebarCollapsed: true,
    showGlobalSettings: false,
    showControllerPanel: false,
  });
  plotterPlants = $state<Plant[]>([]);
  activePlotterPlantId = $state<string | null>(null);

  private findPlant(plantId: string): Plant | undefined {
    return this.plotterPlants.find((plant) => plant.id === plantId);
  }

  private withPlant<T>(plantId: string, updater: (plant: Plant) => T): T | undefined {
    const plant = this.findPlant(plantId);
    if (!plant) {
      return undefined;
    }

    return updater(plant);
  }

  private findController(plant: Plant, controllerId: string): Controller | undefined {
    return plant.controllers.find((controller) => controller.id === controllerId);
  }

  private withController<T>(
    plantId: string,
    controllerId: string,
    updater: (plant: Plant, controller: Controller) => T
  ): T | undefined {
    return this.withPlant(plantId, (plant) => {
      const controller = this.findController(plant, controllerId);
      if (!controller) {
        return undefined;
      }

      return updater(plant, controller);
    });
  }

  private updateControllerMetaValue<
    K extends ControllerMetaField,
  >(controller: Controller, field: K, value: ControllerMetaValue<K>) {
    switch (field) {
      case 'name':
        controller.name = value as Controller['name'];
        break;
      case 'type':
        controller.type = value as Controller['type'];
        break;
      case 'active':
        controller.active = value as Controller['active'];
        break;
      case 'inputVariableIds':
        controller.inputVariableIds = value as Controller['inputVariableIds'];
        break;
      case 'outputVariableIds':
        controller.outputVariableIds = value as Controller['outputVariableIds'];
        break;
      case 'pluginId':
        controller.pluginId = value as Controller['pluginId'];
        break;
      case 'pluginName':
        controller.pluginName = value as Controller['pluginName'];
        break;
      case 'runtimeStatus':
        controller.runtimeStatus = value as Controller['runtimeStatus'];
        break;
    }
  }

  private commitPlantTabs(nextPlants: Plant[], preferredActivePlantId: string | null) {
    this.plotterPlants = nextPlants;
    this.activePlotterPlantId = resolveActivePlantId(
      nextPlants,
      this.activePlotterPlantId,
      preferredActivePlantId,
    );
  }

  setTheme(theme: 'dark' | 'light') {
    this.state.theme = theme;
  }

  toggleTheme() {
    this.state.theme = this.state.theme === 'dark' ? 'light' : 'dark';
  }

  setActiveModule(module: TabKey) {
    this.state.activeModule = module;
  }

  setActivePlantId(id: string) {
    this.activePlotterPlantId = id;
  }

  setSidebarCollapsed(collapsed: boolean) {
    this.state.sidebarCollapsed = collapsed;
  }

  toggleSidebar() {
    this.state.sidebarCollapsed = !this.state.sidebarCollapsed;
  }

  setShowGlobalSettings(show: boolean) {
    this.state.showGlobalSettings = show;
  }

  setShowControllerPanel(show: boolean) {
    this.state.showControllerPanel = show;
  }

  openPlant(plant: Plant) {
    const nextPlants = openPlantTabs(this.plotterPlants, plant);
    this.commitPlantTabs(nextPlants, plant.id);
  }

  upsertPlant(plant: Plant) {
    const nextPlants = openPlantTabs(this.plotterPlants, plant);
    this.commitPlantTabs(nextPlants, this.activePlotterPlantId ?? plant.id);
  }

  updatePlantRuntimeState(
    plantId: string,
    runtimeState: Partial<Pick<Plant, 'connected' | 'paused'>>
  ) {
    this.withPlant(plantId, (plant) => {
      if (typeof runtimeState.connected === 'boolean') {
        plant.connected = runtimeState.connected;
      }

      if (typeof runtimeState.paused === 'boolean') {
        plant.paused = runtimeState.paused;
      }
    });
  }

  removePlant(plantId: string) {
    const preferredActivePlantId = this.activePlotterPlantId === plantId
      ? null
      : this.activePlotterPlantId;
    const nextPlants = removePlantTabs(this.plotterPlants, plantId);
    this.plotterPlants = nextPlants;
    this.activePlotterPlantId = resolveActivePlantId(nextPlants, preferredActivePlantId, null);
  }

  reorderPlants(sourcePlantId: string, targetPlantId: string, position: 'before' | 'after') {
    const nextPlants = movePlantTab(this.plotterPlants, sourcePlantId, targetPlantId, position);
    this.commitPlantTabs(nextPlants, this.activePlotterPlantId);
  }

  addController(plantId: string, controller: Omit<Controller, 'id'>) {
    this.withPlant(plantId, (plant) => {
      plant.controllers.push({
        ...controller,
        id: crypto.randomUUID().substring(0, 9)
      });
    });
  }

  deleteController(plantId: string, controllerId: string) {
    this.withPlant(plantId, (plant) => {
      const index = plant.controllers.findIndex((controller) => controller.id === controllerId);
      if (index > -1) plant.controllers.splice(index, 1);
    });
  }

  updateControllerMeta<K extends ControllerMetaField>(
    plantId: string,
    controllerId: string,
    field: K,
    value: ControllerMetaValue<K>
  ) {
    this.withController(plantId, controllerId, (_plant, controller) => {
      this.updateControllerMetaValue(controller, field, value);
    });
  }

  updateControllerParam(plantId: string, controllerId: string, paramKey: string, value: any): boolean {
    return this.withController(plantId, controllerId, (_plant, controller) => {
      const param = (controller.params as Record<string, ControllerParam>)[paramKey];
      if (!param) return false;

      const normalizedValue = normalizeControllerParamValue(param, value);
      if (normalizedValue === null) {
        return false;
      }

      param.value = normalizedValue;
      return true;
    }) ?? false;
  }

  updateVariableSetpoint(plantId: string, variableIndex: number, setpoint: number) {
    this.withPlant(plantId, (plant) => {
      if (plant.variables[variableIndex]) {
        plant.variables[variableIndex].setpoint = setpoint;
      }
    });
  }

  addVariable(plantId: string, variable?: Partial<PlantVariable>) {
    this.withPlant(plantId, (plant) => {
      const index = plant.variables.length;
      plant.variables.push({
        ...createDefaultVariable(index),
        ...variable,
        id: `var_${index}`,
      });
    });
  }

  removeVariable(plantId: string, variableIndex: number) {
    this.withPlant(plantId, (plant) => {
      if (plant.variables.length > 1) {
        plant.variables.splice(variableIndex, 1);
      }
    });
  }
}

export const appStore = new AppStore();
