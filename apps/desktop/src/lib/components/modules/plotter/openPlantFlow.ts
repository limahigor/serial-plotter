import { FILE_FILTERS, openFilePathDialog } from '$lib/services/fileDialog';
import { openPlant, type OpenPlantResponse } from '$lib/services/plant';
import { appStore } from '$lib/stores/data.svelte';
import {
  clearVariableStats,
  getRecommendedPlantBufferConfig,
  setPlantBufferConfig,
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

export async function openPlantFromDialog(): Promise<{ warning?: string; cancelled?: boolean }> {
  const result = await promptOpenPlantFile();
  if (!result) {
    return { cancelled: true };
  }

  return applyOpenedPlantResult(result);
}

export function openPlantFilePath(path: string, fileName?: string): Promise<OpenPlantResponse> {
  return openPlant({
    path,
    fileName,
  });
}

export function isRegistryJsonFile(file: File): boolean {
  return file.name.trim().toLowerCase() === 'registry.json';
}

export function resolveDroppedRegistryPath(file: File): string {
  const candidatePath = (file as File & { path?: string }).path;
  return typeof candidatePath === 'string' ? candidatePath : '';
}

export async function openDroppedRegistryFile(
  file: File,
): Promise<{ warning?: string }> {
  const droppedPath = resolveDroppedRegistryPath(file);
  if (!droppedPath) {
    throw new Error('Não foi possível resolver o caminho do registry.json selecionado.');
  }

  return applyOpenedPlantResult(
    await openPlantFilePath(droppedPath, file.name),
  );
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
  setPlantBufferConfig(result.plant.id, getRecommendedPlantBufferConfig(result.plant.sampleTimeMs));
  setPlantStats(result.plant.id, result.stats ?? result.plant.stats);
  clearVariableStats(result.plant.id);

  for (const [index, stats] of (result.variableStats ?? []).entries()) {
    setVariableStats(result.plant.id, index, stats);
  }

  return { warning: result.warning };
}
