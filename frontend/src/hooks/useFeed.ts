import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Cart, Feed, FeedSection } from "../types";

/**
 * Keep items the shopper just added on the shelf where they tapped them.
 *
 * The server leaves products already in the cart out of the feed. Without this,
 * a tile would vanish under the shopper's finger; instead it stays put (shown as
 * "in basket") while the rest of the shelf restocks around it.
 */
function keepAddedInPlace(prev: Feed | null, next: Feed, inCart: Set<number>): Feed {
  if (!prev) return next;
  const before = new Map(prev.sections.map((s) => [s.key, s]));
  const sections: FeedSection[] = next.sections.map((section) => {
    const old = before.get(section.key);
    if (!old) return section;
    const stay = old.items.filter((i) => inCart.has(i.product.id));
    const fresh = section.items.filter((i) => !stay.some((s) => s.product.id === i.product.id));
    return { ...section, items: [...stay, ...fresh] };
  });

  // A shelf the shopper just added from can drop out of the new feed (a small aisle
  // with too few new items left). Keep it where it was, so the shelf under their
  // finger, and the suggestions anchored to it, don't vanish.
  const shown = new Set(sections.flatMap((s) => s.items.map((i) => i.product.id)));
  const keys = new Set(sections.map((s) => s.key));
  prev.sections.forEach((old, index) => {
    const isPairs = old.kind === "pairs" || old.kind === "mission";
    if (keys.has(old.key) || isPairs || !old.items.some((i) => inCart.has(i.product.id))) return;
    const items = old.items.filter((i) => inCart.has(i.product.id) || !shown.has(i.product.id));
    // insert after the nearest earlier section that is still in the feed
    let at = 0;
    for (let j = index - 1; j >= 0; j--) {
      const k = sections.findIndex((s) => s.key === prev.sections[j].key);
      if (k !== -1) {
        at = k + 1;
        break;
      }
    }
    sections.splice(at, 0, { ...old, items });
    keys.add(old.key);
  });
  return { ...next, sections };
}

/** The shopper's feed, refetched whenever the cart's contents change. */
export function useFeed(shopperId: number | null, cart: Cart | null) {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const feedRef = useRef<Feed | null>(null);

  const cartId = cart?.id ?? null;
  const contents = cart ? cart.items.map((i) => i.product.id).join(",") : "";

  useEffect(() => {
    feedRef.current = null;
    setFeed(null);
  }, [shopperId]);

  useEffect(() => {
    if (shopperId == null || cartId == null) return;
    const controller = new AbortController();
    const inCart = new Set(contents ? contents.split(",").map(Number) : []);
    setLoading(true);
    api
      .feed(shopperId, cartId, { signal: controller.signal })
      .then((next) => {
        const merged = keepAddedInPlace(feedRef.current, next, inCart);
        feedRef.current = merged;
        setFeed(merged);
        setError(null);
      })
      .catch((e) => {
        if (e?.name !== "AbortError") setError(String(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [shopperId, cartId, contents]);

  return { feed, loading, error };
}
