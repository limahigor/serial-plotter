import type { PlantStats } from '$lib/types/plant';

const DEFAULT_SAMPLE_TIME_MS = 100;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function toFiniteNumber(value: unknown, fallback = 0): number {
  const resolved = Number(value);
  return Number.isFinite(resolved) ? resolved : fallback;
}

export function normalizeSampleTimeMs(
  sampleTimeMs: number | null | undefined,
  fallback = DEFAULT_SAMPLE_TIME_MS,
): number {
  const resolved = Number(sampleTimeMs);
  if (!Number.isFinite(resolved)) return fallback;
  return Math.max(1, Math.round(resolved));
}

export function createEmptyPlantStats(sampleTimeMs: number): PlantStats {
  return {
    dt: sampleTimeMs / 1000,
    uptime: 0,
  };
}
