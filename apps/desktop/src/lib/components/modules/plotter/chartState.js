// @ts-check

/**
 * @typedef {{
 *   xMode: 'auto' | 'sliding' | 'manual',
 *   yMode: 'auto' | 'manual',
 *   xMin: number | null,
 *   xMax: number | null,
 *   yMin: number,
 *   yMax: number,
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
    yMode: 'auto',
    xMin: null,
    xMax: null,
    yMin: 0,
    yMax: 100,
    windowSize: 30,
  });
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
      nextStates[sensorIndex] = currentState;
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
  const currentState = currentStates[variableIndex] ?? createDefaultChartScaleState();

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
    Object.entries(currentStates).map(([key, state]) => [
      Number(key),
      /** @type {ChartScaleState} */ ({
        ...state,
        xMode: 'auto',
        xMin: null,
        xMax: null,
      }),
    ]),
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
    const scaleState = activeChartScaleStates[sensorEntry.index] ?? createDefaultChartScaleState();

    configs[sensorEntry.index] = {
      pvConfig: {
        yMin: scaleState.yMin,
        yMax: scaleState.yMax,
        yMode: scaleState.yMode,
        xMode: scaleState.xMode,
        windowSize: scaleState.windowSize,
        xMin: scaleState.xMin,
        xMax: scaleState.xMax,
        showGrid: true,
        showHover: true,
      },
      mvConfig: {
        yMin: 0,
        yMax: 100,
        yMode: 'manual',
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
  menuHeight = 360,
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
