use crate::core::models::console::{ConsoleAlertRule, ConsoleLogEntry, ConsolePlantOption, ConsoleState};
use chrono::{DateTime, Utc};
use parking_lot::RwLock;
use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, Ordering};

pub const MAX_RECENT_ENTRIES: usize = 2_000;

#[derive(Debug, Default)]
pub struct ConsoleStore {
    state: RwLock<ConsoleStoreState>,
    badge_recompute_generation: AtomicU64,
}

#[derive(Debug, Default, Clone)]
pub struct ConsoleStoreState {
    pub recent_entries: VecDeque<ConsoleLogEntry>,
    pub rules: Vec<ConsoleAlertRule>,
    pub known_plants: Vec<ConsolePlantOption>,
    pub console_state: ConsoleState,
    pub badge_count: usize,
}

#[derive(Debug, Clone)]
pub struct ConsoleBadgeStateSnapshot {
    pub rules: Vec<ConsoleAlertRule>,
    pub last_alert_read_at: Option<DateTime<Utc>>,
    pub badge_count: usize,
}

impl ConsoleStore {
    pub fn new() -> Self {
        Self {
            state: RwLock::new(ConsoleStoreState::default()),
            badge_recompute_generation: AtomicU64::new(0),
        }
    }

    pub fn snapshot(&self) -> ConsoleStoreState {
        self.state.read().clone()
    }

    pub fn replace_all(&self, next: ConsoleStoreState) {
        *self.state.write() = next;
    }

    pub fn append_recent_entries(&self, entries: &[ConsoleLogEntry]) {
        let mut state = self.state.write();
        for entry in entries {
            state.recent_entries.push_front(entry.clone());
            while state.recent_entries.len() > MAX_RECENT_ENTRIES {
                state.recent_entries.pop_back();
            }

            let Some(plant_id) = entry.plant_id.as_ref() else {
                continue;
            };
            let Some(plant_name) = entry.plant_name.as_ref() else {
                continue;
            };

            let exists = state
                .known_plants
                .iter()
                .any(|known| known.plant_id == *plant_id);
            if !exists {
                state.known_plants.push(ConsolePlantOption {
                    plant_id: plant_id.clone(),
                    plant_name: plant_name.clone(),
                });
            }
        }

        state
            .known_plants
            .sort_by(|left, right| left.plant_name.cmp(&right.plant_name));
    }

    pub fn increment_badge_count_by(&self, count: usize) -> usize {
        if count == 0 {
            return self.state.read().badge_count;
        }

        let mut state = self.state.write();
        state.badge_count = state.badge_count.saturating_add(count);
        state.badge_count
    }

    pub fn set_badge_count(&self, badge_count: usize) -> usize {
        let mut state = self.state.write();
        state.badge_count = badge_count;
        state.badge_count
    }

    pub fn next_badge_recompute_generation(&self) -> u64 {
        self.badge_recompute_generation.fetch_add(1, Ordering::Relaxed) + 1
    }

    pub fn current_badge_recompute_generation(&self) -> u64 {
        self.badge_recompute_generation.load(Ordering::Relaxed)
    }

    pub fn badge_state_snapshot(&self) -> ConsoleBadgeStateSnapshot {
        let state = self.state.read();
        ConsoleBadgeStateSnapshot {
            rules: state.rules.clone(),
            last_alert_read_at: state.console_state.last_alert_read_at,
            badge_count: state.badge_count,
        }
    }
}
