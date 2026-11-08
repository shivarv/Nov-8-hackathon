import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Cart } from "../types";

const storageKey = (shopperId: number) => `cartId:${shopperId}`;

function readStoredId(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storeId(key: string, id: string) {
  try {
    localStorage.setItem(key, id);
  } catch {
    /* storage unavailable: cart lives for this tab only */
  }
}

/** Loads (or creates) this shopper's cart and exposes mutations. One cart per shopper. */
export function useCart(shopperId: number | null) {
  const [cart, setCart] = useState<Cart | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCart(null);
    if (shopperId == null) return;
    let cancelled = false;
    const key = storageKey(shopperId);
    (async () => {
      const stored = readStoredId(key);
      let next: Cart | null = null;
      if (stored) {
        try {
          next = await api.getCart(stored);
        } catch (e) {
          if (!(e instanceof ApiError && e.status === 404)) throw e;
        }
      }
      next ??= await api.createCart();
      storeId(key, next.id);
      if (!cancelled) setCart(next);
    })().catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [shopperId]);

  const setQuantity = useCallback(
    async (productId: number, quantity: number) => {
      if (!cart) return;
      try {
        setCart(await api.setQuantity(cart.id, productId, quantity));
      } catch (e) {
        setError(String(e));
      }
    },
    [cart],
  );

  /** Add several products one after another (e.g. "Add all"), then publish the final cart once. */
  const addMany = useCallback(
    async (productIds: number[]) => {
      if (!cart) return;
      let next = cart;
      try {
        for (const id of productIds) {
          if (next.items.some((i) => i.product.id === id)) continue;
          next = await api.setQuantity(cart.id, id, 1);
        }
        setCart(next);
      } catch (e) {
        setError(String(e));
      }
    },
    [cart],
  );

  const checkout = useCallback(async () => {
    if (!cart) return null;
    const result = await api.checkout(cart.id);
    setCart(await api.getCart(cart.id));
    return result;
  }, [cart]);

  const quantityOf = useCallback(
    (productId: number) => cart?.items.find((i) => i.product.id === productId)?.quantity ?? 0,
    [cart],
  );

  return { cart, error, setQuantity, addMany, checkout, quantityOf };
}
