use crate::core::error::{AppError, AppResult};
use crate::core::models::plant::{Plant, PlantController, PlantDriver, PlantResponse, PlantStats, PlantVariable, VariableType};
use crate::state::PlantStore;
use serde::Serialize;
use std::collections::HashMap;
use std::path::Path;

#[derive(Debug, Clone)]
pub struct OpenPlantFilePayload {
    pub file_name: String,
    pub content: String,
    pub path: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ImportedVariableStatsResponse {
    pub error_avg: f64,
    pub stability: f64,
    pub ripple: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ImportedSeriesDescriptorResponse {
    pub key: String,
    pub label: String,
    pub role: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ImportedSeriesCatalogResponse {
    pub plant_id: String,
    pub series: Vec<ImportedSeriesDescriptorResponse>,
}

#[derive(Debug, Clone, Serialize)]
pub struct OpenPlantFileResponse {
    pub plant: PlantResponse,
    pub data: Vec<HashMap<String, f64>>,
    pub stats: PlantStats,
    pub variable_stats: Vec<ImportedVariableStatsResponse>,
    pub series_catalog: ImportedSeriesCatalogResponse,
}

pub struct PlantOpenService;

impl PlantOpenService {
    pub fn open_file(
        plants: &PlantStore,
        request: OpenPlantFilePayload,
    ) -> AppResult<OpenPlantFileResponse> {
        let (file_name, content) = resolve_registry_payload(&request)?;
        validate_registry_file_name(&file_name)?;

        let parsed = serde_json::from_str::<Plant>(&content)
            .map_err(|error| invalid_argument(format!("registry.json inválido: {error}")))?;
        let plant = normalize_opened_plant(parsed)?;

        if let Some(existing) = find_existing_plant(plants, &plant)? {
            return Ok(build_open_file_response(existing));
        }

        plants.insert(plant.clone())?;
        Ok(build_open_file_response(plant))
    }
}

fn invalid_argument(message: impl Into<String>) -> AppError {
    AppError::InvalidArgument(message.into())
}

fn resolve_registry_payload(request: &OpenPlantFilePayload) -> AppResult<(String, String)> {
    if let Some(path) = request.path.as_deref().map(str::trim).filter(|path| !path.is_empty()) {
        let content = std::fs::read_to_string(path).map_err(|error| {
            invalid_argument(format!("Falha ao ler registry.json em '{path}': {error}"))
        })?;
        let file_name = Path::new(path)
            .file_name()
            .and_then(|value| value.to_str())
            .map(str::to_string)
            .unwrap_or_else(|| request.file_name.clone());
        return Ok((file_name, content));
    }

    if request.content.trim().is_empty() {
        return Err(invalid_argument(
            "Conteúdo do registry.json é obrigatório quando nenhum caminho é informado",
        ));
    }

    Ok((request.file_name.clone(), request.content.clone()))
}

fn validate_registry_file_name(file_name: &str) -> AppResult<()> {
    let normalized = file_name.trim().to_lowercase();
    if normalized == "registry.json" {
        return Ok(());
    }

    Err(invalid_argument(
        "Abertura de planta aceita apenas o arquivo registry.json",
    ))
}

fn normalize_opened_plant(mut plant: Plant) -> AppResult<Plant> {
    plant.id = plant.id.trim().to_string();
    plant.name = plant.name.trim().to_string();

    if plant.id.is_empty() {
        return Err(invalid_argument("registry.json deve conter plant.id não vazio"));
    }

    if plant.name.is_empty() {
        return Err(invalid_argument("registry.json deve conter plant.name não vazio"));
    }

    if plant.variables.is_empty() {
        return Err(invalid_argument("registry.json deve conter ao menos uma variável"));
    }

    normalize_driver(&mut plant.driver)?;

    for controller in &mut plant.controllers {
        normalize_controller(controller)?;
        controller.active = false;
    }

    plant.connected = false;
    plant.paused = false;
    plant.stats = PlantStats {
        dt: milliseconds_to_seconds(plant.sample_time_ms),
        uptime: 0,
    };

    Ok(plant)
}

fn find_existing_plant(plants: &PlantStore, plant: &Plant) -> AppResult<Option<Plant>> {
    if let Ok(existing) = plants.get(&plant.id) {
        return Ok(Some(existing));
    }

    if let Some(existing) = plants.get_by_name(&plant.name) {
        if existing.id != plant.id {
            return Err(invalid_argument(format!(
                "Conflito de registro: já existe uma planta aberta com nome '{}' e id '{}'",
                existing.name.trim(),
                existing.id
            )));
        }

        return Ok(Some(existing));
    }

    Ok(None)
}

fn normalize_driver(driver: &mut PlantDriver) -> AppResult<()> {
    driver.plugin_id = driver.plugin_id.trim().to_string();
    driver.plugin_name = driver.plugin_name.trim().to_string();

    if driver.plugin_id.is_empty() {
        return Err(invalid_argument(
            "registry.json deve conter driver.plugin_id não vazio",
        ));
    }

    if driver.plugin_name.is_empty() {
        return Err(invalid_argument(
            "registry.json deve conter driver.plugin_name não vazio",
        ));
    }

    if let Some(source_file) = driver.source_file.as_mut() {
        *source_file = source_file.trim().to_string();
    }

    if let Some(source_code) = driver.source_code.as_mut() {
        *source_code = source_code.trim().to_string();
    }

    Ok(())
}

fn normalize_controller(controller: &mut PlantController) -> AppResult<()> {
    controller.id = controller.id.trim().to_string();
    controller.plugin_id = controller.plugin_id.trim().to_string();
    controller.plugin_name = controller.plugin_name.trim().to_string();
    controller.name = controller.name.trim().to_string();
    controller.controller_type = controller.controller_type.trim().to_string();

    if controller.id.is_empty() {
        return Err(invalid_argument(
            "registry.json deve conter controllers[].id não vazio",
        ));
    }

    if controller.plugin_id.is_empty() {
        return Err(invalid_argument(
            "registry.json deve conter controllers[].plugin_id não vazio",
        ));
    }

    if controller.plugin_name.is_empty() {
        return Err(invalid_argument(
            "registry.json deve conter controllers[].plugin_name não vazio",
        ));
    }

    if controller.name.is_empty() {
        return Err(invalid_argument(
            "registry.json deve conter controllers[].name não vazio",
        ));
    }

    if controller.controller_type.is_empty() {
        return Err(invalid_argument(
            "registry.json deve conter controllers[].controller_type não vazio",
        ));
    }

    Ok(())
}

fn build_open_file_response(plant: Plant) -> OpenPlantFileResponse {
    let stats = PlantStats {
        dt: milliseconds_to_seconds(plant.sample_time_ms),
        uptime: 0,
    };
    let variable_stats = plant
        .variables
        .iter()
        .map(compute_variable_stats)
        .collect::<Vec<_>>();
    let series_catalog = build_series_catalog(&plant.id, &plant.variables);

    OpenPlantFileResponse {
        plant: PlantResponse::from(plant),
        data: vec![],
        stats,
        variable_stats,
        series_catalog,
    }
}

fn compute_variable_stats(variable: &PlantVariable) -> ImportedVariableStatsResponse {
    if variable.var_type == VariableType::Atuador {
        return ImportedVariableStatsResponse {
            error_avg: 0.0,
            stability: 100.0,
            ripple: 0.0,
        };
    }

    ImportedVariableStatsResponse {
        error_avg: 0.0,
        stability: 100.0,
        ripple: 0.0,
    }
}

#[allow(clippy::cast_precision_loss)]
fn milliseconds_to_seconds(sample_time_ms: u64) -> f64 {
    sample_time_ms as f64 / 1000.0
}

fn build_series_catalog(
    plant_id: &str,
    variables: &[PlantVariable],
) -> ImportedSeriesCatalogResponse {
    let mut series = Vec::new();

    for (index, variable) in variables.iter().enumerate() {
        let pv_key = format!("var_{index}_pv");
        let sp_key = format!("var_{index}_sp");

        if variable.var_type == VariableType::Sensor {
            series.push(ImportedSeriesDescriptorResponse {
                key: pv_key,
                label: variable.name.clone(),
                role: "pv".into(),
            });
            series.push(ImportedSeriesDescriptorResponse {
                key: sp_key,
                label: format!("{} SP", variable.name),
                role: "sp".into(),
            });
            continue;
        }

        series.push(ImportedSeriesDescriptorResponse {
            key: pv_key,
            label: variable.name.clone(),
            role: "mv".into(),
        });
    }

    ImportedSeriesCatalogResponse {
        plant_id: plant_id.to_string(),
        series,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::models::plant::{ControllerParamType, ControllerRuntimeStatus};
    use crate::core::models::plugin::{PluginRuntime, SchemaFieldValue};
    use crate::state::PlantStore;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn sample_registry_json(plant_id: &str, plant_name: &str, controller_active: bool) -> String {
        format!(
            r#"{{
  "id": "{plant_id}",
  "name": "{plant_name}",
  "sample_time_ms": 500,
  "variables": [
    {{
      "id": "var_0",
      "name": "Temperatura",
      "type": "sensor",
      "unit": "C",
      "setpoint": 45.0,
      "pv_min": 0.0,
      "pv_max": 100.0
    }},
    {{
      "id": "var_1",
      "name": "Aquecedor",
      "type": "atuador",
      "unit": "%",
      "setpoint": 0.0,
      "pv_min": 0.0,
      "pv_max": 100.0,
      "linked_sensor_ids": ["var_0"]
    }}
  ],
  "driver": {{
    "plugin_id": "driver_mock",
    "plugin_name": "Driver Mock",
    "runtime": "python",
    "source_file": "main.py",
    "config": {{
      "baud": 9600
    }}
  }},
  "controllers": [
    {{
      "id": "ctrl_1",
      "plugin_id": "controller_pid",
      "plugin_name": "PID Controller",
      "name": "PID Temperatura",
      "controller_type": "PID",
      "active": {controller_active},
      "input_variable_ids": ["var_0"],
      "output_variable_ids": ["var_1"],
      "params": {{
        "kp": {{
          "type": "number",
          "value": 1.5,
          "label": "Kp"
        }}
      }},
      "runtime_status": "pending_restart"
    }}
  ]
}}"#
        )
    }

    #[test]
    fn open_file_loads_registry_with_canonical_id_and_inactive_controllers() {
        let plants = PlantStore::new();
        let response = PlantOpenService::open_file(
            &plants,
            OpenPlantFilePayload {
                file_name: "registry.json".to_string(),
                content: sample_registry_json("plant_a", "Planta A", true),
                path: None,
            },
        )
        .expect("open file should succeed");

        assert_eq!(response.plant.id, "plant_a");
        assert_eq!(response.plant.name, "Planta A");
        assert_eq!(response.plant.sample_time_ms, 500);
        assert_eq!(response.plant.controllers.len(), 1);
        assert!(!response.plant.controllers[0].active);
        assert_eq!(response.plant.controllers[0].runtime_status, ControllerRuntimeStatus::PendingRestart);
        assert_eq!(response.stats.dt, 0.5);
        assert_eq!(response.series_catalog.plant_id, "plant_a");
        assert!(matches!(
            response.plant.driver.config.get("baud"),
            Some(SchemaFieldValue::Int(9600))
        ));
        assert_eq!(response.plant.driver.runtime, PluginRuntime::Python);
        assert_eq!(response.variable_stats.len(), 2);
        assert!(plants.exists("plant_a"));
    }

    #[test]
    fn open_file_reuses_existing_plant_by_id_without_creating_duplicate() {
        let plants = PlantStore::new();

        let first_response = PlantOpenService::open_file(
            &plants,
            OpenPlantFilePayload {
                file_name: "registry.json".to_string(),
                content: sample_registry_json("plant_same", "Planta Same", false),
                path: None,
            },
        )
        .expect("first open should succeed");

        let second_response = PlantOpenService::open_file(
            &plants,
            OpenPlantFilePayload {
                file_name: "registry.json".to_string(),
                content: sample_registry_json("plant_same", "Planta Same", true),
                path: None,
            },
        )
        .expect("second open should reuse existing plant");

        assert_eq!(plants.count(), 1);
        assert_eq!(first_response.plant.id, second_response.plant.id);
        assert_eq!(second_response.plant.controllers[0].active, false);
    }

    #[test]
    fn open_file_rejects_name_conflict_with_different_id() {
        let plants = PlantStore::new();

        PlantOpenService::open_file(
            &plants,
            OpenPlantFilePayload {
                file_name: "registry.json".to_string(),
                content: sample_registry_json("plant_original", "Planta Conflito", false),
                path: None,
            },
        )
        .expect("first open should succeed");

        let error = PlantOpenService::open_file(
            &plants,
            OpenPlantFilePayload {
                file_name: "registry.json".to_string(),
                content: sample_registry_json("plant_other", "Planta Conflito", false),
                path: None,
            },
        )
        .expect_err("name conflict must fail");

        assert!(error
            .to_string()
            .contains("Conflito de registro: já existe uma planta aberta com nome 'Planta Conflito'"));
    }

    #[test]
    fn open_file_does_not_require_loaded_plugins_to_reopen_registry() {
        let plants = PlantStore::new();
        let response = PlantOpenService::open_file(
            &plants,
            OpenPlantFilePayload {
                file_name: "registry.json".to_string(),
                content: sample_registry_json("plant_unvalidated", "Planta Offline", false),
                path: None,
            },
        )
        .expect("registry open should not validate plugins");

        assert_eq!(response.plant.driver.plugin_id, "driver_mock");
        assert_eq!(response.plant.controllers[0].plugin_id, "controller_pid");
        assert_eq!(response.plant.controllers[0].params["kp"].param_type, ControllerParamType::Number);
    }

    #[test]
    fn open_file_rejects_non_registry_file_name() {
        let plants = PlantStore::new();
        let error = PlantOpenService::open_file(
            &plants,
            OpenPlantFilePayload {
                file_name: "planta.json".to_string(),
                content: sample_registry_json("plant_x", "Planta X", false),
                path: None,
            },
        )
        .expect_err("only registry.json should be accepted");

        assert!(error
            .to_string()
            .contains("Abertura de planta aceita apenas o arquivo registry.json"));
    }

    #[test]
    fn open_file_reads_registry_from_path_when_available() {
        let plants = PlantStore::new();
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time should move forward")
            .as_nanos();
        let temp_dir = std::env::temp_dir().join(format!("senamby_registry_test_{unique}"));
        fs::create_dir_all(&temp_dir).expect("temp dir should be created");
        let registry_path = temp_dir.join("registry.json");
        fs::write(
            &registry_path,
            sample_registry_json("plant_from_path", "Planta Path", false),
        )
        .expect("registry should be written");

        let response = PlantOpenService::open_file(
            &plants,
            OpenPlantFilePayload {
                file_name: String::new(),
                content: String::new(),
                path: Some(registry_path.to_string_lossy().into_owned()),
            },
        )
        .expect("open file should read registry from path");

        assert_eq!(response.plant.id, "plant_from_path");
        assert_eq!(response.plant.name, "Planta Path");

        let _ = fs::remove_file(&registry_path);
        let _ = fs::remove_dir(&temp_dir);
    }
}
