use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConsoleLogLevel {
    Debug,
    Info,
    Warning,
    Error,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConsoleSourceScope {
    App,
    Plant,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConsoleSourceKind {
    Frontend,
    Backend,
    Runtime,
    Driver,
    Controller,
    NativeOutput,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsoleLogEntry {
    pub id: String,
    pub timestamp: DateTime<Utc>,
    pub level: ConsoleLogLevel,
    pub message: String,
    pub source_scope: ConsoleSourceScope,
    pub source_kind: ConsoleSourceKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub plant_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub plant_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub runtime_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub plugin_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub plugin_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub controller_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub controller_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<Value>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AppendConsoleLogRequest {
    pub level: ConsoleLogLevel,
    pub message: String,
    pub source_scope: ConsoleSourceScope,
    pub source_kind: ConsoleSourceKind,
    #[serde(default)]
    pub plant_id: Option<String>,
    #[serde(default)]
    pub plant_name: Option<String>,
    #[serde(default)]
    pub runtime_id: Option<String>,
    #[serde(default)]
    pub plugin_id: Option<String>,
    #[serde(default)]
    pub plugin_name: Option<String>,
    #[serde(default)]
    pub controller_id: Option<String>,
    #[serde(default)]
    pub controller_name: Option<String>,
    #[serde(default)]
    pub details: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ConsoleAlertTarget {
    App,
    AllPlants,
    SelectedPlants { plant_ids: Vec<String> },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsoleAlertRule {
    pub id: String,
    pub name: String,
    pub enabled: bool,
    #[serde(default)]
    pub levels: Vec<ConsoleLogLevel>,
    pub target: ConsoleAlertTarget,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SaveConsoleAlertRuleRequest {
    #[serde(default)]
    pub id: Option<String>,
    pub name: String,
    #[serde(default = "default_alert_enabled")]
    pub enabled: bool,
    #[serde(default)]
    pub levels: Vec<ConsoleLogLevel>,
    pub target: ConsoleAlertTarget,
}

fn default_alert_enabled() -> bool {
    true
}

#[derive(Debug, Clone, Deserialize)]
pub struct DeleteConsoleAlertRuleRequest {
    pub id: String,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct ListConsoleLogsRequest {
    #[serde(default)]
    pub levels: Vec<ConsoleLogLevel>,
    #[serde(default)]
    pub source_scope: Option<ConsoleSourceScope>,
    #[serde(default)]
    pub plant_id: Option<String>,
    #[serde(default)]
    pub search: Option<String>,
    #[serde(default)]
    pub limit: Option<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsolePlantOption {
    pub plant_id: String,
    pub plant_name: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ConsoleState {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_alert_read_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ConsoleOverviewResponse {
    pub badge_count: usize,
    pub rules: Vec<ConsoleAlertRule>,
    pub known_plants: Vec<ConsolePlantOption>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_alert_read_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ConsoleBadgeEvent {
    pub badge_count: usize,
}

#[derive(Debug, Clone)]
pub struct ConsoleLogInput {
    pub level: ConsoleLogLevel,
    pub message: String,
    pub source_scope: ConsoleSourceScope,
    pub source_kind: ConsoleSourceKind,
    pub plant_id: Option<String>,
    pub plant_name: Option<String>,
    pub runtime_id: Option<String>,
    pub plugin_id: Option<String>,
    pub plugin_name: Option<String>,
    pub controller_id: Option<String>,
    pub controller_name: Option<String>,
    pub details: Option<Value>,
}

impl From<AppendConsoleLogRequest> for ConsoleLogInput {
    fn from(value: AppendConsoleLogRequest) -> Self {
        Self {
            level: value.level,
            message: value.message,
            source_scope: value.source_scope,
            source_kind: value.source_kind,
            plant_id: value.plant_id,
            plant_name: value.plant_name,
            runtime_id: value.runtime_id,
            plugin_id: value.plugin_id,
            plugin_name: value.plugin_name,
            controller_id: value.controller_id,
            controller_name: value.controller_name,
            details: value.details,
        }
    }
}
