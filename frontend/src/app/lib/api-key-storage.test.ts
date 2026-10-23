import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getRememberApiKeyPreference,
  getStoredApiKey,
  saveApiKey,
} from "@/app/lib/api-key-storage";

describe("api-key-storage", () => {
  function createMemoryStorage(): Storage {
    const data = new Map<string, string>();
    return {
      get length() {
        return data.size;
      },
      clear() {
        data.clear();
      },
      getItem(key: string) {
        return data.has(key) ? data.get(key)! : null;
      },
      key(index: number) {
        return Array.from(data.keys())[index] ?? null;
      },
      removeItem(key: string) {
        data.delete(key);
      },
      setItem(key: string, value: string) {
        data.set(key, String(value));
      },
    };
  }

  beforeEach(() => {
    vi.stubGlobal("localStorage", createMemoryStorage());
    vi.stubGlobal("sessionStorage", createMemoryStorage());
    localStorage.clear();
    sessionStorage.clear();
  });

  it("prefers session storage over local storage", () => {
    localStorage.setItem("X-API-KEY", "local-key");
    sessionStorage.setItem("X-API-KEY", "session-key");

    expect(getStoredApiKey()).toBe("session-key");
  });

  it("stores key in session storage by default", () => {
    saveApiKey("test-session-key", false);

    expect(sessionStorage.getItem("X-API-KEY")).toBe("test-session-key");
    expect(localStorage.getItem("X-API-KEY")).toBeNull();
    expect(getRememberApiKeyPreference()).toBe(false);
  });

  it("stores key in local storage when remember mode is enabled", () => {
    saveApiKey("test-local-key", true);

    expect(localStorage.getItem("X-API-KEY")).toBe("test-local-key");
    expect(sessionStorage.getItem("X-API-KEY")).toBeNull();
    expect(getRememberApiKeyPreference()).toBe(true);
  });
});
