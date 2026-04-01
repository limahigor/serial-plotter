import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { ingestPlantTelemetry } from '$lib/stores/plantData';
import type { Plant, PlantDataPoint, PlantVariable } from '$lib/types/plant';
import type {
  PlantRuntimeErrorEvent,
  PlantRuntimeStatusEvent,
  PlantRuntimeTelemetryEvent,
  PlantTelemetryPacket,
} from './types';
import { toFiniteNumber } from './shared';
import { resolveActuatorTelemetryValue } from './tabState.js';

const telemetrySeriesKeyCache = new Map<
  string,
  {
    signature: string;
    descriptors: Array<{
      id: string;
      type: PlantVariable['type'];
      pvKey: string;
      spKey: string | null;
      fallbackSetpoint: number;
    }>;
  }
>();

function getTelemetrySeriesKeyDescriptors(plant: Plant) {
  const signature = plant.variables
    .map((variable) => `${variable.id}:${variable.type}:${variable.setpoint}`)
    .join('|');
  const cached = telemetrySeriesKeyCache.get(plant.id);
  if (cached && cached.signature === signature) {
    return cached.descriptors;
  }

  const descriptors = plant.variables.map((variable, index) => ({
    id: variable.id,
    type: variable.type,
    pvKey: `var_${index}_pv`,
    spKey: variable.type === 'sensor' ? `var_${index}_sp` : null,
    fallbackSetpoint: variable.setpoint,
  }));
  telemetrySeriesKeyCache.set(plant.id, { signature, descriptors });
  return descriptors;
}

export async function subscribePlantRuntimeEvents(handlers: {
  onTelemetry?: (event: PlantRuntimeTelemetryEvent) => void;
  onStatus?: (event: PlantRuntimeStatusEvent) => void;
  onError?: (event: PlantRuntimeErrorEvent) => void;
}): Promise<() => void> {
  const unlisteners: UnlistenFn[] = [];

  if (handlers.onTelemetry) {
    unlisteners.push(
      await listen<PlantRuntimeTelemetryEvent>('plant://telemetry', (event) => {
        handlers.onTelemetry?.(event.payload);
      }),
    );
  }

  if (handlers.onStatus) {
    unlisteners.push(
      await listen<PlantRuntimeStatusEvent>('plant://status', (event) => {
        handlers.onStatus?.(event.payload);
      }),
    );
  }

  if (handlers.onError) {
    unlisteners.push(
      await listen<PlantRuntimeErrorEvent>('plant://error', (event) => {
        handlers.onError?.(event.payload);
      }),
    );
  }

  return () => {
    for (const unlisten of unlisteners) {
      unlisten();
    }
  };
}

export function buildTelemetryPacketFromRuntimeEvent(
  plant: Plant,
  event: PlantRuntimeTelemetryEvent,
): PlantTelemetryPacket {
  const descriptors = getTelemetrySeriesKeyDescriptors(plant);
  const point: PlantDataPoint = {
    time: Math.max(0, toFiniteNumber(event.uptime_s, 0)),
  };

  for (const descriptor of descriptors) {
    if (descriptor.type === 'sensor') {
      point[descriptor.pvKey] = toFiniteNumber(event.sensors?.[descriptor.id], 0);
      point[descriptor.spKey!] = toFiniteNumber(
        event.setpoints?.[descriptor.id],
        descriptor.fallbackSetpoint,
      );
      continue;
    }

    point[descriptor.pvKey] = resolveActuatorTelemetryValue(
      event.written_outputs,
      event.actuators_read,
      descriptor.id,
    );
  }

  return {
    plantId: plant.id,
    points: [point],
    stats: {
      dt: Math.max(0, toFiniteNumber(event.effective_dt_ms, plant.sampleTimeMs) / 1000),
      uptime: point.time,
    },
  };
}

export function applyPlantTelemetryPacket(packet: PlantTelemetryPacket): PlantDataPoint[] {
  return ingestPlantTelemetry(packet);
}
