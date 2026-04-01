import { invoke } from '@tauri-apps/api/core';
import { extractServiceErrorMessage } from '$lib/services/shared/errorMessage';
import { mapDtoToPlant, normalizeImportedSeriesCatalog, normalizeImportedVariableStats } from './mappers';
import type { OpenPlantFileCommandResponse, OpenPlantRequest, OpenPlantResponse } from './types';

function resolveRegistryFileName(request: OpenPlantRequest): string {
  const requestedFileName = request.fileName?.trim();
  if (requestedFileName) {
    return requestedFileName;
  }

  const normalizedPath = request.path.replace(/\\/g, '/');
  return normalizedPath.split('/').pop() ?? '';
}

export async function openPlant(request: OpenPlantRequest): Promise<OpenPlantResponse> {
  const fileName = resolveRegistryFileName(request);
  if (fileName.toLowerCase() !== 'registry.json') {
    return {
      success: false,
      error: 'Selecione o arquivo registry.json da planta para reabri-la',
    };
  }

  try {
    const response = await invoke<OpenPlantFileCommandResponse>('open_plant_file', {
      request: {
        fileName,
        content: '',
        path: request.path,
      },
    });
    const plant = mapDtoToPlant(response.plant);

    return {
      success: true,
      plant,
      data: response.data,
      stats: response.stats,
      variableStats: (response.variable_stats ?? []).map(normalizeImportedVariableStats),
      seriesCatalog: normalizeImportedSeriesCatalog(response.series_catalog, plant.id),
    };
  } catch (error) {
    return {
      success: false,
      error: extractServiceErrorMessage(error, 'Erro ao abrir arquivo'),
    };
  }
}
