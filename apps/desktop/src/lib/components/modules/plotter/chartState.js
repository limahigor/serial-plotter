// @ts-check

/**
 * @typedef {{
 *   xMode: 'auto' | 'sliding' | 'manual',
 *   xMin: number | null,
 *   xMax: number | null,
 *   sensorYMode: 'auto' | 'manual',
 *   sensorYMin: number,
 *   sensorYMax: number,
 *   actuatorYMode: 'auto' | 'manual',
 *   actuatorYMin: number,
 *   actuatorYMax: number,
 *   windowSize: number,
 * }} ChartScaleState
 */

/**
 * @typedef {{
 *   viewMode: 'grid' | 'single',
 *   focusedVariableIndex: number,
 *   variableCount: number,
 * }} ChartViewState
 */

/**
 * @typedef {{
 *   index: number,
 * }} SensorEntry
 */

/**
 * @typedef {{
 *   pvConfig: {
 *     yMin: number,
 *     yMax: number,
 *     yMode: 'auto' | 'manual',
 *     xMode: 'auto' | 'sliding' | 'manual',
 *     windowSize: number,
 *     xMin: number | null,
 *     xMax: number | null,
 *     showGrid: boolean,
 *     showHover: boolean,
 *   },
 *   mvConfig: {
 *     yMin: number,
 *     yMax: number,
 *     yMode: 'auto' | 'manual',
 *     xMode: 'auto' | 'sliding' | 'manual',
 *     windowSize: number,
 *     xMin: number | null,
 *     xMax: number | null,
 *     showGrid: boolean,
 *     showHover: boolean,
 *   },
 * }} VariableChartConfigPair
 */

function createDefaultChartScaleState() {
  return /** @type {ChartScaleState} */ ({
    xMode: 'auto',
    xMin: null,
    xMax: null,
    sensorYMode: 'auto',
    sensorYMin: 0,
    sensorYMax: 100,
    actuatorYMode: 'manual',
    actuatorYMin: 0,
    actuatorYMax: 100,
    windowSize: 30,
  });
}

/**
 * @param {Partial<ChartScaleState> | undefined} state
 * @returns {ChartScaleState}
 */
function normalizeChartScaleState(state) {
  if (
    state &&
    'sensorYMode' in state &&
    'sensorYMin' in state &&
    'sensorYMax' in state &&
    'actuatorYMode' in state &&
    'actuatorYMin' in state &&
    'actuatorYMax' in state
  ) {
    return /** @type {ChartScaleState} */ (state);
  }

  return {
    ...createDefaultChartScaleState(),
    ...state,
  };
}

/**
 * @param {number} [variableCount]
 * @returns {ChartViewState}
 */
function createDefaultChartViewState(variableCount = 1) {
  return {
    viewMode: 'grid',
    focusedVariableIndex: 0,
    variableCount,
  };
}

/**
 * @param {{ variables: Array<{ type: string }> }} plant
 * @returns {number[]}
 */
export function getSensorIndices(plant) {
  const sensorIndices = [];

  for (const [index, variable] of plant.variables.entries()) {
    if (variable.type === 'sensor') {
      sensorIndices.push(index);
    }
  }

  return sensorIndices;
}

/**
 * @param {ChartViewState | undefined} currentState
 * @param {number} sensorCount
 * @returns {ChartViewState | null}
 */
export function buildSyncedChartViewState(currentState, sensorCount) {
  if (!currentState) {
    return createDefaultChartViewState(sensorCount);
  }

  const focusedVariableIndex = Math.max(
    0,
    Math.min(currentState.focusedVariableIndex, Math.max(sensorCount - 1, 0)),
  );

  if (
    currentState.variableCount === sensorCount &&
    currentState.focusedVariableIndex === focusedVariableIndex
  ) {
    return null;
  }

  return {
    ...currentState,
    variableCount: sensorCount,
    focusedVariableIndex,
  };
}

/**
 * @param {Record<number, ChartScaleState> | undefined} currentStates
 * @param {number[]} sensorIndices
 * @returns {Record<number, ChartScaleState> | null}
 */
export function buildSyncedChartScaleStates(currentStates, sensorIndices) {
  const sensorIndexSet = new Set(sensorIndices);
  const existingStates = currentStates ?? {};
  /** @type {Record<number, ChartScaleState>} */
  const nextStates = {};
  let changed = !currentStates;

  for (const sensorIndex of sensorIndices) {
    const currentState = existingStates[sensorIndex];
    if (currentState) {
      const normalizedState = normalizeChartScaleState(currentState);
      nextStates[sensorIndex] = normalizedState;
      if (normalizedState !== currentState) {
        changed = true;
      }
    } else {
      nextStates[sensorIndex] = createDefaultChartScaleState();
      changed = true;
    }
  }

  if (!changed) {
    for (const key of Object.keys(existingStates)) {
      if (!sensorIndexSet.has(Number(key))) {
        changed = true;
        break;
      }
    }
  }

  return changed ? nextStates : null;
}

/**
 * @template T
 * @param {Record<string, T>} currentStates
 * @param {Set<string>} activePlantIds
 * @returns {Record<string, T> | null}
 */
export function pruneOrphanPlantStates(currentStates, activePlantIds) {
  for (const plantId of Object.keys(currentStates)) {
    if (!activePlantIds.has(plantId)) {
      const nextStates = { ...currentStates };

      for (const orphanPlantId of Object.keys(nextStates)) {
        if (!activePlantIds.has(orphanPlantId)) {
          delete nextStates[orphanPlantId];
        }
      }

      return nextStates;
    }
  }

  return null;
}

/**
 * @param {Array<{ id: string, variables: Array<{ type: string }> }>} plants
 * @param {Record<string, ChartViewState>} chartViewStatesByPlant
 * @param {Record<string, Record<number, ChartScaleState>>} chartScaleStatesByPlant
 */
export function syncChartStateMaps(
  plants,
  chartViewStatesByPlant,
  chartScaleStatesByPlant,
) {
  const activePlantIds = new Set(plants.map((plant) => plant.id));
  let nextChartViewStates = chartViewStatesByPlant;
  let nextChartScaleStates = chartScaleStatesByPlant;

  for (const plant of plants) {
    const sensorIndices = getSensorIndices(plant);
    const nextViewState = buildSyncedChartViewState(
      nextChartViewStates[plant.id],
      sensorIndices.length,
    );

    if (nextViewState) {
      if (nextChartViewStates === chartViewStatesByPlant) {
        nextChartViewStates = { ...chartViewStatesByPlant };
      }
      nextChartViewStates[plant.id] = nextViewState;
    }

    const nextScaleStates = buildSyncedChartScaleStates(
      nextChartScaleStates[plant.id],
      sensorIndices,
    );

    if (nextScaleStates) {
      if (nextChartScaleStates === chartScaleStatesByPlant) {
        nextChartScaleStates = { ...chartScaleStatesByPlant };
      }
      nextChartScaleStates[plant.id] = nextScaleStates;
    }
  }

  const prunedChartViewStates = pruneOrphanPlantStates(nextChartViewStates, activePlantIds);
  if (prunedChartViewStates) {
    nextChartViewStates = prunedChartViewStates;
  }

  const prunedChartScaleStates = pruneOrphanPlantStates(nextChartScaleStates, activePlantIds);
  if (prunedChartScaleStates) {
    nextChartScaleStates = prunedChartScaleStates;
  }

  return {
    chartViewStatesByPlant: nextChartViewStates,
    chartScaleStatesByPlant: nextChartScaleStates,
  };
}

/**
 * @param {Record<string, Record<number, ChartScaleState>>} chartScaleStatesByPlant
 * @param {string} plantId
 */
export function resetScaleStatesForPlant(chartScaleStatesByPlant, plantId) {
  const currentStates = chartScaleStatesByPlant[plantId] ?? {};
  /** @type {Record<number, ChartScaleState>} */
  const nextPlantStates = Object.fromEntries(
    Object.keys(currentStates).map((key) => [Number(key), createDefaultChartScaleState()]),
  );

  return {
    ...chartScaleStatesByPlant,
    [plantId]: nextPlantStates,
  };
}

/**
 * @param {Record<string, Record<number, ChartScaleState>>} chartScaleStatesByPlant
 * @param {string} plantId
 * @param {number} variableIndex
 * @param {(current: ChartScaleState) => ChartScaleState} updater
 */
export function updateScaleStateMap(
  chartScaleStatesByPlant,
  plantId,
  variableIndex,
  updater,
) {
  const currentStates = chartScaleStatesByPlant[plantId] ?? {};
  const currentState = normalizeChartScaleState(currentStates[variableIndex]);

  return {
    ...chartScaleStatesByPlant,
    [plantId]: {
      ...currentStates,
      [variableIndex]: updater(currentState),
    },
  };
}

/**
 * @param {Record<string, Record<number, ChartScaleState>>} chartScaleStatesByPlant
 * @param {string} plantId
 */
export function resetPlantZoomState(chartScaleStatesByPlant, plantId) {
  const currentStates = chartScaleStatesByPlant[plantId] ?? {};
  /** @type {Record<number, ChartScaleState>} */
  const nextPlantStates = Object.fromEntries(
    Object.entries(currentStates).map(([key, state]) => {
      const normalizedState = normalizeChartScaleState(state);
      return [
        Number(key),
        /** @type {ChartScaleState} */ ({
          ...createDefaultChartScaleState(),
          ...normalizedState,
          windowSize: normalizedState.windowSize,
        }),
      ];
    }),
  );

  return {
    ...chartScaleStatesByPlant,
    [plantId]: nextPlantStates,
  };
}

/**
 * @param {SensorEntry[]} sensorEntries
 * @param {Record<number, ChartScaleState>} activeChartScaleStates
 * @returns {Record<number, VariableChartConfigPair>}
 */
export function buildChartConfigsByVariableIndex(sensorEntries, activeChartScaleStates) {
  /** @type {Record<number, VariableChartConfigPair>} */
  const configs = {};

  for (const sensorEntry of sensorEntries) {
    const scaleState = normalizeChartScaleState(activeChartScaleStates[sensorEntry.index]);

    configs[sensorEntry.index] = {
      pvConfig: {
        yMin: scaleState.sensorYMin,
        yMax: scaleState.sensorYMax,
        yMode: scaleState.sensorYMode,
        xMode: scaleState.xMode,
        windowSize: scaleState.windowSize,
        xMin: scaleState.xMin,
        xMax: scaleState.xMax,
        showGrid: true,
        showHover: true,
      },
      mvConfig: {
        yMin: scaleState.actuatorYMin,
        yMax: scaleState.actuatorYMax,
        yMode: scaleState.actuatorYMode,
        xMode: scaleState.xMode,
        windowSize: scaleState.windowSize,
        xMin: scaleState.xMin,
        xMax: scaleState.xMax,
        showGrid: true,
        showHover: true,
      },
    };
  }

  return configs;
}

/**
 * @param {DragEvent} event
 * @returns {boolean}
 */
export function hasDraggedFiles(event) {
  const transfer = event.dataTransfer;
  if (!transfer) return false;

  if ((transfer.files?.length ?? 0) > 0) {
    return true;
  }

  for (let index = 0; index < transfer.types.length; index += 1) {
    if (transfer.types[index] === 'Files') {
      return true;
    }
  }

  for (let index = 0; index < transfer.items.length; index += 1) {
    if (transfer.items[index]?.kind === 'file') {
      return true;
    }
  }

  return false;
}

/**
 * @param {HTMLElement | undefined} container
 * @param {MouseEvent} event
 * @param {number} [menuWidth]
 * @param {number} [menuHeight]
 */
export function resolveContextMenuPosition(
  container,
  event,
  menuWidth = 250,
  menuHeight = 460,
) {
  if (!container) {
    return null;
  }

  const bounds = container.getBoundingClientRect();
  let x = event.clientX - bounds.left;
  let y = event.clientY - bounds.top;

  if (x + menuWidth > bounds.width) x -= menuWidth;
  if (y + menuHeight > bounds.height) y -= menuHeight;

  return { x, y };
}
