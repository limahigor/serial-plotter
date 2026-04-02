use crate::core::services::console::ConsoleService;
use crate::core::services::plugin::PluginService;
use crate::core::services::runtime::PlantRuntimeManager;
use crate::state::{console_store::ConsoleStore, plant_store::PlantStore, PluginStore};
use std::sync::Arc;

#[derive(Clone)]
pub struct AppState {
    console_store: Arc<ConsoleStore>,
    plant_store: Arc<PlantStore>,
    plugin_store: Arc<PluginStore>,
    runtime_manager: Arc<PlantRuntimeManager>,
}

impl AppState {
    pub fn new() -> Self {
        let console_store = Arc::new(ConsoleStore::new());
        let plant_store = Arc::new(PlantStore::new());
        let plugin_store = Arc::new(PluginStore::new());
        let runtime_manager = Arc::new(PlantRuntimeManager::new());
        if let Err(error) = ConsoleService::load(console_store.as_ref()) {
            eprintln!("Falha ao carregar console do workspace na inicialização: {error}");
        }
        if let Err(error) = PluginService::load_all(&plugin_store) {
            let _ = ConsoleService::append_backend_error(
                console_store.as_ref(),
                "Falha ao carregar plugins do workspace na inicialização",
                Some(serde_json::json!({ "error": error.to_string() })),
            );
            eprintln!("Falha ao carregar plugins do workspace na inicialização: {error}");
        }

        Self {
            console_store,
            plant_store,
            plugin_store,
            runtime_manager,
        }
    }

    pub fn console(&self) -> &ConsoleStore {
        &self.console_store
    }

    pub fn console_handle(&self) -> Arc<ConsoleStore> {
        self.console_store.clone()
    }

    pub fn plants(&self) -> &PlantStore {
        &self.plant_store
    }

    pub fn plugins(&self) -> &PluginStore {
        &self.plugin_store
    }

    pub fn runtimes(&self) -> &PlantRuntimeManager {
        &self.runtime_manager
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self::new()
    }
}
