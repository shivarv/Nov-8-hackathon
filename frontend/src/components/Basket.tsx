import { useEffect, useId, useMemo, useRef, useState } from "react";
import { formatPrice } from "../api";
import { DELIVERY_FEE_CENTS, FREE_DELIVERY_CENTS, upcomingSlots, usualSlot } from "../delivery";
import type { Cart, FeedItem, Shopper } from "../types";
import { ProductImage } from "./ProductImage";
import { ReadyToAdd } from "./ReadyToAdd";

interface Props {
  cart: Cart | null;
  shopper: Shopper;
  /** Not in the basket yet but goes with it (the top of the pairs shelf). */
  forgot: FeedItem[];
  loading: boolean;
  onSetQuantity: (productId: number, quantity: number) => void;
  onCheckout: () => Promise<{ item_count: number } | null>;
  /** Jump to the shopper's next trip (their usual gap later). */
  onNextVisit: () => Promise<void>;
}

interface Placed {
  count: number;
  total: string;
  slot: string;
}

// Static icons hoisted out of render.
const BAG_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
    <path d="M5 8h14l-1.2 11.1a2 2 0 0 1-2 1.9H8.2a2 2 0 0 1-2-1.9L5 8Z" strokeLinejoin="round" />
    <path d="M9 10V7a3 3 0 0 1 6 0v3" strokeLinecap="round" />
  </svg>
);

const CHEVRON_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
    <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/**
 * The basket lives in the top bar as a pill showing the running total.
 * Closed by default; opening it drops down the full list, a "forgot something?"
 * nudge from what goes with the basket, and checkout.
 */
export function Basket({
  cart,
  shopper,
  forgot,
  loading,
  onSetQuantity,
  onCheckout,
  onNextVisit,
}: Props) {
  const [open, setOpen] = useState(false);
  const [placed, setPlaced] = useState<Placed | null>(null);
  const slots = useMemo(() => upcomingSlots(), []);
  const [slotKey, setSlotKey] = useState(
    () => usualSlot(slots, shopper.usual_day, shopper.usual_hour).key,
  );
  const rootRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  const items = cart?.items ?? [];
  const count = cart?.item_count ?? 0;
  const subtotalCents = cart?.subtotal_cents ?? 0;
  const freeDelivery = subtotalCents >= FREE_DELIVERY_CENTS;
  const feeCents = count === 0 || freeDelivery ? 0 : DELIVERY_FEE_CENTS;
  const total = formatPrice(subtotalCents);
  const slot = slots.find((s) => s.key === slotKey) ?? slots[0];

  // Close on outside click or Escape, only while open.
  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        toggleRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function checkout() {
    const result = await onCheckout();
    if (result) {
      setPlaced({
        count: result.item_count,
        total: formatPrice(subtotalCents + feeCents),
        slot: `${slot.day}, ${slot.label}`,
      });
    }
  }

  function toggle() {
    setOpen((o) => !o);
    setPlaced(null);
  }

  const itemsLabel = count === 1 ? "1 item" : `${count} items`;

  return (
    <div ref={rootRef} className={`basket${open ? " is-open" : ""}`}>
      <button
        ref={toggleRef}
        className="basket-toggle"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`Basket, ${itemsLabel}, ${total}`}
      >
        <span className="basket-icon">
          {BAG_ICON}
          {count > 0 ? (
            // Keyed on count so the badge pops each time something is added.
            <span key={count} className="basket-count">
              {count}
            </span>
          ) : null}
        </span>
        <span className="basket-total">{total}</span>
        {forgot.length > 0 && !open ? <span className="basket-ready-dot" aria-hidden /> : null}
        <span className="basket-chevron">{CHEVRON_ICON}</span>
      </button>

      {open ? (
        <div id={panelId} className="basket-panel" role="dialog" aria-label="Your basket">
          <header className="basket-head">
            <div>
              <h2>Your basket</h2>
              <p>{itemsLabel}</p>
            </div>
            <button
              className="basket-close"
              onClick={() => setOpen(false)}
              aria-label="Close basket"
            >
              ×
            </button>
          </header>

          <div className="basket-body">
            {placed ? (
              <div className="basket-placed">
                <strong>Order placed</strong>
                <span>
                  {placed.count} items · {placed.total} · arriving {placed.slot}
                </span>
                <button className="basket-next" onClick={() => void onNextVisit()}>
                  Skip to your next trip (+{shopper.usual_gap_days} days) →
                </button>
              </div>
            ) : null}

            {items.length === 0 ? (
              <p className="basket-empty">
                Your basket is empty. Tap <strong>Add</strong> on anything in the store.
              </p>
            ) : (
              <ul className="basket-lines">
                {items.map(({ product, quantity }) => (
                  <li key={product.id} className="basket-line">
                    <ProductImage product={product} size="thumb" />
                    <div className="basket-line-info">
                      <span className="basket-line-name">{product.name}</span>
                      <span className="basket-line-unit">
                        {formatPrice(product.price_cents)} each
                      </span>
                    </div>
                    <span className="basket-line-total">
                      {formatPrice(product.price_cents * quantity)}
                    </span>
                    <div
                      className="basket-stepper"
                      role="group"
                      aria-label={`${product.name} quantity`}
                    >
                      <button
                        onClick={() => onSetQuantity(product.id, quantity - 1)}
                        aria-label={quantity === 1 ? `Remove ${product.name}` : `Remove one ${product.name}`}
                      >
                        −
                      </button>
                      <span aria-live="polite">{quantity}</span>
                      <button
                        onClick={() => onSetQuantity(product.id, quantity + 1)}
                        disabled={quantity >= 99}
                        aria-label={`Add one more ${product.name}`}
                      >
                        +
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}

            {count > 0 ? (
              <ReadyToAdd items={forgot} loading={loading} onAdd={(id) => onSetQuantity(id, 1)} />
            ) : null}
          </div>

          <footer className="basket-foot">
            {count > 0 ? (
              <div className="free-delivery">
                <span className="free-delivery-bar" aria-hidden>
                  <span
                    style={{ width: `${Math.min(100, (100 * subtotalCents) / FREE_DELIVERY_CENTS)}%` }}
                  />
                </span>
                <span>
                  {freeDelivery
                    ? "Free delivery unlocked"
                    : `Add ${formatPrice(FREE_DELIVERY_CENTS - subtotalCents)} for free delivery`}
                </span>
              </div>
            ) : null}
            <label className="slot">
              <span>Delivery</span>
              <select value={slot.key} onChange={(e) => setSlotKey(e.target.value)}>
                {slots.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.day}, {s.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="basket-row">
              <span>Subtotal</span>
              <span>{total}</span>
            </div>
            <div className="basket-row">
              <span>Delivery</span>
              <span>{count === 0 ? "—" : feeCents ? formatPrice(feeCents) : "Free"}</span>
            </div>
            <div className="basket-subtotal">
              <span>Total</span>
              <strong>{formatPrice(subtotalCents + feeCents)}</strong>
            </div>
            <button className="checkout" disabled={count === 0} onClick={checkout}>
              Check out
            </button>
            <p className="basket-note">Prices are estimates for this demo.</p>
          </footer>
        </div>
      ) : null}
    </div>
  );
}
