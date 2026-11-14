import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
  silentReload: () => void;
}

/** Runs `fn` when deps change; ignores stale responses. Supports silent background refreshes without spinner flash. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[], enabled = true): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [tick, setTick] = useState(0);
  const [silentTick, setSilentTick] = useState(0);
  const seq = useRef(0);
  const prevSilent = useRef(0);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const isSilent = silentTick !== prevSilent.current;
    prevSilent.current = silentTick;
    const my = ++seq.current;
    if (!isSilent) {
      setLoading(true);
      setError(null);
    }
    fn().then(
      (d) => {
        if (my === seq.current) {
          setData(d);
          setError(null);
          setLoading(false);
        }
      },
      (e: unknown) => {
        if (my === seq.current && !isSilent) {
          setError(e instanceof Error ? e : new Error(String(e)));
          setData(null);
          setLoading(false);
        }
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, silentTick, enabled]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const silentReload = useCallback(() => setSilentTick((t) => t + 1), []);
  return { data, error, loading, reload, silentReload };
}
