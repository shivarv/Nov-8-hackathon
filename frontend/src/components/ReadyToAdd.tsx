import { formatPrice } from "../api";
import type { FeedItem } from "../types";
import { ProductImage } from "./ProductImage";

interface Props {
  items: FeedItem[];
  loading: boolean;
  onAdd: (productId: number) => void;
}

/**
 * Under the receipt: the shopper's own items BehaviorGPT is surest belong in this
 * basket, each one tap away. Hidden when the model has nothing it's sure about.
 */
export function ReadyToAdd({ items, loading, onAdd }: Props) {
  if (items.length === 0) return null;
  return (
    <section className={`ready${loading ? " is-busy" : ""}`} aria-label="Ready to add">
      <header className="ready-head">
        <h2>Ready to add</h2>
        <p>Your items that BehaviorGPT ranks in its top 20 of the whole store for this basket</p>
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
