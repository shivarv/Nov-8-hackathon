import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Cart } from "../types";

const STORAGE_KEY = "cartId";

function readStoredId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeId(id: string) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* storage unavailable: cart lives for this tab only */
  }
}

/** Loads (or creates) the shopper's cart and exposes mutations. */
export function useCart() {
  const [cart, setCart] = useState<Cart | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = readStoredId();
      let next: Cart | null = null;
      if (stored) {
        try {
          next = await api.getCart(stored);
        } catch (e) {
          if (!(e instanceof ApiError && e.status === 404)) throw e;
        }
      }
      next ??= await api.createCart();
      storeId(next.id);
      if (!cancelled) setCart(next);
    })().catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, []);

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

  return { cart, error, setQuantity, checkout, quantityOf };
}
