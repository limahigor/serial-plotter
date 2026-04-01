import { open as openNativeDialog } from '@tauri-apps/plugin-dialog';

export interface FileFilter {
  name: string;
  extensions: readonly string[] | string[];
}

export interface OpenFileOptions {
  title?: string;
  filters?: readonly FileFilter[];
  multiple?: boolean;
}

export interface FileResult {
  file: File;
  name: string;
  path: string;
  extension: string;
}

export interface FilePathResult {
  name: string;
  path: string;
  extension: string;
}

function isTauriRuntime(): boolean {
  if (typeof window === 'undefined') return false;
  return '__TAURI_INTERNALS__' in window || '__TAURI__' in window;
}

function normalizeDialogPath(path: string | string[] | null): string | null {
  if (typeof path === 'string') return path;
  if (Array.isArray(path) && path.length > 0) return path[0] ?? null;
  return null;
}

function buildPathResult(path: string): FilePathResult {
  const normalizedPath = path.replace(/\\/g, '/');
  const name = normalizedPath.split('/').pop() ?? path;
  const extension = name.split('.').pop()?.toLowerCase() ?? '';

  return {
    name,
    path,
    extension,
  };
}

export function openFileDialog(options: OpenFileOptions = {}): Promise<FileResult | null> {
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.style.display = 'none';
    let settled = false;
    
    if (options.filters && options.filters.length > 0) {
      const accept = options.filters
        .flatMap(f => f.extensions.map(ext => `.${ext}`))
        .join(',');
      input.accept = accept;
    }
    
    input.multiple = options.multiple ?? false;

    const cleanup = () => {
      if (input.parentNode) {
        input.parentNode.removeChild(input);
      }
      window.removeEventListener('focus', handleFocus);
    };

    const finish = (result: FileResult | null) => {
      if (settled) return;
      settled = true;
      resolve(result);
      cleanup();
    };

    input.onchange = () => {
      const file = input.files?.[0];
      if (file) {
        const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
        finish({
          file,
          name: file.name,
          path: file.name,
          extension,
        });
      } else {
        finish(null);
      }
    };
    
    input.oncancel = () => {
      finish(null);
    };
    
    function handleFocus() {
      setTimeout(() => {
        if (!input.files?.length) {
          finish(null);
        }
      }, 300);
    }
    
    document.body.appendChild(input);
    window.addEventListener('focus', handleFocus);
    input.click();
  });
}

export async function openFilePathDialog(options: OpenFileOptions = {}): Promise<FilePathResult | null> {
  if (isTauriRuntime()) {
    const selected = await openNativeDialog({
      title: options.title,
      filters: options.filters?.map((filter) => ({
        name: filter.name,
        extensions: [...filter.extensions],
      })),
      multiple: options.multiple ?? false,
      directory: false,
    });

    const path = normalizeDialogPath(selected);
    return path ? buildPathResult(path) : null;
  }

  const result = await openFileDialog(options);
  if (!result) return null;

  return {
    name: result.name,
    path: result.path,
    extension: result.extension,
  };
}

export function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error('Erro ao ler arquivo'));
    reader.readAsText(file);
  });
}

export async function readFileAsJSON<T = unknown>(file: File): Promise<T> {
  const text = await readFileAsText(file);
  return JSON.parse(text) as T;
}

/**
 * Filtros pré-definidos para tipos comuns de arquivos.
 */
export const FILE_FILTERS = {
  plant: [{ name: 'Planta', extensions: ['plant', 'json'] }],
  csv: [{ name: 'CSV', extensions: ['csv'] }],
  json: [{ name: 'JSON', extensions: ['json'] }],
  all: [{ name: 'Todos', extensions: ['*'] }],
} as const;
