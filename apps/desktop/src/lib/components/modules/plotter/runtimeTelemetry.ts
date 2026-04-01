import {
  applyPlantTelemetryPacket,
  buildTelemetryPacketFromRuntimeEvent,
  type PlantRuntimeStatusEvent,
  type PlantRuntimeTelemetryEvent,
} from '$lib/services/plant';
import {
  clearPlant,
  clearVariableStats,
  getPlantStats,
  getRecommendedPlantBufferConfig,
  setPlantBufferConfig,
  setPlantSeriesCatalog,
  setPlantStats,
} from '$lib/stores/plantData';
import { buildPlantSeriesCatalog, type Plant } from '$lib/types/plant';

type TelemetryPacket = ReturnType<typeof buildTelemetryPacketFromRuntimeEvent>;

type BacklogEntry = {
  runtimeId: string;
  packets: TelemetryPacket[];
};

type LiveTelemetryEntry = {
  packets: TelemetryPacket[];
};

type RuntimeTelemetryManagerDependencies = {
  findPlantById: (plantId: string) => Plant | undefined;
  updatePlantRuntimeState: (
    plantId: string,
    runtimeState: Partial<Pick<Plant, 'connected' | 'paused'>>,
  ) => void;
};

export function createRuntimeTelemetryManager(
  deps: RuntimeTelemetryManagerDependencies,
) {
  const runtimeSessionByPlant = new Map<string, string>();
  const telemetryBacklogByPlant = new Map<string, BacklogEntry>();
  const liveTelemetryByPlant = new Map<string, LiveTelemetryEntry>();
  const preparedSessionResetPlants = new Set<string>();
  let telemetryFlushFrame = 0;

  function resetPlantTelemetryState(plant: Plant) {
    clearPlant(plant.id);
    setPlantBufferConfig(plant.id, getRecommendedPlantBufferConfig(plant.sampleTimeMs));
    setPlantSeriesCatalog(buildPlantSeriesCatalog(plant.id, plant.variables));
    setPlantStats(plant.id, {
      dt: plant.sampleTimeMs / 1000,
      uptime: 0,
    });
    clearVariableStats(plant.id);
  }

  function clearTelemetryBacklog(plantId: string) {
    telemetryBacklogByPlant.delete(plantId);
  }

  function forgetRuntimeSession(plantId: string) {
    clearTelemetryBacklog(plantId);
    liveTelemetryByPlant.delete(plantId);
    runtimeSessionByPlant.delete(plantId);
    preparedSessionResetPlants.delete(plantId);
  }

  function preparePlantSessionStart(plant: Plant) {
    forgetRuntimeSession(plant.id);
    resetPlantTelemetryState(plant);
    preparedSessionResetPlants.add(plant.id);
  }

  function rememberRuntimeSession(
    plantId: string,
    runtimeId: string,
  ): { changed: boolean; requiresReset: boolean } {
    if (runtimeSessionByPlant.get(plantId) === runtimeId) {
      return {
        changed: false,
        requiresReset: false,
      };
    }

    clearTelemetryBacklog(plantId);
    liveTelemetryByPlant.delete(plantId);
    runtimeSessionByPlant.set(plantId, runtimeId);
    const hasPreparedReset = preparedSessionResetPlants.delete(plantId);

    return {
      changed: true,
      requiresReset: !hasPreparedReset,
    };
  }

  function queueTelemetryPacket(
    plantId: string,
    runtimeId: string,
    packet: TelemetryPacket,
  ) {
    const backlog = telemetryBacklogByPlant.get(plantId);
    if (!backlog || backlog.runtimeId !== runtimeId) {
      telemetryBacklogByPlant.set(plantId, {
        runtimeId,
        packets: [packet],
      });
      return;
    }

    backlog.packets.push(packet);
  }

  function flushTelemetryBacklog(plantId: string, basePlant?: Plant) {
    const backlog = telemetryBacklogByPlant.get(plantId);
    if (!backlog || backlog.packets.length === 0) {
      clearTelemetryBacklog(plantId);
      return;
    }

    clearTelemetryBacklog(plantId);
    const plant = basePlant ?? deps.findPlantById(plantId);
    if (!plant) {
      return;
    }

    for (const packet of backlog.packets) {
      applyPlantTelemetryPacket(packet);
    }
  }

  function flushLiveTelemetry() {
    telemetryFlushFrame = 0;

    for (const [plantId, queued] of liveTelemetryByPlant.entries()) {
      for (const packet of queued.packets) {
        applyPlantTelemetryPacket(packet);
      }

      liveTelemetryByPlant.delete(plantId);
    }
  }

  function scheduleLiveTelemetryFlush() {
    if (telemetryFlushFrame !== 0) return;
    telemetryFlushFrame = requestAnimationFrame(() => {
      flushLiveTelemetry();
    });
  }

  function enqueueLiveTelemetryPacket(plant: Plant, packet: TelemetryPacket) {
    const queued = liveTelemetryByPlant.get(plant.id);
    if (!queued) {
      liveTelemetryByPlant.set(plant.id, {
        packets: [packet],
      });
    } else {
      queued.packets.push(packet);
    }

    scheduleLiveTelemetryFlush();
  }

  function handleRuntimeTelemetry(event: PlantRuntimeTelemetryEvent) {
    const plant = deps.findPlantById(event.plant_id);
    if (!plant) return;

    const runtimeSession = rememberRuntimeSession(event.plant_id, event.runtime_id);
    if (runtimeSession.requiresReset) {
      resetPlantTelemetryState(plant);
    }

    const packet = buildTelemetryPacketFromRuntimeEvent(plant, event);
    if (plant.paused) {
      queueTelemetryPacket(plant.id, event.runtime_id, packet);
      return;
    }

    enqueueLiveTelemetryPacket(plant, packet);
  }

  function handleRuntimeStatus(event: PlantRuntimeStatusEvent) {
    const plant = deps.findPlantById(event.plant_id);
    if (!plant) return;

    const isOffline =
      event.lifecycle_state === 'stopped' || event.lifecycle_state === 'faulted';
    const knownRuntimeId = runtimeSessionByPlant.get(event.plant_id);

    if (knownRuntimeId && knownRuntimeId !== event.runtime_id) {
      return;
    }

    if (!knownRuntimeId) {
      if (isOffline || !plant.connected) {
        return;
      }

      rememberRuntimeSession(event.plant_id, event.runtime_id);
    }

    if (isOffline) {
      forgetRuntimeSession(event.plant_id);
    }

    const currentStats = getPlantStats(event.plant_id);
    setPlantStats(event.plant_id, {
      ...currentStats,
      dt:
        plant.paused && !isOffline
          ? currentStats.dt
          : Math.max(0, event.effective_dt_ms / 1000),
    });

    const nextConnected = !isOffline && (plant.connected || event.lifecycle_state === 'running');
    const nextPaused = isOffline ? false : plant.paused;
    if (plant.connected !== nextConnected || plant.paused !== nextPaused) {
      deps.updatePlantRuntimeState(event.plant_id, {
        connected: nextConnected,
        paused: nextPaused,
      });
    }
  }

  function dispose() {
    if (telemetryFlushFrame !== 0) {
      cancelAnimationFrame(telemetryFlushFrame);
      telemetryFlushFrame = 0;
    }
  }

  return {
    dispose,
    flushTelemetryBacklog,
    forgetRuntimeSession,
    handleRuntimeStatus,
    handleRuntimeTelemetry,
    preparePlantSessionStart,
    resetPlantTelemetryState,
  };
}
