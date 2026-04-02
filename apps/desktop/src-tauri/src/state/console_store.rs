use crate::core::models::console::{ConsoleAlertRule, ConsoleLogEntry, ConsolePlantOption, ConsoleState};
use parking_lot::RwLock;
use std::collections::VecDeque;

pub const MAX_RECENT_ENTRIES: usize = 2_000;

#[derive(Debug, Default)]
pub struct ConsoleStore {
    state: RwLock<ConsoleStoreState>,
}

#[derive(Debug, Default, Clone)]
pub struct ConsoleStoreState {
    pub recent_entries: VecDeque<ConsoleLogEntry>,
    pub rules: Vec<ConsoleAlertRule>,
    pub known_plants: Vec<ConsolePlantOption>,
    pub console_state: ConsoleState,
    pub badge_count: usize,
}

impl ConsoleStore {
    pub fn new() -> Self {
        Self {
            state: RwLock::new(ConsoleStoreState::default()),
        }
    }

    pub fn snapshot(&self) -> ConsoleStoreState {
        self.state.read().clone()
    }

    pub fn replace_all(&self, next: ConsoleStoreState) {
        *self.state.write() = next;
    }

    pub fn push_recent_entry(&self, entry: ConsoleLogEntry) {
        let mut state = self.state.write();
        state.recent_entries.push_front(entry);
        while state.recent_entries.len() > MAX_RECENT_ENTRIES {
            state.recent_entries.pop_back();
        }
    }

    pub fn set_badge_count(&self, badge_count: usize) {
        self.state.write().badge_count = badge_count;
    }

    pub fn register_known_plant(&self, plant: ConsolePlantOption) {
        let mut state = self.state.write();
        if state.known_plants.iter().any(|entry| entry.plant_id == plant.plant_id) {
            return;
        }
        state.known_plants.push(plant);
        state
            .known_plants
            .sort_by(|left, right| left.plant_name.cmp(&right.plant_name));
    }
}
