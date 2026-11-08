import { formatPrice } from "../api";
import type { Product } from "../types";
import { ProductImage } from "./ProductImage";
import { QuantityControl } from "./QuantityControl";

interface Props {
  product: Product;
  quantity: number;
  onSetQuantity: (productId: number, quantity: number) => void;
  reason?: string;
}

export function ProductCard({ product, quantity, onSetQuantity, reason }: Props) {
  return (
    <article className="product-card">
      <ProductImage product={product} size="card" />
      <div className="product-price">{formatPrice(product.price_cents)}</div>
      <h3 className="product-name">{product.name}</h3>
      <div className="product-aisle">{reason ?? product.aisle}</div>
      <QuantityControl
        quantity={quantity}
        label={product.name}
        onChange={(q) => onSetQuantity(product.id, q)}
      />
    </article>
  );
}
