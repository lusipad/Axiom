const memory = new Map<string, string>();

export function readStorage(key: string): string | null {
  try {
    if (typeof window.localStorage?.getItem === "function") {
      return window.localStorage.getItem(key);
    }
  } catch {
    // fall through to memory
  }
  return memory.get(key) ?? null;
}

export function writeStorage(key: string, value: string): void {
  memory.set(key, value);
  try {
    if (typeof window.localStorage?.setItem === "function") {
      window.localStorage.setItem(key, value);
    }
  } catch {
    // memory only
  }
}

export function clearStorage(): void {
  memory.clear();
  try {
    const store = window.localStorage;
    if (store && typeof store.removeItem === "function") {
      for (const key of Object.keys(store)) store.removeItem(key);
    }
  } catch {
    // noop
  }
}
