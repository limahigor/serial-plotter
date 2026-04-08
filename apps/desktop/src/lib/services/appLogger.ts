import { appendConsoleLog } from '$lib/services/console';
import type { AppendConsoleLogInput, ConsoleLogLevel } from '$lib/types/console';

let installed = false;

const rawConsole = {
  debug: console.debug.bind(console),
  info: console.info.bind(console),
  warn: console.warn.bind(console),
  error: console.error.bind(console),
};

function serializeArg(value: unknown): unknown {
  if (value instanceof Error) {
    return {
      name: value.name,
      message: value.message,
      stack: value.stack,
    };
  }

  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' || value === null) {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map(serializeArg);
  }

  if (value && typeof value === 'object') {
    try {
      return JSON.parse(JSON.stringify(value));
    } catch {
      return String(value);
    }
  }

  return String(value);
}

function buildMessage(args: unknown[]): string {
  return args
    .map((value) => {
      if (value instanceof Error) return `${value.name}: ${value.message}`;
      if (typeof value === 'string') return value;
      try {
        return JSON.stringify(serializeArg(value));
      } catch {
        return String(value);
      }
    })
    .join(' ')
    .trim();
}

function sendToConsoleModule(level: ConsoleLogLevel, args: unknown[]) {
  const message = buildMessage(args);
  if (!message) return;

  const payload: AppendConsoleLogInput = {
    level,
    message,
    sourceScope: 'app',
    sourceKind: 'frontend',
    details: {
      args: args.map(serializeArg),
    },
  };

  void appendConsoleLog(payload);
}

function createLogger(level: ConsoleLogLevel, sink: (...args: unknown[]) => void) {
  return (...args: unknown[]) => {
    sink(...args);
    sendToConsoleModule(level, args);
  };
}

function isIgnorableBrowserResizeObserverError(message: string | undefined | null) {
  if (!message) {
    return false;
  }

  return message === 'ResizeObserver loop completed with undelivered notifications.'
    || message === 'ResizeObserver loop limit exceeded';
}

function handleWindowError(event: ErrorEvent) {
  if (isIgnorableBrowserResizeObserverError(event.message)) {
    return;
  }

  void appendConsoleLog({
    level: 'error',
    message: event.message || 'Erro não tratado no frontend',
    sourceScope: 'app',
    sourceKind: 'frontend',
    details: {
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
      stack: event.error instanceof Error ? event.error.stack : null,
    },
  });
}

function handleUnhandledRejection(event: PromiseRejectionEvent) {
  const reason = event.reason instanceof Error
    ? `${event.reason.name}: ${event.reason.message}`
    : String(event.reason ?? 'Promise rejection sem detalhes');

  void appendConsoleLog({
    level: 'error',
    message: reason,
    sourceScope: 'app',
    sourceKind: 'frontend',
    details: {
      reason: serializeArg(event.reason),
    },
  });
}

export const appLogger = {
  debug: createLogger('debug', rawConsole.debug),
  info: createLogger('info', rawConsole.info),
  warn: createLogger('warning', rawConsole.warn),
  error: createLogger('error', rawConsole.error),
};

export function installAppLogger() {
  if (installed || typeof window === 'undefined') {
    return () => {};
  }

  installed = true;
  window.addEventListener('error', handleWindowError);
  window.addEventListener('unhandledrejection', handleUnhandledRejection);

  return () => {
    window.removeEventListener('error', handleWindowError);
    window.removeEventListener('unhandledrejection', handleUnhandledRejection);
    installed = false;
  };
}
