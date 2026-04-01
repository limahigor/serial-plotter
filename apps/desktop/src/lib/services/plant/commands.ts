import { invoke } from '@tauri-apps/api/core';
import type { Plant } from '$lib/types/plant';
import { extractServiceErrorMessage } from '$lib/services/shared/errorMessage';
import {
  buildCreatePlantDto,
  mapControllerToDto,
  mapDtoToPlant,
  mapVariableToDto,
} from './mappers';
import { normalizeSampleTimeMs } from './shared';
import type {
  CreatePlantRequest,
  CreatePlantResponse,
  PlantActionResponse,
  PlantDto,
  RemoveControllerInstanceRequest,
  SaveControllerInstanceConfigRequest,
  SaveControllerInstanceConfigResponse,
  SavePlantSetpointRequest,
  UpdatePlantDto,
  UpdatePlantRequest,
} from './types';

async function getBackendPlant(id: string): Promise<Plant | null> {
  try {
    const response = await invoke<PlantDto>('get_plant', { id });
    return mapDtoToPlant(response);
  } catch {
    return null;
  }
}

function mergeBackendRuntimeState(currentPlant: Plant, backendPlant: Plant): Plant {
  const backendControllersById = new Map(
    (backendPlant.controllers ?? []).map((controller) => [controller.id, controller]),
  );

  return {
    ...backendPlant,
    driver: currentPlant.driver ?? backendPlant.driver,
    controllers: (currentPlant.controllers ?? backendPlant.controllers).map((controller) => ({
      ...controller,
      runtimeStatus:
        backendControllersById.get(controller.id)?.runtimeStatus ??
        controller.runtimeStatus ??
        'synced',
    })),
    source: 'backend',
  };
}

async function invokePlantAction(
  command: string,
  id: string,
  merge: (current: Plant, backend: Plant) => Plant,
): Promise<PlantActionResponse> {
  const current = await getBackendPlant(id);
  if (!current) {
    return { success: false, error: 'Planta não encontrada' };
  }

  try {
    const response = await invoke<PlantDto>(command, { id });
    return { success: true, plant: merge(current, mapDtoToPlant(response)) };
  } catch (error) {
    const message = extractServiceErrorMessage(error, 'Erro ao sincronizar ação da planta');
    return { success: false, error: message };
  }
}

export async function createPlant(request: CreatePlantRequest): Promise<CreatePlantResponse> {
  if (!request.name.trim()) {
    return { success: false, error: 'Nome da planta é obrigatório' };
  }

  const driver = request.driver;
  if (!driver?.pluginId) {
    return { success: false, error: 'Configure um driver de comunicação para a planta' };
  }

  if (request.variables.length === 0) {
    return { success: false, error: 'Pelo menos uma variável deve ser definida' };
  }

  try {
    const response = await invoke<PlantDto>('create_plant', {
      request: buildCreatePlantDto({
        ...request,
        driver,
      }),
    });
    return { success: true, plant: mapDtoToPlant(response) };
  } catch (error) {
    const message = extractServiceErrorMessage(error, 'Erro ao criar planta no backend');
    return { success: false, error: message };
  }
}

export async function updatePlant(request: UpdatePlantRequest): Promise<PlantActionResponse> {
  const current = await getBackendPlant(request.id);
  if (!current) {
    return { success: false, error: 'Planta não encontrada' };
  }

  try {
    const response = await invoke<PlantDto>('update_plant', {
      request: {
        id: request.id,
        name: request.name.trim(),
        sample_time_ms: normalizeSampleTimeMs(request.sampleTimeMs, current.sampleTimeMs),
        variables: request.variables.map(mapVariableToDto),
        driver: {
          plugin_id: request.driver?.pluginId ?? current.driver?.pluginId ?? current.driverId ?? '',
          config: request.driver?.config ?? current.driver?.config ?? {},
        },
        controllers: request.controllers.map(mapControllerToDto),
      } satisfies UpdatePlantDto,
    });

    return { success: true, plant: mapDtoToPlant(response) };
  } catch (error) {
    const message = extractServiceErrorMessage(error, 'Erro ao atualizar planta no backend');
    return { success: false, error: message };
  }
}

export async function saveController(
  request: SaveControllerInstanceConfigRequest,
): Promise<SaveControllerInstanceConfigResponse> {
  if (!request.controller.id) {
    return { success: false, error: 'Controlador não encontrado' };
  }

  if (request.source !== 'backend') {
    return { success: true };
  }

  try {
    const response = await invoke<PlantDto>('save_controller', {
      request: {
        plant_id: request.plantId,
        controller_id: request.controller.id,
        plugin_id: request.controller.pluginId ?? null,
        name: request.controller.name,
        controller_type: request.controller.type,
        active: request.controller.active,
        input_variable_ids: request.controller.inputVariableIds ?? [],
        output_variable_ids: request.controller.outputVariableIds ?? [],
        params: Object.entries(request.controller.params ?? {}).map(([key, param]) => ({
          key,
          type: param.type,
          value: param.value,
          label: param.label,
        })),
      },
    });

    return { success: true, plant: mapDtoToPlant(response) };
  } catch (error) {
    const message = extractServiceErrorMessage(
      error,
      'Erro ao salvar configuração do controlador',
    );
    return { success: false, error: message };
  }
}

export async function removeController(
  request: RemoveControllerInstanceRequest,
): Promise<PlantActionResponse> {
  try {
    const response = await invoke<PlantDto>('remove_controller', {
      request: {
        plant_id: request.plantId,
        controller_id: request.controllerId,
      },
    });

    return { success: true, plant: mapDtoToPlant(response) };
  } catch (error) {
    const message = extractServiceErrorMessage(error, 'Erro ao remover controlador da planta');
    return { success: false, error: message };
  }
}

export async function saveSetpoint(
  request: SavePlantSetpointRequest,
): Promise<PlantActionResponse> {
  try {
    const response = await invoke<PlantDto>('save_setpoint', {
      request: {
        plant_id: request.plantId,
        variable_id: request.variableId,
        setpoint: request.setpoint,
      },
    });

    return { success: true, plant: mapDtoToPlant(response) };
  } catch (error) {
    const message = extractServiceErrorMessage(error, 'Erro ao salvar setpoint da planta');
    return { success: false, error: message };
  }
}

export async function removePlant(id: string): Promise<PlantActionResponse> {
  try {
    const response = await invoke<PlantDto>('remove_plant', { id });
    return { success: true, plant: mapDtoToPlant(response) };
  } catch (error) {
    const message = extractServiceErrorMessage(error, 'Erro ao remover planta no backend');
    return { success: false, error: message };
  }
}

export async function closePlant(id: string): Promise<PlantActionResponse> {
  try {
    const response = await invoke<PlantDto>('close_plant', { id });
    return { success: true, plant: mapDtoToPlant(response) };
  } catch (error) {
    const message = extractServiceErrorMessage(error, 'Erro ao fechar planta no backend');
    return { success: false, error: message };
  }
}

export async function connectPlant(id: string): Promise<PlantActionResponse> {
  const current = await getBackendPlant(id);
  if (current && !current.connected && !current.driver?.pluginId) {
    return {
      success: false,
      error: current.driverId
        ? 'O driver desta planta não está carregado. Vincule um novo driver antes de ligar.'
        : 'Configure um driver de comunicação para a planta antes de ligar.',
    };
  }

  return invokePlantAction('connect_plant', id, mergeBackendRuntimeState);
}

export function disconnectPlant(id: string): Promise<PlantActionResponse> {
  return invokePlantAction('disconnect_plant', id, mergeBackendRuntimeState);
}

export function pausePlant(id: string): Promise<PlantActionResponse> {
  return invokePlantAction('pause_plant', id, mergeBackendRuntimeState);
}

export function resumePlant(id: string): Promise<PlantActionResponse> {
  return invokePlantAction('resume_plant', id, mergeBackendRuntimeState);
}
