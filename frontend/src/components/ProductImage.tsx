import { useState } from "react";
import type { Product } from "../types";

interface Props {
  product: Product;
  size?: "card" | "thumb";
}

/** Product photo, falling back to the emoji when there is none or it fails to load. */
export function ProductImage({ product, size = "card" }: Props) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const url = product.image_url;

  if (url && url !== failedUrl) {
    return (
      <div className={`product-img ${size}`}>
        <img src={url} alt="" loading="lazy" onError={() => setFailedUrl(url)} />
      </div>
    );
  }
  return (
    <div className={`product-img ${size} is-emoji`} aria-hidden>
      {product.emoji}
    </div>
  );
}
