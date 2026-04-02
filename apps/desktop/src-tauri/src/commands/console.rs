#![allow(clippy::needless_pass_by_value)]

use crate::core::error::ErrorDto;
use crate::core::models::console::{
    AppendConsoleLogRequest, ConsoleLogEntry, ConsoleOverviewResponse,
    DeleteConsoleAlertRuleRequest, ListConsoleLogsRequest, SaveConsoleAlertRuleRequest,
};
use crate::core::services::console::ConsoleService;
use crate::state::AppState;
use tauri::{AppHandle, State};

#[tauri::command]
pub fn get_console_overview(state: State<'_, AppState>) -> ConsoleOverviewResponse {
    ConsoleService::get_overview(state.console())
}

#[tauri::command]
pub fn list_console_logs(
    state: State<'_, AppState>,
    request: ListConsoleLogsRequest,
) -> Result<Vec<ConsoleLogEntry>, ErrorDto> {
    ConsoleService::list_logs(state.console(), request).map_err(ErrorDto::from)
}

#[tauri::command]
pub fn append_console_log(
    app: AppHandle,
    state: State<'_, AppState>,
    request: AppendConsoleLogRequest,
) -> Result<ConsoleLogEntry, ErrorDto> {
    ConsoleService::append_log(Some(&app), state.console(), request.into()).map_err(ErrorDto::from)
}

#[tauri::command]
pub fn save_console_alert_rule(
    app: AppHandle,
    state: State<'_, AppState>,
    request: SaveConsoleAlertRuleRequest,
) -> Result<ConsoleOverviewResponse, ErrorDto> {
    ConsoleService::save_alert_rule(&app, state.console(), request).map_err(ErrorDto::from)
}

#[tauri::command]
pub fn delete_console_alert_rule(
    app: AppHandle,
    state: State<'_, AppState>,
    request: DeleteConsoleAlertRuleRequest,
) -> Result<ConsoleOverviewResponse, ErrorDto> {
    ConsoleService::delete_alert_rule(&app, state.console(), request).map_err(ErrorDto::from)
}

#[tauri::command]
pub fn mark_console_alerts_read(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<ConsoleOverviewResponse, ErrorDto> {
    ConsoleService::mark_alerts_read(&app, state.console()).map_err(ErrorDto::from)
}

#[tauri::command]
pub fn clear_console_logs(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<ConsoleOverviewResponse, ErrorDto> {
    ConsoleService::clear_logs(&app, state.console()).map_err(ErrorDto::from)
}
