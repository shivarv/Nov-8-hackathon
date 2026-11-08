import { formatPrice } from "../api";
import type { Cart, Recommendation } from "../types";
import { ProductImage } from "./ProductImage";
import { QuantityControl } from "./QuantityControl";

interface Props {
  cart: Cart | null;
  recs: Recommendation[];
  onSetQuantity: (productId: number, quantity: number) => void;
  onCheckout: () => void;
  message: string | null;
}

export function CartPanel({ cart, recs, onSetQuantity, onCheckout, message }: Props) {
  const items = cart?.items ?? [];
  return (
    <aside className="cart-panel">
      <h2>
        Your cart <span className="muted">({cart?.item_count ?? 0})</span>
      </h2>

      {message && <p className="notice">{message}</p>}

      {items.length === 0 ? (
        <p className="muted">Your cart is empty. Add something to get suggestions.</p>
      ) : (
        <ul className="cart-items">
          {items.map(({ product, quantity }) => (
            <li key={product.id}>
              <ProductImage product={product} size="thumb" />
              <div className="cart-item-info">
                <div>{product.name}</div>
                <div className="muted">{formatPrice(product.price_cents * quantity)}</div>
              </div>
              <QuantityControl
                quantity={quantity}
                label={product.name}
                onChange={(q) => onSetQuantity(product.id, q)}
              />
            </li>
          ))}
        </ul>
      )}

      {recs.length > 0 && (
        <div className="cart-recs">
          <h3>{items.length ? "Complete your cart" : "Popular right now"}</h3>
          <ul>
            {recs.map((r) => (
              <li key={r.product.id}>
                <ProductImage product={r.product} size="thumb" />
                <div className="cart-item-info">
                  <div>{r.product.name}</div>
                  <div className="muted small">{r.reason}</div>
                </div>
                <button
                  className="btn-add small"
                  onClick={() => onSetQuantity(r.product.id, 1)}
                  aria-label={`Add ${r.product.name}`}
                >
                  +
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <footer className="cart-footer">
        <div className="subtotal">
          <span>Subtotal</span>
          <strong>{formatPrice(cart?.subtotal_cents ?? 0)}</strong>
        </div>
        <button className="btn-primary" disabled={items.length === 0} onClick={onCheckout}>
          Checkout
        </button>
      </footer>
    </aside>
  );
}
