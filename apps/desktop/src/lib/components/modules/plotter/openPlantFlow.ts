import { FILE_FILTERS, openFilePathDialog } from '$lib/services/fileDialog';
import { openPlant, type OpenPlantResponse } from '$lib/services/plant';
import { appStore } from '$lib/stores/data.svelte';
import {
  clearVariableStats,
  setPlantData,
  setPlantSeriesCatalog,
  setPlantStats,
  setVariableStats,
} from '$lib/stores/plantData';
import { buildPlantSeriesCatalog } from '$lib/types/plant';

export async function promptOpenPlantFile(): Promise<OpenPlantResponse | null> {
  const selectedFile = await openFilePathDialog({
    title: 'Abrir Planta',
    filters: FILE_FILTERS.plant,
  });

  if (!selectedFile) {
    return null;
  }

  return openPlantFilePath(selectedFile.path, selectedFile.name);
}

export function openPlantFilePath(path: string, fileName?: string): Promise<OpenPlantResponse> {
  return openPlant({
    path,
    fileName,
  });
}

export function applyOpenedPlantResult(result: OpenPlantResponse): { warning?: string } {
  if (!result.success || !result.plant) {
    throw new Error(result.error || 'Erro ao abrir planta');
  }

  appStore.openPlant(result.plant);
  setPlantData(result.plant.id, result.data ?? []);
  setPlantSeriesCatalog(
    result.seriesCatalog ?? buildPlantSeriesCatalog(result.plant.id, result.plant.variables),
  );
  setPlantStats(result.plant.id, result.stats ?? result.plant.stats);
  clearVariableStats(result.plant.id);

  for (const [index, stats] of (result.variableStats ?? []).entries()) {
    setVariableStats(result.plant.id, index, stats);
  }

  return { warning: result.warning };
}
