import { type CSSProperties, useContext } from "react";
import { formatPrice } from "../api";
import type { FeedItem } from "../types";
import { RevealContext } from "../reveal";
import { TrackingContext } from "../tracking";
import { ProductImage } from "./ProductImage";

interface Props {
  item: FeedItem;
  quantity: number;
  onSetQuantity: (productId: number, quantity: number) => void;
}

const STICKER: Partial<Record<FeedItem["tag"], string>> = {
  new: "New to you",
  due: "Due",
  foryou: "For you",
};

/** One product on the shelf: photo, shelf-edge price tag, why it's here, one-tap add. */
export function ProductTile({ item, quantity, onSetQuantity }: Props) {
  const { product, tag, reason, confidence } = item;
  const inBasket = quantity > 0;
  const sticker = STICKER[tag];
  const boughtNext = useContext(RevealContext)?.has(product.id) ?? false;
  // New shoppers: time on screen is recorded, and the photo / name open a closer look.
  const tracking = useContext(TrackingContext);
  const open = tracking ? () => tracking.open(item) : undefined;

  return (
    <article
      ref={tracking?.track(product.id)}
      className={`tile tile--${tag}${inBasket ? " is-in-basket" : ""}${boughtNext ? " is-bought-next" : ""}`}
      style={{ "--fit": confidence } as CSSProperties}
    >
      <div
        className={`tile-photo${open ? " is-openable" : ""}`}
        {...(open && {
          role: "button",
          tabIndex: 0,
          "aria-label": `Look closer at ${product.name}`,
          onClick: open,
          onKeyDown: (e: React.KeyboardEvent) => e.key === "Enter" && open(),
        })}
      >
        <ProductImage product={product} size="card" />
        {sticker && <span className="tile-sticker">{sticker}</span>}
        {boughtNext && <span className="tile-real">Bought next</span>}
        {inBasket && (
          <span className="tile-check" aria-hidden>
            ✓
          </span>
        )}
      </div>

      <div className="tile-tag">
        <span className="tile-price">{formatPrice(product.price_cents)}</span>
      </div>

      <h3 className={`tile-name${open ? " is-openable" : ""}`} onClick={open}>
        {product.name}
      </h3>
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
