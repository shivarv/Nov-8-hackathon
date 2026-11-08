import { useEffect, useState } from "react";
import { api } from "../api";
import type { Replay } from "../types";

/** The shopper's real next order and scoreboard, fetched only while `on`. */
export function useReplay(shopperId: number, on: boolean, visit: number) {
  const [replay, setReplay] = useState<Replay | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!on) return;
    let cancelled = false;
    setError(null);
    api
      .replay(shopperId)
      .then((r) => !cancelled && setReplay(r))
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [shopperId, on, visit]);

  return { replay: on ? replay : null, error: on ? error : null };
}
