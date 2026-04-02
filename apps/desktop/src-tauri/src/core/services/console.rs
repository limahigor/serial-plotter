use crate::core::error::{AppError, AppResult};
use crate::core::models::console::{
    ConsoleAlertRule, ConsoleAlertTarget, ConsoleBadgeEvent, ConsoleLogEntry, ConsoleLogInput,
    ConsoleLogLevel, ConsoleOverviewResponse, ConsolePlantOption, ConsoleSourceKind,
    ConsoleSourceScope, ConsoleState, DeleteConsoleAlertRuleRequest, ListConsoleLogsRequest,
    SaveConsoleAlertRuleRequest,
};
use crate::core::services::workspace::{map_io_error, map_serde_error, WorkspaceService};
use crate::state::{
    ConsoleStore,
    console_store::{ConsoleStoreState, MAX_RECENT_ENTRIES},
};
use chrono::{DateTime, Duration, NaiveDate, Utc};
use serde_json::Value;
use std::collections::{BTreeMap, VecDeque};
use std::fs::{self, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Emitter, Runtime};
use uuid::Uuid;

const LOG_RETENTION_DAYS: i64 = 30;
const DEFAULT_LOG_QUERY_LIMIT: usize = 200;
const MAX_LOG_QUERY_LIMIT: usize = 1000;
const CONSOLE_ENTRY_EVENT: &str = "console://entry";
const CONSOLE_BADGE_EVENT: &str = "console://badge";

pub struct ConsoleService;

impl ConsoleService {
    pub fn load(console: &ConsoleStore) -> AppResult<()> {
        ensure_console_layout()?;
        prune_old_log_files()?;

        let rules = load_alert_rules()?;
        let console_state = load_console_state()?;
        let mut entries = read_retained_log_entries()?;
        entries.sort_by(|left, right| right.timestamp.cmp(&left.timestamp));

        let recent_entries = entries
            .iter()
            .take(500)
            .cloned()
            .collect::<VecDeque<_>>();
        let known_plants = collect_known_plants(&entries);
        let badge_count = compute_badge_count(
            &entries,
            &rules,
            console_state.last_alert_read_at.as_ref(),
        );

        console.replace_all(ConsoleStoreState {
            recent_entries,
            rules,
            known_plants,
            console_state,
            badge_count,
        });

        Ok(())
    }

    pub fn get_overview(console: &ConsoleStore) -> ConsoleOverviewResponse {
        let snapshot = console.snapshot();
        ConsoleOverviewResponse {
            badge_count: snapshot.badge_count,
            rules: snapshot.rules,
            known_plants: snapshot.known_plants,
            last_alert_read_at: snapshot.console_state.last_alert_read_at,
        }
    }

    pub fn list_logs(
        console: &ConsoleStore,
        request: ListConsoleLogsRequest,
    ) -> AppResult<Vec<ConsoleLogEntry>> {
        let limit = resolve_log_query_limit(request.limit);

        if let Some(entries) = list_recent_logs_from_cache(console, &request, limit) {
            return Ok(entries);
        }

        prune_old_log_files()?;
        let mut entries = read_retained_log_entries()?;
        entries.retain(|entry| matches_log_filters(entry, &request));
        entries.sort_by(|left, right| right.timestamp.cmp(&left.timestamp));
        entries.truncate(limit);
        Ok(entries)
    }

    pub fn append_backend_error(
        console: &ConsoleStore,
        message: &str,
        details: Option<Value>,
    ) -> AppResult<ConsoleLogEntry> {
        Self::append_log::<tauri::Wry>(
            None,
            console,
            ConsoleLogInput {
                level: ConsoleLogLevel::Error,
                message: message.to_string(),
                source_scope: ConsoleSourceScope::App,
                source_kind: ConsoleSourceKind::Backend,
                plant_id: None,
                plant_name: None,
                runtime_id: None,
                plugin_id: None,
                plugin_name: None,
                controller_id: None,
                controller_name: None,
                details,
            },
        )
    }

    pub fn append_log<R: Runtime>(
        app: Option<&AppHandle<R>>,
        console: &ConsoleStore,
        input: ConsoleLogInput,
    ) -> AppResult<ConsoleLogEntry> {
        let message = input.message.trim();
        if message.is_empty() {
            return Err(AppError::InvalidArgument(
                "Mensagem de log não pode ser vazia".into(),
            ));
        }

        ensure_console_layout()?;

        let entry = ConsoleLogEntry {
            id: format!("log_{}", Uuid::new_v4().simple()),
            timestamp: Utc::now(),
            level: input.level,
            message: message.to_string(),
            source_scope: input.source_scope,
            source_kind: input.source_kind,
            plant_id: input.plant_id,
            plant_name: input.plant_name,
            runtime_id: input.runtime_id,
            plugin_id: input.plugin_id,
            plugin_name: input.plugin_name,
            controller_id: input.controller_id,
            controller_name: input.controller_name,
            details: input.details,
        };

        append_entry_to_disk(&entry)?;
        console.push_recent_entry(entry.clone());
        if let (Some(plant_id), Some(plant_name)) = (&entry.plant_id, &entry.plant_name) {
            console.register_known_plant(ConsolePlantOption {
                plant_id: plant_id.clone(),
                plant_name: plant_name.clone(),
            });
        }

        let snapshot = console.snapshot();
        let should_increment_badge =
            entry_matches_any_rule(&entry, &snapshot.rules)
                && snapshot
                    .console_state
                    .last_alert_read_at
                    .is_none_or(|timestamp| entry.timestamp > timestamp);

        let next_badge_count = if should_increment_badge {
            let next = snapshot.badge_count.saturating_add(1);
            console.set_badge_count(next);
            next
        } else {
            snapshot.badge_count
        };

        if let Some(app) = app {
            emit_entry_event(app, &entry);
            if should_increment_badge {
                emit_badge_event(app, next_badge_count);
            }
        }

        Ok(entry)
    }

    pub fn save_alert_rule<R: Runtime>(
        app: &AppHandle<R>,
        console: &ConsoleStore,
        request: SaveConsoleAlertRuleRequest,
    ) -> AppResult<ConsoleOverviewResponse> {
        let name = request.name.trim();
        if name.is_empty() {
            return Err(AppError::InvalidArgument(
                "Nome da regra de alerta é obrigatório".into(),
            ));
        }

        if let ConsoleAlertTarget::SelectedPlants { plant_ids } = &request.target {
            if plant_ids.is_empty() {
                return Err(AppError::InvalidArgument(
                    "Selecione pelo menos uma planta para a regra".into(),
                ));
            }
        }

        let mut rules = load_alert_rules()?;
        let rule_id = request
            .id
            .map(|id| id.trim().to_string())
            .filter(|id| !id.is_empty())
            .unwrap_or_else(|| format!("alert_{}", Uuid::new_v4().simple()));
        let next_rule = ConsoleAlertRule {
            id: rule_id,
            name: name.to_string(),
            enabled: request.enabled,
            levels: request.levels,
            target: request.target,
        };

        if let Some(rule) = rules.iter_mut().find(|rule| rule.id == next_rule.id) {
            *rule = next_rule;
        } else {
            rules.push(next_rule);
        }

        save_alert_rules(&rules)?;
        Self::load(console)?;
        let overview = Self::get_overview(console);
        emit_badge_event(app, overview.badge_count);
        Ok(overview)
    }

    pub fn delete_alert_rule<R: Runtime>(
        app: &AppHandle<R>,
        console: &ConsoleStore,
        request: DeleteConsoleAlertRuleRequest,
    ) -> AppResult<ConsoleOverviewResponse> {
        let mut rules = load_alert_rules()?;
        let initial_len = rules.len();
        rules.retain(|rule| rule.id != request.id);
        if rules.len() == initial_len {
            return Err(AppError::NotFound(format!(
                "Regra de alerta '{}' não encontrada",
                request.id
            )));
        }

        save_alert_rules(&rules)?;
        Self::load(console)?;
        let overview = Self::get_overview(console);
        emit_badge_event(app, overview.badge_count);
        Ok(overview)
    }

    pub fn mark_alerts_read<R: Runtime>(
        app: &AppHandle<R>,
        console: &ConsoleStore,
    ) -> AppResult<ConsoleOverviewResponse> {
        save_console_state(&ConsoleState {
            last_alert_read_at: Some(Utc::now()),
        })?;
        Self::load(console)?;
        let overview = Self::get_overview(console);
        emit_badge_event(app, overview.badge_count);
        Ok(overview)
    }

    pub fn clear_logs<R: Runtime>(
        app: &AppHandle<R>,
        console: &ConsoleStore,
    ) -> AppResult<ConsoleOverviewResponse> {
        let logs_dir = WorkspaceService::console_logs_directory()?;
        if logs_dir.exists() {
            fs::remove_dir_all(&logs_dir).map_err(|error| {
                map_io_error(
                    &format!(
                        "Falha ao limpar diretório de logs do console '{}'",
                        logs_dir.display()
                    ),
                    &error,
                )
            })?;
        }
        fs::create_dir_all(&logs_dir).map_err(|error| {
            map_io_error(
                &format!(
                    "Falha ao recriar diretório de logs do console '{}'",
                    logs_dir.display()
                ),
                &error,
            )
        })?;
        save_console_state(&ConsoleState {
            last_alert_read_at: Some(Utc::now()),
        })?;
        Self::load(console)?;
        let overview = Self::get_overview(console);
        emit_badge_event(app, overview.badge_count);
        Ok(overview)
    }
}

fn emit_entry_event<R: Runtime>(app: &AppHandle<R>, entry: &ConsoleLogEntry) {
    let _ = app.emit(CONSOLE_ENTRY_EVENT, entry);
}

fn emit_badge_event<R: Runtime>(app: &AppHandle<R>, badge_count: usize) {
    let _ = app.emit(CONSOLE_BADGE_EVENT, ConsoleBadgeEvent { badge_count });
}

fn ensure_console_layout() -> AppResult<()> {
    let root = WorkspaceService::console_root_directory()?;
    let logs_dir = WorkspaceService::console_logs_directory()?;
    fs::create_dir_all(&root).map_err(|error| {
        map_io_error(
            &format!("Falha ao criar diretório raiz do console '{}'", root.display()),
            &error,
        )
    })?;
    fs::create_dir_all(&logs_dir).map_err(|error| {
        map_io_error(
            &format!(
                "Falha ao criar diretório de logs do console '{}'",
                logs_dir.display()
            ),
            &error,
        )
    })?;
    Ok(())
}

fn load_alert_rules() -> AppResult<Vec<ConsoleAlertRule>> {
    let path = WorkspaceService::console_alerts_path()?;
    if !path.exists() {
        return Ok(Vec::new());
    }

    let contents = fs::read_to_string(&path).map_err(|error| {
        map_io_error(
            &format!("Falha ao ler regras de alerta em '{}'", path.display()),
            &error,
        )
    })?;
    serde_json::from_str::<Vec<ConsoleAlertRule>>(&contents).map_err(|error| {
        map_serde_error(
            &format!(
                "Falha ao desserializar regras de alerta em '{}'",
                path.display()
            ),
            &error,
        )
    })
}

fn save_alert_rules(rules: &[ConsoleAlertRule]) -> AppResult<()> {
    let path = WorkspaceService::console_alerts_path()?;
    let payload = serde_json::to_string_pretty(rules).map_err(|error| {
        map_serde_error("Falha ao serializar regras de alerta do console", &error)
    })?;
    fs::write(&path, payload).map_err(|error| {
        map_io_error(
            &format!("Falha ao salvar regras de alerta em '{}'", path.display()),
            &error,
        )
    })
}

fn load_console_state() -> AppResult<ConsoleState> {
    let path = WorkspaceService::console_state_path()?;
    if !path.exists() {
        return Ok(ConsoleState::default());
    }

    let contents = fs::read_to_string(&path).map_err(|error| {
        map_io_error(
            &format!("Falha ao ler estado do console em '{}'", path.display()),
            &error,
        )
    })?;
    serde_json::from_str::<ConsoleState>(&contents).map_err(|error| {
        map_serde_error(
            &format!("Falha ao desserializar estado do console em '{}'", path.display()),
            &error,
        )
    })
}

fn save_console_state(state: &ConsoleState) -> AppResult<()> {
    let path = WorkspaceService::console_state_path()?;
    let payload = serde_json::to_string_pretty(state)
        .map_err(|error| map_serde_error("Falha ao serializar estado do console", &error))?;
    fs::write(&path, payload).map_err(|error| {
        map_io_error(
            &format!("Falha ao salvar estado do console em '{}'", path.display()),
            &error,
        )
    })
}

fn append_entry_to_disk(entry: &ConsoleLogEntry) -> AppResult<()> {
    let date = entry.timestamp.date_naive();
    let log_file = log_file_path(date)?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_file)
        .map_err(|error| {
            map_io_error(
                &format!("Falha ao abrir arquivo de log '{}'", log_file.display()),
                &error,
            )
        })?;
    let payload = serde_json::to_string(entry)
        .map_err(|error| map_serde_error("Falha ao serializar linha do console", &error))?;
    file.write_all(payload.as_bytes()).map_err(|error| {
        map_io_error(
            &format!("Falha ao escrever log em '{}'", log_file.display()),
            &error,
        )
    })?;
    file.write_all(b"\n").map_err(|error| {
        map_io_error(
            &format!("Falha ao finalizar log em '{}'", log_file.display()),
            &error,
        )
    })?;
    Ok(())
}

fn read_retained_log_entries() -> AppResult<Vec<ConsoleLogEntry>> {
    let mut entries = Vec::new();
    for path in retained_log_paths()? {
        let file = match fs::File::open(&path) {
            Ok(file) => file,
            Err(error) => {
                return Err(map_io_error(
                    &format!("Falha ao abrir logs do console em '{}'", path.display()),
                    &error,
                ));
            }
        };

        for line in BufReader::new(file).lines() {
            let line = line.map_err(|error| {
                map_io_error(
                    &format!("Falha ao ler linha de log em '{}'", path.display()),
                    &error,
                )
            })?;
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }
            let entry = serde_json::from_str::<ConsoleLogEntry>(trimmed).map_err(|error| {
                map_serde_error(
                    &format!(
                        "Falha ao desserializar entrada do console em '{}'",
                        path.display()
                    ),
                    &error,
                )
            })?;
            entries.push(entry);
        }
    }
    Ok(entries)
}

fn retained_log_paths() -> AppResult<Vec<PathBuf>> {
    let logs_dir = WorkspaceService::console_logs_directory()?;
    if !logs_dir.exists() {
        return Ok(Vec::new());
    }

    let mut paths = fs::read_dir(&logs_dir)
        .map_err(|error| {
            map_io_error(
                &format!("Falha ao listar diretório de logs '{}'", logs_dir.display()),
                &error,
            )
        })?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| is_retained_log_path(path))
        .collect::<Vec<_>>();
    paths.sort();
    Ok(paths)
}

fn is_retained_log_path(path: &Path) -> bool {
    path.file_stem()
        .and_then(|stem| stem.to_str())
        .and_then(parse_log_date)
        .is_some_and(|date| date >= retention_cutoff())
        && path.extension().and_then(|ext| ext.to_str()) == Some("jsonl")
}

fn prune_old_log_files() -> AppResult<()> {
    let logs_dir = WorkspaceService::console_logs_directory()?;
    if !logs_dir.exists() {
        return Ok(());
    }

    for entry in fs::read_dir(&logs_dir).map_err(|error| {
        map_io_error(
            &format!("Falha ao listar diretório de logs '{}'", logs_dir.display()),
            &error,
        )
    })? {
        let Ok(entry) = entry else {
            continue;
        };
        let path = entry.path();
        let Some(stem) = path.file_stem().and_then(|stem| stem.to_str()) else {
            continue;
        };
        let Some(date) = parse_log_date(stem) else {
            continue;
        };
        if date >= retention_cutoff() {
            continue;
        }
        fs::remove_file(&path).map_err(|error| {
            map_io_error(
                &format!("Falha ao remover log antigo '{}'", path.display()),
                &error,
            )
        })?;
    }

    Ok(())
}

fn log_file_path(date: NaiveDate) -> AppResult<PathBuf> {
    Ok(WorkspaceService::console_logs_directory()?.join(format!("{date}.jsonl")))
}

fn parse_log_date(value: &str) -> Option<NaiveDate> {
    NaiveDate::parse_from_str(value, "%Y-%m-%d").ok()
}

fn retention_cutoff() -> NaiveDate {
    Utc::now().date_naive() - Duration::days(LOG_RETENTION_DAYS)
}

fn collect_known_plants(entries: &[ConsoleLogEntry]) -> Vec<ConsolePlantOption> {
    let mut by_id = BTreeMap::<String, String>::new();
    for entry in entries {
        let (Some(plant_id), Some(plant_name)) = (&entry.plant_id, &entry.plant_name) else {
            continue;
        };
        by_id.entry(plant_id.clone()).or_insert_with(|| plant_name.clone());
    }
    by_id
        .into_iter()
        .map(|(plant_id, plant_name)| ConsolePlantOption { plant_id, plant_name })
        .collect()
}

fn compute_badge_count(
    entries: &[ConsoleLogEntry],
    rules: &[ConsoleAlertRule],
    last_alert_read_at: Option<&DateTime<Utc>>,
) -> usize {
    entries
        .iter()
        .filter(|entry| {
            last_alert_read_at.is_none_or(|timestamp| entry.timestamp > *timestamp)
                && entry_matches_any_rule(entry, rules)
        })
        .count()
}

fn resolve_log_query_limit(limit: Option<usize>) -> usize {
    limit.unwrap_or(DEFAULT_LOG_QUERY_LIMIT).min(MAX_LOG_QUERY_LIMIT)
}

fn list_recent_logs_from_cache(
    console: &ConsoleStore,
    request: &ListConsoleLogsRequest,
    limit: usize,
) -> Option<Vec<ConsoleLogEntry>> {
    let snapshot = console.snapshot();
    let entries = snapshot
        .recent_entries
        .iter()
        .filter(|entry| matches_log_filters(entry, request))
        .take(limit)
        .cloned()
        .collect::<Vec<_>>();

    if entries.len() == limit || snapshot.recent_entries.len() < MAX_RECENT_ENTRIES {
        return Some(entries);
    }

    None
}

fn entry_matches_any_rule(entry: &ConsoleLogEntry, rules: &[ConsoleAlertRule]) -> bool {
    rules.iter().any(|rule| entry_matches_rule(entry, rule))
}

fn entry_matches_rule(entry: &ConsoleLogEntry, rule: &ConsoleAlertRule) -> bool {
    if !rule.enabled {
        return false;
    }

    if !rule.levels.is_empty() && !rule.levels.contains(&entry.level) {
        return false;
    }

    match &rule.target {
        ConsoleAlertTarget::App => entry.plant_id.is_none(),
        ConsoleAlertTarget::AllPlants => entry.plant_id.is_some(),
        ConsoleAlertTarget::SelectedPlants { plant_ids } => entry
            .plant_id
            .as_ref()
            .is_some_and(|plant_id| plant_ids.contains(plant_id)),
    }
}

fn matches_log_filters(entry: &ConsoleLogEntry, request: &ListConsoleLogsRequest) -> bool {
    if !request.levels.is_empty() && !request.levels.contains(&entry.level) {
        return false;
    }

    if let Some(source_scope) = request.source_scope {
        if entry.source_scope != source_scope {
            return false;
        }
    }

    if let Some(plant_id) = request.plant_id.as_deref() {
        if entry.plant_id.as_deref() != Some(plant_id) {
            return false;
        }
    }

    if let Some(search) = request.search.as_deref().map(str::trim).filter(|value| !value.is_empty())
    {
        let search = search.to_lowercase();
        let search_targets = [
            entry.message.to_lowercase(),
            entry.plant_name.clone().unwrap_or_default().to_lowercase(),
            entry.plugin_name.clone().unwrap_or_default().to_lowercase(),
            entry.controller_name.clone().unwrap_or_default().to_lowercase(),
        ];
        if !search_targets.iter().any(|value| value.contains(&search)) {
            return false;
        }
    }

    true
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::models::console::{
        ConsoleAlertTarget, ConsoleLogInput, ConsoleLogLevel, ConsoleSourceKind,
        ConsoleSourceScope, ListConsoleLogsRequest, SaveConsoleAlertRuleRequest,
    };
    use crate::core::services::workspace::test_workspace_root;

    fn reset_console_workspace() {
        let root = test_workspace_root().join("console");
        let _ = fs::remove_dir_all(root);
    }

    fn build_entry(
        console: &ConsoleStore,
        message: &str,
        level: ConsoleLogLevel,
        plant_id: Option<&str>,
        plant_name: Option<&str>,
    ) -> ConsoleLogEntry {
        ConsoleService::append_log::<tauri::Wry>(
            None,
            console,
            ConsoleLogInput {
                level,
                message: message.to_string(),
                source_scope: if plant_id.is_some() {
                    ConsoleSourceScope::Plant
                } else {
                    ConsoleSourceScope::App
                },
                source_kind: ConsoleSourceKind::Backend,
                plant_id: plant_id.map(str::to_string),
                plant_name: plant_name.map(str::to_string),
                runtime_id: None,
                plugin_id: None,
                plugin_name: None,
                controller_id: None,
                controller_name: None,
                details: None,
            },
        )
        .unwrap()
    }

    #[test]
    fn append_persists_and_lists_logs() {
        reset_console_workspace();
        let console = ConsoleStore::new();
        ConsoleService::load(&console).unwrap();

        build_entry(&console, "erro backend", ConsoleLogLevel::Error, None, None);
        build_entry(
            &console,
            "warning planta",
            ConsoleLogLevel::Warning,
            Some("plant_1"),
            Some("Planta 1"),
        );

        let logs = ConsoleService::list_logs(&console, ListConsoleLogsRequest::default()).unwrap();
        assert_eq!(logs.len(), 2);
        assert_eq!(logs[0].message, "warning planta");
        assert_eq!(logs[1].message, "erro backend");
    }

    #[test]
    fn badge_counts_matching_logs_only_once() {
        reset_console_workspace();
        let console = ConsoleStore::new();
        ConsoleService::load(&console).unwrap();

        build_entry(
            &console,
            "error planta",
            ConsoleLogLevel::Error,
            Some("plant_1"),
            Some("Planta 1"),
        );
        build_entry(
            &console,
            "warning planta",
            ConsoleLogLevel::Warning,
            Some("plant_1"),
            Some("Planta 1"),
        );

        let app = tauri::test::mock_app();
        ConsoleService::save_alert_rule(
            app.handle(),
            &console,
            SaveConsoleAlertRuleRequest {
                id: None,
                name: "Erros da planta".into(),
                enabled: true,
                levels: vec![ConsoleLogLevel::Error],
                target: ConsoleAlertTarget::SelectedPlants {
                    plant_ids: vec!["plant_1".into()],
                },
            },
        )
        .unwrap();

        let overview = ConsoleService::get_overview(&console);
        assert_eq!(overview.badge_count, 1);
    }

    #[test]
    fn mark_alerts_read_resets_badge() {
        reset_console_workspace();
        let console = ConsoleStore::new();
        ConsoleService::load(&console).unwrap();
        let app = tauri::test::mock_app();

        ConsoleService::save_alert_rule(
            app.handle(),
            &console,
            SaveConsoleAlertRuleRequest {
                id: None,
                name: "Todos erros app".into(),
                enabled: true,
                levels: vec![ConsoleLogLevel::Error],
                target: ConsoleAlertTarget::App,
            },
        )
        .unwrap();

        build_entry(&console, "erro app", ConsoleLogLevel::Error, None, None);
        assert_eq!(ConsoleService::get_overview(&console).badge_count, 1);

        ConsoleService::mark_alerts_read(app.handle(), &console).unwrap();
        assert_eq!(ConsoleService::get_overview(&console).badge_count, 0);
    }
}
