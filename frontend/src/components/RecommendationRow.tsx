import type { Recommendation } from "../types";
import { ProductCard } from "./ProductCard";

interface Props {
  title: string;
  recs: Recommendation[];
  quantityOf: (productId: number) => number;
  onSetQuantity: (productId: number, quantity: number) => void;
  onDismiss?: () => void;
}

/** Horizontal strip of recommended products, each showing why it was suggested. */
export function RecommendationRow({ title, recs, quantityOf, onSetQuantity, onDismiss }: Props) {
  if (recs.length === 0) return null;
  return (
    <section className="rec-row">
      <header>
        <div>
          <div className="eyebrow">✨ Frequently bought together</div>
          <h2>{title}</h2>
        </div>
        {onDismiss && (
          <button className="btn-ghost" onClick={onDismiss} aria-label="Dismiss suggestions">
            ✕
          </button>
        )}
      </header>
      <div className="rec-scroller">
        {recs.map((r) => (
          <ProductCard
            key={r.product.id}
            product={r.product}
            reason={r.source === "bought_together" ? "Bought together" : "Popular"}
            quantity={quantityOf(r.product.id)}
            onSetQuantity={onSetQuantity}
          />
        ))}
      </div>
    </section>
  );
}
