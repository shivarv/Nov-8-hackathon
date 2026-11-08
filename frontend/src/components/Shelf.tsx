import type { FeedSection } from "../types";
import { AisleSign } from "./AisleSign";
import { ProductTile } from "./ProductTile";

interface Props {
  section: FeedSection;
  quantityOf: (productId: number) => number;
  onSetQuantity: (productId: number, quantity: number) => void;
  onAddAll: (productIds: number[]) => void;
  /** Called when something is added from this shelf, before the cart changes. */
  onAddFrom: (section: FeedSection) => void;
}

/** One stop on the walk: its aisle sign and a shelf of products you scroll sideways. */
export function Shelf({ section, quantityOf, onSetQuantity, onAddAll, onAddFrom }: Props) {
  const notYet = section.items.filter((i) => quantityOf(i.product.id) === 0);
  const canAddAll = section.confidence === "sure" && notYet.length > 1;

  const setQuantity = (productId: number, quantity: number) => {
    if (quantity > quantityOf(productId)) onAddFrom(section);
    onSetQuantity(productId, quantity);
  };

  return (
    <section className={`stop stop--${section.confidence} stop--${section.kind}`}>
      <AisleSign
        section={section}
        action={
          canAddAll ? (
            <button
              className="add-all"
              onClick={() => {
                onAddFrom(section);
                onAddAll(notYet.map((i) => i.product.id));
              }}
            >
              {section.kind === "regulars" ? "Reorder all" : "Add all"} {notYet.length}
            </button>
          ) : undefined
        }
      />
      <div className="shelf" role="list" aria-label={section.title}>
        {section.items.map((item) => (
          <div role="listitem" key={item.product.id}>
            <ProductTile
              item={item}
              quantity={quantityOf(item.product.id)}
              onSetQuantity={setQuantity}
            />
          </div>
        ))}
      </div>
      <div className="shelf-edge" aria-hidden />
    </section>
  );
}
