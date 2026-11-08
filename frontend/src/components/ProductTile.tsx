import type { CSSProperties } from "react";
import { formatPrice } from "../api";
import type { FeedItem } from "../types";
import { ProductImage } from "./ProductImage";

interface Props {
  item: FeedItem;
  quantity: number;
  onSetQuantity: (productId: number, quantity: number) => void;
}

const STICKER: Partial<Record<FeedItem["tag"], string>> = {
  new: "New to you",
  due: "Due",
};

/** One product on the shelf: photo, shelf-edge price tag, why it's here, one-tap add. */
export function ProductTile({ item, quantity, onSetQuantity }: Props) {
  const { product, tag, reason, confidence } = item;
  const inBasket = quantity > 0;
  const sticker = STICKER[tag];

  return (
    <article
      className={`tile tile--${tag}${inBasket ? " is-in-basket" : ""}`}
      style={{ "--fit": confidence } as CSSProperties}
    >
      <div className="tile-photo">
        <ProductImage product={product} size="card" />
        {sticker && <span className="tile-sticker">{sticker}</span>}
        {inBasket && (
          <span className="tile-check" aria-hidden>
            ✓
          </span>
        )}
      </div>

      <div className="tile-tag">
        <span className="tile-price">{formatPrice(product.price_cents)}</span>
      </div>

      <h3 className="tile-name">{product.name}</h3>
      <p className="tile-reason">
        <span className="tile-fit" aria-hidden />
        {reason}
      </p>

      {inBasket ? (
        <div className="tile-stepper" role="group" aria-label={`${product.name} quantity`}>
          <button
            onClick={() => onSetQuantity(product.id, quantity - 1)}
            aria-label={`Remove one ${product.name}`}
          >
            −
          </button>
          <span aria-live="polite">{quantity} in basket</span>
          <button
            onClick={() => onSetQuantity(product.id, quantity + 1)}
            disabled={quantity >= 99}
            aria-label={`Add one more ${product.name}`}
          >
            +
          </button>
        </div>
      ) : (
        <button
          className="tile-add"
          onClick={() => onSetQuantity(product.id, 1)}
          aria-label={`Add ${product.name} to basket`}
        >
          Add
        </button>
      )}
    </article>
  );
}
