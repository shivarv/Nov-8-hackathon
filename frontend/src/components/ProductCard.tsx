import type { Product } from "../types";
import { Price } from "./Price";
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
    <article className={quantity > 0 ? "product-card in-cart" : "product-card"}>
      <div className="product-media">
        <ProductImage key={product.id} product={product} />
        <div className="card-action">
          <QuantityControl
            quantity={quantity}
            label={product.name}
            onChange={(q) => onSetQuantity(product.id, q)}
          />
        </div>
      </div>
      <div className="product-body">
        <Price cents={product.price_cents} />
        <h3 className="product-name" title={product.name}>
          {product.name}
        </h3>
        {reason ? (
          <div className="reason-badge" title={reason}>
            {reason}
          </div>
        ) : (
          <div className="product-aisle">{product.aisle}</div>
        )}
      </div>
    </article>
  );
}
