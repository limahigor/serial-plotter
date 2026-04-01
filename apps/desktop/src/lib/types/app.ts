import type { TabKey } from './ui';

export interface AppState {
  theme: 'dark' | 'light';
  activeModule: TabKey;
  sidebarCollapsed: boolean;
  showGlobalSettings: boolean;
  showControllerPanel: boolean;
}
