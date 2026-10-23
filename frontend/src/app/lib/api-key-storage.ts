const API_KEY_STORAGE_KEY = "X-API-KEY";
const LEGACY_API_KEY_KEYS = ["groq_api_key", "api_key"] as const;
const REMEMBER_KEY_STORAGE_KEY = "remember_api_key";

type StorageMode = "session" | "local";

function resolveStorage(mode: StorageMode): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return mode === "session" ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
}

function readFromStorage(storage: Storage | null): string {
  if (!storage) {
    return "";
  }
  const direct = storage.getItem(API_KEY_STORAGE_KEY);
  if (direct && direct.trim()) {
    return direct.trim();
  }
  for (const key of LEGACY_API_KEY_KEYS) {
    const value = storage.getItem(key);
    if (value && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function removeLegacyKeys(storage: Storage | null): void {
  if (!storage) {
    return;
  }
  for (const key of LEGACY_API_KEY_KEYS) {
    storage.removeItem(key);
  }
}

function clearStorageKey(storage: Storage | null): void {
  if (!storage) {
    return;
  }
  storage.removeItem(API_KEY_STORAGE_KEY);
  removeLegacyKeys(storage);
}

export function getStoredApiKey(): string {
  const sessionKey = readFromStorage(resolveStorage("session"));
  if (sessionKey) {
    return sessionKey;
  }
  return readFromStorage(resolveStorage("local"));
}

export function getRememberApiKeyPreference(): boolean {
  const localStorage = resolveStorage("local");
  const sessionStorage = resolveStorage("session");
  if (localStorage) {
    const remember = localStorage.getItem(REMEMBER_KEY_STORAGE_KEY);
    if (remember === "1") {
      return true;
    }
    if (remember === "0") {
      return false;
    }
  }

  const localKey = readFromStorage(localStorage);
  const sessionKey = readFromStorage(sessionStorage);
  return Boolean(localKey && !sessionKey);
}

export function saveApiKey(key: string, remember: boolean): void {
  const trimmed = key.trim();
  const localStorage = resolveStorage("local");
  const sessionStorage = resolveStorage("session");

  if (!trimmed) {
    clearStorageKey(localStorage);
    clearStorageKey(sessionStorage);
    localStorage?.removeItem(REMEMBER_KEY_STORAGE_KEY);
    return;
  }

  if (remember && localStorage) {
    localStorage.setItem(API_KEY_STORAGE_KEY, trimmed);
    removeLegacyKeys(localStorage);
    localStorage.setItem(REMEMBER_KEY_STORAGE_KEY, "1");
    clearStorageKey(sessionStorage);
    return;
  }

  if (sessionStorage) {
    sessionStorage.setItem(API_KEY_STORAGE_KEY, trimmed);
    removeLegacyKeys(sessionStorage);
  }
  clearStorageKey(localStorage);
  localStorage?.setItem(REMEMBER_KEY_STORAGE_KEY, "0");
}
