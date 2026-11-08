import { createContext } from "react";

/**
 * Products in the shopper's real next order, while the demo reveals it (else null).
 * Tiles read it to mark what the shopper really bought.
 */
export const RevealContext = createContext<Set<number> | null>(null);
