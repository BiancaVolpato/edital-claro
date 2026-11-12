"use client";

import { useCallback, useSyncExternalStore } from "react";

const noopSubscribe = () => () => {};

/** False during server rendering and hydration, true afterwards (no effect needed). */
export function useIsClient(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}

const LOCAL_EVENT = "edital-claro:local-storage";

/** A JSON value in localStorage, safe for server rendering. Failures (private mode,
 *  blocked storage) fall back to the default and keep the change for this visit only. */
export function useLocalStorage<T>(key: string, fallback: T): [T, (value: T) => void] {
  const subscribe = useCallback((notify: () => void) => {
    window.addEventListener("storage", notify);
    window.addEventListener(LOCAL_EVENT, notify);
    return () => {
      window.removeEventListener("storage", notify);
      window.removeEventListener(LOCAL_EVENT, notify);
    };
  }, []);
  const raw = useSyncExternalStore(
    subscribe,
    () => {
      try {
        return localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    () => null,
  );
  let value = fallback;
  if (raw !== null) {
    try {
      value = JSON.parse(raw) as T;
    } catch {
      value = fallback;
    }
  }
  const set = useCallback(
    (next: T) => {
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // storage unavailable
      }
      window.dispatchEvent(new Event(LOCAL_EVENT));
    },
    [key],
  );
  return [value, set];
}
