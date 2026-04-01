import test from 'node:test';
import assert from 'node:assert/strict';

import {
  movePlantTab,
  openPlantTabs,
  resolveActivePlantId,
  resolveActuatorTelemetryValue,
} from './tabState.js';

test('openPlantTabs appends a newly opened plant after the last tab', () => {
  const plantA = { id: 'plant_a', name: 'Plant A' };
  const plantB = { id: 'plant_b', name: 'Plant B' };

  const openedOnce = openPlantTabs([], plantA);
  const openedTwice = openPlantTabs(openedOnce, plantB);

  assert.deepEqual(
    openedTwice.map((plant) => plant.id),
    ['plant_a', 'plant_b'],
  );
  assert.equal(resolveActivePlantId(openedTwice, 'plant_a', 'plant_b'), 'plant_b');
});

test('openPlantTabs reuses an existing tab without duplicating or moving it', () => {
  const plantA = { id: 'plant_a', name: 'Plant A' };
  const plantB = { id: 'plant_b', name: 'Plant B' };
  const updatedPlantA = { id: 'plant_a', name: 'Plant A+' };

  const reopened = openPlantTabs([plantA, plantB], updatedPlantA);

  assert.deepEqual(
    reopened.map((plant) => plant.id),
    ['plant_a', 'plant_b'],
  );
  assert.equal(reopened[0].name, 'Plant A+');
});

test('resolveActuatorTelemetryValue prefers written outputs and falls back to actuator readings', () => {
  assert.equal(
    resolveActuatorTelemetryValue(
      { actuator_1: 11, actuator_2: 22 },
      { actuator_1: 1, actuator_2: 2 },
      'actuator_2',
    ),
    22,
  );

  assert.equal(
    resolveActuatorTelemetryValue(
      {},
      { actuator_1: 1, actuator_2: 2 },
      'actuator_2',
    ),
    2,
  );
});

test('movePlantTab reorders tabs before or after the target tab', () => {
  const tabs = [
    { id: 'plant_a', name: 'Plant A' },
    { id: 'plant_b', name: 'Plant B' },
    { id: 'plant_c', name: 'Plant C' },
  ];

  const movedAfter = movePlantTab(tabs, 'plant_a', 'plant_c', 'after');
  assert.deepEqual(
    movedAfter.map((plant) => plant.id),
    ['plant_b', 'plant_c', 'plant_a'],
  );

  const movedBefore = movePlantTab(movedAfter, 'plant_c', 'plant_b', 'before');
  assert.deepEqual(
    movedBefore.map((plant) => plant.id),
    ['plant_c', 'plant_b', 'plant_a'],
  );
});
