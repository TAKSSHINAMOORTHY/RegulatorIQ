/**
 * On-device local storage manager for history and user preferences.
 * Safe against unavailable localStorage (private browsing, cookies blocked) and adheres to opt-out policy.
 */

export interface SavedConversation {
  id: string;
  timestamp: number;
  question: string;
  summary: string;
}

export interface UserPreferences {
  theme: "light" | "dark" | "system";
  reduceMotionOverride: boolean;
  includeSuperseded: boolean;
  lastDocTypeFilter?: string;
  historyOptOut: boolean;
}

const STORAGE_KEY_HISTORY = "regulatoriq_history_v1";
const STORAGE_KEY_PREFS = "regulatoriq_prefs_v1";
const MAX_HISTORY_ITEMS = 30;

export const defaultPreferences: UserPreferences = {
  theme: "system",
  reduceMotionOverride: false,
  includeSuperseded: false,
  historyOptOut: false,
};

function isLocalStorageAvailable(): boolean {
  try {
    if (typeof window === "undefined" || !window.localStorage) {
      return false;
    }
    const testKey = "__test_storage__";
    window.localStorage.setItem(testKey, "1");
    window.localStorage.removeItem(testKey);
    return true;
  } catch {
    return false;
  }
}

export function loadPreferences(): UserPreferences {
  if (!isLocalStorageAvailable()) {
    return { ...defaultPreferences };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY_PREFS);
    if (!raw) return { ...defaultPreferences };
    const parsed = JSON.parse(raw);
    return { ...defaultPreferences, ...parsed };
  } catch {
    return { ...defaultPreferences };
  }
}

export function savePreferences(prefs: Partial<UserPreferences>): UserPreferences {
  const current = loadPreferences();
  const updated = { ...current, ...prefs };
  if (isLocalStorageAvailable()) {
    try {
      window.localStorage.setItem(STORAGE_KEY_PREFS, JSON.stringify(updated));
    } catch {
      // Storage quota or restriction, ignore gracefully
    }
  }
  return updated;
}

export function loadHistory(): SavedConversation[] {
  const prefs = loadPreferences();
  if (prefs.historyOptOut || !isLocalStorageAvailable()) {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY_HISTORY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list.slice(0, MAX_HISTORY_ITEMS) : [];
  } catch {
    return [];
  }
}

export function saveConversation(item: SavedConversation): void {
  const prefs = loadPreferences();
  if (prefs.historyOptOut || !isLocalStorageAvailable()) {
    return;
  }
  try {
    const current = loadHistory();
    // Filter out duplicate id if already exists, prepend new item
    const filtered = current.filter((c) => c.id !== item.id);
    const updated = [item, ...filtered].slice(0, MAX_HISTORY_ITEMS);
    window.localStorage.setItem(STORAGE_KEY_HISTORY, JSON.stringify(updated));
  } catch {
    // Storage quota or error, ignore
  }
}

export function clearHistory(): void {
  if (!isLocalStorageAvailable()) return;
  try {
    window.localStorage.removeItem(STORAGE_KEY_HISTORY);
  } catch {
    // Graceful catch
  }
}
