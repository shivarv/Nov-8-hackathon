import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Cart, SearchResult } from "../types";

/**
 * Search results for `query`, as this shopper with this cart.
 *
 * A new query replaces everything. A cart change only refreshes the "for you"
 * strip: the results the shopper is adding from stay where they are.
 */
export function useSearch(shopperId: number, query: string, cart: Cart | null) {
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shownQuery = useRef<string | null>(null);

  const cartId = cart?.id ?? null;
  const contents = cart ? cart.items.map((i) => i.product.id).join(",") : "";

  useEffect(() => {
    if (!query) {
      shownQuery.current = null;
      setResult(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    api
      .search(shopperId, query, cartId, { signal: controller.signal })
      .then((next) => {
        const sameQuery = shownQuery.current === query;
        shownQuery.current = query;
        setResult((prev) =>
          sameQuery && prev ? { ...prev, for_you: next.for_you, for_you_title: next.for_you_title } : next,
        );
        setError(null);
      })
      .catch((e) => {
        if (e?.name !== "AbortError") setError(String(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [shopperId, query, cartId, contents]);

  return { result, loading, error };
}
