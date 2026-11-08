import { useEffect, useRef } from "react";
import { formatPrice } from "../api";
import type { FeedItem } from "../types";
import { ProductImage } from "./ProductImage";

interface Props {
  item: FeedItem;
  quantity: number;
  onSetQuantity: (productId: number, quantity: number) => void;
  /** Closed after being open for `ms` (a click and time spent: strong interest). */
  onClose: (ms: number) => void;
}

/** A closer look at one product: big photo, price, where it is, why it's suggested. */
export function ProductPeek({ item, quantity, onSetQuantity, onClose }: Props) {
  const openedAt = useRef(performance.now());
  const close = () => onClose(performance.now() - openedAt.current);
  const { product } = item;
  const organic = product.name.toLowerCase().includes("organic");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="peek-backdrop" onClick={close}>
      <div
        className="peek"
        role="dialog"
        aria-modal="true"
        aria-label={product.name}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="peek-close" onClick={close} aria-label="Close">
          ✕
        </button>
        <div className="peek-photo">
          <ProductImage product={product} size="card" />
        </div>
        <div className="peek-body">
          <p className="peek-where">
            {product.department} · {product.aisle}
          </p>
          <h2 className="peek-name">{product.name}</h2>
          <div className="peek-tags">
            <span className="peek-price">{formatPrice(product.price_cents)}</span>
            {organic && <span className="peek-chip">Organic</span>}
          </div>
          <p className="peek-reason">{item.reason}</p>
          {quantity > 0 ? (
            <div className="peek-stepper">
              <button onClick={() => onSetQuantity(product.id, quantity - 1)} aria-label="One less">
                −
              </button>
              <span>{quantity} in basket</span>
              <button onClick={() => onSetQuantity(product.id, quantity + 1)} aria-label="One more">
                +
              </button>
            </div>
          ) : (
            <button className="peek-add" onClick={() => onSetQuantity(product.id, 1)}>
              Add to basket
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
