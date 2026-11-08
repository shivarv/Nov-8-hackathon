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
    <aside className="cart-panel" id="cart">
      <h2>
        Your cart <span className="count-pill">{cart?.item_count ?? 0}</span>
      </h2>

      {message && <p className="notice">{message}</p>}

      {items.length === 0 ? (
        <div className="cart-empty">
          <div className="cart-empty-icon" aria-hidden>
            🛒
          </div>
          <p>Your cart is empty.</p>
          <p className="muted small">Add an item and we'll suggest what usually goes with it.</p>
        </div>
      ) : (
        <ul className="cart-items">
          {items.map(({ product, quantity }) => (
            <li key={product.id}>
              <ProductImage key={product.id} product={product} size="thumb" />
              <div className="cart-item-info">
                <div className="cart-item-name">{product.name}</div>
                <div className="muted small">{formatPrice(product.price_cents * quantity)}</div>
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
          <h3>{items.length ? "✨ Complete your cart" : "🔥 Popular right now"}</h3>
          <ul>
            {recs.map((r) => (
              <li key={r.product.id}>
                <ProductImage key={r.product.id} product={r.product} size="thumb" />
                <div className="cart-item-info">
                  <div className="cart-item-name">{r.product.name}</div>
                  <div className="muted small">
                    {formatPrice(r.product.price_cents)} · {r.reason}
                  </div>
                </div>
                <button
                  className="btn-plus"
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
          {items.length > 0 && <span className="btn-primary-total">{formatPrice(cart!.subtotal_cents)}</span>}
        </button>
      </footer>
    </aside>
  );
}
