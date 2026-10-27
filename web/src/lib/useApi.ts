import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "./api";

export interface Loaded<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  /** Fetch again, keeping what's shown until the answer is in. */
  reload: () => void;
  /** Replace the data in place, e.g. with what a POST answered. */
  setData: (next: T | null | ((prev: T | null) => T | null)) => void;
}

interface State<T> { key: string | null; data: T | null; error: Error | null; loading: boolean }

/**
 * Load something for `key` (null: nothing yet). A new key aborts the old request and shows nothing of the
 * old key's data, so a slow answer for a filter you already left can never land on the new one. Unmounting
 * aborts too. `load` may change every render; only `key` and reload() start a new request.
 */
export function useLoad<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>): Loaded<T> {
  const [state, setState] = useState<State<T>>({ key: null, data: null, error: null, loading: key != null });
  const [reloads, setReloads] = useState(0);
  const loader = useRef(load);
  loader.current = load;
  const keyRef = useRef(key);
  keyRef.current = key;

  useEffect(() => {
    if (key == null) {
      setState({ key, data: null, error: null, loading: false });
      return;
    }
    const ctrl = new AbortController();
    setState((s) => (s.key === key ? { ...s, error: null, loading: true } : { key, data: null, error: null, loading: true }));
    loader.current(ctrl.signal).then(
      (data) => { if (!ctrl.signal.aborted) setState({ key, data, error: null, loading: false }); },
      (error: unknown) => {
        if (!ctrl.signal.aborted) setState((s) => ({ ...s, key, error: error instanceof Error ? error : new Error(String(error)), loading: false }));
      },
    );
    return () => ctrl.abort();
  }, [key, reloads]);

  const reload = useCallback(() => setReloads((n) => n + 1), []);
  const setData = useCallback((next: T | null | ((prev: T | null) => T | null)) => setState((s) => {
    const prev = s.key === keyRef.current ? s.data : null;
    return { key: keyRef.current, error: null, loading: false,
      data: typeof next === "function" ? (next as (prev: T | null) => T | null)(prev) : next };
  }), []);

  const current = state.key === key;
  return {
    data: current ? state.data : null,
    error: current ? state.error : null,
    loading: key != null && (!current || state.loading),
    reload,
    setData,
  };
}

/** GET `path` from the API (null: don't load yet), with the abort-on-change rules of useLoad. */
export function useApi<T>(path: string | null): Loaded<T> {
  return useLoad<T>(path, (signal) => apiFetch<T>(path!, { signal }));
}
