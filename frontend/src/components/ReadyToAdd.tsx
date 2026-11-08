import { formatPrice } from "../api";
import type { FeedItem } from "../types";
import { ProductImage } from "./ProductImage";

interface Props {
  items: FeedItem[];
  loading: boolean;
  onAdd: (productId: number) => void;
}

/**
 * In the basket, before checkout: "Forgot something?", the items BehaviorGPT ranks
 * highest for going with this basket, each one tap away. Hidden when there are none.
 */
export function ReadyToAdd({ items, loading, onAdd }: Props) {
  if (items.length === 0) return null;
  return (
    <section className={`ready${loading ? " is-busy" : ""}`} aria-label="Forgot something?">
      <header className="ready-head">
        <h2>Forgot something?</h2>
        <p>What BehaviorGPT ranks highest for going with this basket</p>
      </header>
      <ul className="ready-list">
        {items.map(({ product, reason }) => (
          <li key={product.id} className="ready-row">
            <ProductImage product={product} size="thumb" />
            <div className="ready-info">
              <span className="ready-name">{product.name}</span>
              <span className="ready-reason">{reason}</span>
            </div>
            <span className="ready-price">{formatPrice(product.price_cents)}</span>
            <button
              className="ready-add"
              onClick={() => onAdd(product.id)}
              aria-label={`Add ${product.name} to basket`}
            >
              Add
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
