// @ts-check

/**
 * @template {{ id: string }} T
 * @param {readonly T[]} tabs
 * @param {T} nextTab
 * @returns {T[]}
 */
export function openPlantTabs(tabs, nextTab) {
  const existingIndex = tabs.findIndex((tab) => tab.id === nextTab.id);
  if (existingIndex < 0) {
    return [...tabs, nextTab];
  }

  return tabs.map((tab) => (tab.id === nextTab.id ? nextTab : tab));
}

/**
 * @template {{ id: string }} T
 * @param {readonly T[]} tabs
 * @param {string} plantId
 * @returns {T[]}
 */
export function removePlantTabs(tabs, plantId) {
  return tabs.filter((tab) => tab.id !== plantId);
}

/**
 * @template {{ id: string }} T
 * @param {readonly T[]} tabs
 * @param {string} movedPlantId
 * @param {string} targetPlantId
 * @param {'before' | 'after'} position
 * @returns {T[]}
 */
export function movePlantTab(tabs, movedPlantId, targetPlantId, position) {
  if (movedPlantId === targetPlantId) {
    return [...tabs];
  }

  const movedIndex = tabs.findIndex((tab) => tab.id === movedPlantId);
  const targetIndex = tabs.findIndex((tab) => tab.id === targetPlantId);
  if (movedIndex < 0 || targetIndex < 0) {
    return [...tabs];
  }

  const nextTabs = [...tabs];
  const [movedTab] = nextTabs.splice(movedIndex, 1);
  const normalizedTargetIndex = nextTabs.findIndex((tab) => tab.id === targetPlantId);
  const insertIndex =
    position === 'after' ? normalizedTargetIndex + 1 : normalizedTargetIndex;

  nextTabs.splice(insertIndex, 0, movedTab);
  return nextTabs;
}

/**
 * @template {{ id: string }} T
 * @param {readonly T[]} tabs
 * @param {string | null} currentActivePlantId
 * @param {string | null} preferredPlantId
 * @returns {string | null}
 */
export function resolveActivePlantId(tabs, currentActivePlantId, preferredPlantId) {
  if (preferredPlantId && tabs.some((plant) => plant.id === preferredPlantId)) {
    return preferredPlantId;
  }

  if (currentActivePlantId && tabs.some((plant) => plant.id === currentActivePlantId)) {
    return currentActivePlantId;
  }

  return tabs[0]?.id ?? null;
}

/**
 * @param {Record<string, number> | null | undefined} writtenOutputs
 * @param {Record<string, number> | null | undefined} actuatorReadings
 * @param {string} actuatorId
 * @returns {number}
 */
export function resolveActuatorTelemetryValue(writtenOutputs, actuatorReadings, actuatorId) {
  const writtenValue = Number(writtenOutputs?.[actuatorId]);
  if (Number.isFinite(writtenValue)) {
    return writtenValue;
  }

  const actuatorValue = Number(actuatorReadings?.[actuatorId]);
  return Number.isFinite(actuatorValue) ? actuatorValue : 0;
}
