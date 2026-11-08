import { useCallback, useEffect, useRef } from "react";
import { api } from "../api";
import type { Pattern, Signal } from "../types";

const VISIBLE = 0.6; // share of a tile that must be on screen to count as looked at
const FLUSH_MS = 5000;

/**
 * Records how a new shopper browses: how long each product tile is on screen while the
 * tab is active, and products clicked open for a closer look (and for how long). Signals
 * are batched to the server every few seconds and when the page is hidden; each reply is
 * their pattern as it stands. `shopperId` null turns tracking off.
 */
export function useBrowsingTracker(shopperId: number | null, onPattern: (p: Pattern) => void) {
  const pending = useRef<Map<string, Signal>>(new Map());
  const since = useRef<Map<number, number>>(new Map()); // product -> on screen since (ms)
  const onScreen = useRef<Set<number>>(new Set());
  const observer = useRef<IntersectionObserver | null>(null);
  const elements = useRef<Map<Element, number>>(new Map());
  const refs = useRef<Map<number, (el: HTMLElement | null) => void>>(new Map());
  const patternCb = useRef(onPattern);
  patternCb.current = onPattern;

  const add = useCallback((productId: number, kind: Signal["kind"], ms: number) => {
    const key = `${kind}:${productId}`;
    const prev = pending.current.get(key);
    pending.current.set(key, {
      product_id: productId,
      kind,
      dwell_ms: Math.round((prev?.dwell_ms ?? 0) + ms),
    });
  }, []);

  const stop = useCallback(
    (productId: number, now = performance.now()) => {
      const start = since.current.get(productId);
      if (start == null) return;
      since.current.delete(productId);
      add(productId, "view", now - start);
    },
    [add],
  );

  const take = useCallback(() => {
    // Cut running looks so a long stare is reported without waiting for scroll-away.
    const now = performance.now();
    for (const id of [...since.current.keys()]) {
      stop(id, now);
      if (document.visibilityState === "visible") since.current.set(id, now);
    }
    const out = [...pending.current.values()];
    pending.current.clear();
    return out;
  }, [stop]);

  const flush = useCallback(() => {
    if (shopperId == null) return;
    const batch = take();
    if (batch.length)
      api
        .recordSignals(shopperId, batch)
        .then((p) => patternCb.current(p))
        .catch(() => {
          /* best effort: a lost batch of browsing signals isn't worth an error */
        });
  }, [shopperId, take]);

  useEffect(() => {
    if (shopperId == null) return;
    observer.current = new IntersectionObserver(
      (entries) => {
        const now = performance.now();
        for (const entry of entries) {
          const id = elements.current.get(entry.target);
          if (id == null) continue;
          if (entry.isIntersecting && entry.intersectionRatio >= VISIBLE) {
            onScreen.current.add(id);
            if (document.visibilityState === "visible" && !since.current.has(id))
              since.current.set(id, now);
          } else {
            onScreen.current.delete(id);
            stop(id, now);
          }
        }
      },
      { threshold: [0, VISIBLE] },
    );
    for (const el of elements.current.keys()) observer.current.observe(el);

    const beacon = () => {
      const batch = take();
      if (batch.length) api.beaconSignals(shopperId, batch);
    };
    const onVisibility = () => {
      const now = performance.now();
      if (document.visibilityState === "visible") {
        for (const id of onScreen.current) since.current.set(id, now);
      } else {
        for (const id of [...since.current.keys()]) stop(id, now);
        beacon();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", beacon);
    const timer = window.setInterval(flush, FLUSH_MS);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", beacon);
      observer.current?.disconnect();
      observer.current = null;
      flush();
    };
  }, [shopperId, flush, stop, take]);

  /** Ref callback for a product tile (stable per product). */
  const track = useCallback(
    (productId: number) => {
      let ref = refs.current.get(productId);
      if (!ref) {
        let current: HTMLElement | null = null;
        ref = (el: HTMLElement | null) => {
          if (current) {
            observer.current?.unobserve(current);
            elements.current.delete(current);
            onScreen.current.delete(productId);
            stop(productId);
          }
          current = el;
          if (el) {
            elements.current.set(el, productId);
            observer.current?.observe(el);
          }
        };
        refs.current.set(productId, ref);
      }
      return ref;
    },
    [stop],
  );

  /** A closer look at a product was closed after `ms`: reported right away. */
  const opened = useCallback(
    (productId: number, ms: number) => {
      add(productId, "open", ms);
      flush();
    },
    [add, flush],
  );

  return { track, opened };
}
