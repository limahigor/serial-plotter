// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
mod commands;
mod core;
mod state;

use crate::commands::console::{
    append_console_log, clear_console_logs, delete_console_alert_rule, get_console_overview,
    list_console_logs, mark_console_alerts_read, save_console_alert_rule,
};
use crate::commands::plants::{
    close_plant, connect_plant, create_plant, disconnect_plant, get_plant, list_plants,
    open_plant_file, pause_plant, remove_controller, remove_plant, resume_plant, save_controller,
    save_export_file, save_setpoint, update_plant,
};
use crate::commands::plugins::{
    create_plugin, delete_plugin, get_plugin, import_plugin_file, list_plugins,
    list_plugins_by_type, load_plugins, update_plugin,
};
use crate::state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
/// Runs the Senamby desktop application.
///
/// # Panics
///
/// Panics if Tauri fails to initialize or run the desktop application.
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![
            create_plant,
            update_plant,
            list_plants,
            get_plant,
            open_plant_file,
            close_plant,
            remove_plant,
            connect_plant,
            disconnect_plant,
            pause_plant,
            resume_plant,
            save_controller,
            remove_controller,
            save_setpoint,
            save_export_file,
            get_console_overview,
            list_console_logs,
            append_console_log,
            save_console_alert_rule,
            delete_console_alert_rule,
            mark_console_alerts_read,
            clear_console_logs,
            create_plugin,
            delete_plugin,
            get_plugin,
            update_plugin,
            import_plugin_file,
            load_plugins,
            list_plugins,
            list_plugins_by_type,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
