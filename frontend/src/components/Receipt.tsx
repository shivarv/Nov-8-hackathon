import { useState } from "react";
import { formatPrice } from "../api";
import type { Cart, FeedItem, Shopper } from "../types";
import { ReadyToAdd } from "./ReadyToAdd";

interface Props {
  cart: Cart | null;
  shopper: Shopper;
  ready: FeedItem[];
  loading: boolean;
  onSetQuantity: (productId: number, quantity: number) => void;
  onCheckout: () => Promise<{ item_count: number } | null>;
}

/** The basket, printed as a receipt that grows line by line as you shop. */
export function Receipt({ cart, shopper, ready, loading, onSetQuantity, onCheckout }: Props) {
  const [open, setOpen] = useState(false); // mobile: receipt sheet expanded
  const [placed, setPlaced] = useState<string | null>(null);
  const items = cart?.items ?? [];
  const count = cart?.item_count ?? 0;
  const total = formatPrice(cart?.subtotal_cents ?? 0);

  async function checkout() {
    const result = await onCheckout();
    if (result) setPlaced(`Order placed · ${result.item_count} items · ${total}`);
    setOpen(false);
  }

  return (
    <aside className={`receipt-wrap${open ? " is-open" : ""}`} aria-label="Your basket">
      <button
        className="receipt-bar"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span>{count === 1 ? "1 item" : `${count} items`}</span>
        <span className="receipt-bar-total">{total}</span>
        <span className="receipt-bar-hint">
          {open ? "Hide basket" : ready.length ? `View basket · ${ready.length} ready` : "View basket"}
        </span>
      </button>

      <div className="receipt">
        <div className="receipt-head">
          <strong>BASKET</strong>
          <span>Shopper {shopper.id}</span>
          <span>{shopper.label}</span>
        </div>

        {placed && <p className="receipt-placed">{placed}</p>}

        {items.length === 0 ? (
          <p className="receipt-empty">
            Nothing yet. Tap Add on anything in the store and it prints here.
          </p>
        ) : (
          <ol className="receipt-lines">
            {items.map(({ product, quantity }) => (
              <li key={product.id} className="receipt-line">
                <span className="receipt-name">{product.name}</span>
                <span className="receipt-dots" aria-hidden />
                <span className="receipt-amount">
                  {formatPrice(product.price_cents * quantity)}
                </span>
                <span className="receipt-qty">
                  <button
                    onClick={() => onSetQuantity(product.id, quantity - 1)}
                    aria-label={`Remove one ${product.name}`}
                  >
                    −
                  </button>
                  {quantity} × {formatPrice(product.price_cents)}
                  <button
                    onClick={() => onSetQuantity(product.id, quantity + 1)}
                    aria-label={`Add one more ${product.name}`}
                  >
                    +
                  </button>
                </span>
              </li>
            ))}
          </ol>
        )}

        <div className="receipt-total">
          <span>Subtotal</span>
          <span>{total}</span>
        </div>
        <button className="checkout" disabled={count === 0} onClick={checkout}>
          Check out
        </button>
        <p className="receipt-foot">Prices are estimates for this demo.</p>
      </div>

      <ReadyToAdd items={ready} loading={loading} onAdd={(id) => onSetQuantity(id, 1)} />
    </aside>
  );
}
