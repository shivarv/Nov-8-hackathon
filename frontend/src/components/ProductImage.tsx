import { useState } from "react";
import type { Product } from "../types";

interface Props {
  product: Product;
  size: "card" | "thumb";
}

/** Product photo, or the department emoji when there is none or it fails to load. */
export function ProductImage({ product, size }: Props) {
  const [failed, setFailed] = useState(false);
  const emojiClass = size === "card" ? "product-emoji" : "cart-emoji";

  if (!product.image_url || failed) {
    return (
      <div className={emojiClass} aria-hidden>
        {product.emoji}
      </div>
    );
  }
  return (
    <img
      className={size === "card" ? "product-photo" : "cart-photo"}
      src={product.image_url}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}
