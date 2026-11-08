import { useEffect, useState } from "react";
import { api } from "../api";
import type { Cart, ForYou } from "../types";

/**
 * A new shopper's For you tab, fetched while it is shown and refetched when the cart's
 * contents change, after checkout (`refreshKey`), or when their pattern changes.
 */
export function useForYou(
  shopperId: number | null,
  cart: Cart | null,
  active: boolean,
  refreshKey: string,
) {
  const [forYou, setForYou] = useState<ForYou | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cartId = cart?.id ?? null;
  const contents = cart ? cart.items.map((i) => i.product.id).join(",") : "";

  useEffect(() => setForYou(null), [shopperId]);

  useEffect(() => {
    if (shopperId == null || !active) return;
    const controller = new AbortController();
    setLoading(true);
    api
      .forYou(shopperId, cartId, { signal: controller.signal })
      .then((next) => {
        setForYou(next);
        setError(null);
      })
      .catch((e) => {
        if (e?.name !== "AbortError") setError(String(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [shopperId, cartId, contents, active, refreshKey]);

  return { forYou, loading, error };
}
