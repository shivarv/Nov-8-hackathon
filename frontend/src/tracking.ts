import { createContext } from "react";
import type { FeedItem } from "./types";

/**
 * For new shoppers only: every product tile reports how long it is on screen
 * (`track` is its ref) and can be opened for a closer look (`open`).
 * Null for demo shoppers, so their tiles behave as before.
 */
export const TrackingContext = createContext<{
  track: (productId: number) => (el: HTMLElement | null) => void;
  open: (item: FeedItem) => void;
} | null>(null);
