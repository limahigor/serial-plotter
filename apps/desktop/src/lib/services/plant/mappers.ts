import type {
  Plant,
  PlantSeriesCatalog,
  PlantVariable,
  VariableStats,
} from '$lib/types/plant';
import type { Controller, ControllerParam } from '$lib/types/controller';
import type { PluginInstance } from '$lib/types/plugin';
import type {
  ControllerParamDto,
  CreatePlantDto,
  PlantControllerDto,
  PlantDriverDto,
  PlantDto,
} from './types';
import { isRecord, normalizeSampleTimeMs, toFiniteNumber } from './shared';

export function mapVariableDtoToFrontend(
  variable: PlantDto['variables'][number],
  index: number,
): PlantVariable {
  return {
    id: `var_${index}`,
    name: variable.name,
    type: variable.type,
    unit: variable.unit,
    setpoint: variable.setpoint,
    pvMin: variable.pv_min,
    pvMax: variable.pv_max,
    linkedSensorIds: variable.linked_sensor_ids ?? [],
  };
}

export function mapDriverDtoToFrontend(driver: PlantDriverDto): PluginInstance {
  return {
    pluginId: driver.plugin_id,
    pluginName: driver.plugin_name,
    pluginKind: 'driver',
    config: driver.config ?? {},
  };
}

export function mapControllerParamDtoToFrontend(param: ControllerParamDto): ControllerParam {
  return {
    type: param.type,
    value: param.value as ControllerParam['value'],
    label: param.label,
  };
}

export function mapControllerDtoToFrontend(controller: PlantControllerDto): Controller {
  return {
    id: controller.id,
    pluginId: controller.plugin_id,
    pluginName: controller.plugin_name,
    name: controller.name,
    type: controller.controller_type,
    active: controller.active,
    inputVariableIds: controller.input_variable_ids ?? [],
    outputVariableIds: controller.output_variable_ids ?? [],
    params: Object.fromEntries(
      Object.entries(controller.params ?? {}).map(([key, param]) => [key, mapControllerParamDtoToFrontend(param)]),
    ),
    runtimeStatus: controller.runtime_status ?? 'synced',
  };
}

export function mapDtoToPlant(dto: PlantDto): Plant {
  const sampleTimeMs = normalizeSampleTimeMs(
    dto.sample_time_ms,
    dto.stats.dt > 0 ? dto.stats.dt * 1000 : undefined,
  );

  return {
    id: dto.id,
    name: dto.name,
    sampleTimeMs,
    connected: dto.connected,
    paused: dto.paused,
    variables: dto.variables.map(mapVariableDtoToFrontend),
    stats: {
      dt: dto.stats.dt > 0 ? dto.stats.dt : sampleTimeMs / 1000,
      uptime: dto.stats.uptime,
    },
    controllers: (dto.controllers ?? []).map(mapControllerDtoToFrontend),
    driverId: dto.driver.plugin_id,
    driver: mapDriverDtoToFrontend(dto.driver),
    source: 'backend',
  };
}

export function mapVariableToDto(variable: PlantVariable): CreatePlantDto['variables'][number] {
  return {
    name: variable.name,
    type: variable.type,
    unit: variable.unit,
    setpoint: variable.setpoint,
    pv_min: variable.pvMin,
    pv_max: variable.pvMax,
    linked_sensor_ids: variable.linkedSensorIds,
  };
}

export function mapControllerParamToDto(param: ControllerParam): ControllerParamDto {
  return {
    type: param.type,
    value: param.value,
    label: param.label,
  };
}

export function mapControllerToDto(controller: Controller): CreatePlantDto['controllers'][number] {
  return {
    id: controller.id,
    plugin_id: controller.pluginId ?? controller.id,
    name: controller.name,
    controller_type: controller.type,
    active: controller.active,
    input_variable_ids: controller.inputVariableIds ?? [],
    output_variable_ids: controller.outputVariableIds ?? [],
    params: Object.fromEntries(
      Object.entries(controller.params ?? {}).map(([key, param]) => [key, mapControllerParamToDto(param)]),
    ),
  };
}

export function buildCreatePlantDto(request: {
  name: string;
  sampleTimeMs: number;
  driver: PluginInstance;
  variables: PlantVariable[];
  controllers: Controller[];
}): CreatePlantDto {
  const sampleTimeMs = normalizeSampleTimeMs(request.sampleTimeMs);

  return {
    name: request.name.trim(),
    sample_time_ms: sampleTimeMs,
    variables: request.variables.map(mapVariableToDto),
    driver: {
      plugin_id: request.driver.pluginId,
      config: request.driver.config ?? {},
    },
    controllers: request.controllers.map(mapControllerToDto),
  };
}

export function normalizeImportedVariableStats(payload: unknown): VariableStats {
  const source = isRecord(payload) ? payload : {};
  const errorAvg = toFiniteNumber(source.errorAvg ?? source.error_avg, 0);
  const stability = toFiniteNumber(source.stability, 100);
  const ripple = toFiniteNumber(source.ripple, 0);

  return {
    errorAvg,
    stability,
    ripple,
  };
}

export function normalizeImportedSeriesCatalog(
  payload: unknown,
  fallbackPlantId: string,
): PlantSeriesCatalog {
  const source = isRecord(payload) ? payload : {};
  const rawSeries = Array.isArray(source.series) ? source.series : [];
  const series = rawSeries
    .map((entry) => {
      const item = isRecord(entry) ? entry : {};
      const key = typeof item.key === 'string' ? item.key.trim() : '';
      const label = typeof item.label === 'string' ? item.label.trim() : '';
      const role = item.role;

      if (!key || (role !== 'pv' && role !== 'sp' && role !== 'mv')) {
        return null;
      }

      return {
        key,
        label: label || key,
        role,
      };
    })
    .filter((entry): entry is PlantSeriesCatalog['series'][number] => entry !== null);

  const plantId = typeof source.plantId === 'string' && source.plantId.trim()
    ? source.plantId
    : typeof source.plant_id === 'string' && source.plant_id.trim()
      ? source.plant_id
      : fallbackPlantId;

  return {
    plantId,
    series,
  };
}
