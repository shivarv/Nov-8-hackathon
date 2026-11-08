import { useState } from "react";
import { useSearch } from "../hooks/useSearch";
import type { Cart, FeedItem } from "../types";
import { PlanView } from "./PlanView";
import { ProductTile } from "./ProductTile";

/** Reads like a request to plan ("tacos for 4 friday"), not a product name ("milk"). */
const isRequest = (q: string) => q.trim().split(/\s+/).length >= 3;

interface Props {
  shopperId: number;
  query: string;
  cart: Cart | null;
  quantityOf: (productId: number) => number;
  onSetQuantity: (productId: number, quantity: number) => void;
  onSetMany: (entries: [number, number][]) => Promise<void>;
  /** Leave the search and go back to the store. */
  onBack: () => void;
}

function Tiles({
  items,
  layout,
  quantityOf,
  onSetQuantity,
}: {
  items: FeedItem[];
  layout: "row" | "grid";
  quantityOf: (productId: number) => number;
  onSetQuantity: (productId: number, quantity: number) => void;
}) {
  return (
    <div className={layout === "row" ? "shelf" : "results-grid"} role="list">
      {items.map((item) => (
        <div role="listitem" key={item.product.id}>
          <ProductTile
            item={item}
            quantity={quantityOf(item.product.id)}
            onSetQuantity={onSetQuantity}
          />
        </div>
      ))}
    </div>
  );
}

/** The search tab: their usual picks for the query, the results, and what fits the basket. */
export function SearchView({
  shopperId,
  query,
  cart,
  quantityOf,
  onSetQuantity,
  onSetMany,
  onBack,
}: Props) {
  const { result, loading, error } = useSearch(shopperId, query, cart);
  const [generic, setGeneric] = useState(false);
  // The query a basket is being planned for; a new query closes the plan.
  const [planFor, setPlanFor] = useState<string | null>(null);
  const tiles = { quantityOf, onSetQuantity };

  if (planFor === query) {
    return (
      <PlanView
        shopperId={shopperId}
        request={query}
        cart={cart}
        quantityOf={quantityOf}
        onSetQuantity={onSetQuantity}
        onSetMany={onSetMany}
        onClose={() => setPlanFor(null)}
      />
    );
  }

  const planBanner = isRequest(query) ? (
    <button className="plan-banner" onClick={() => setPlanFor(query)}>
      <span className="plan-banner-text">
        <strong>Build me a basket for “{query}”</strong>
        <span>Claude plans it, BehaviorGPT picks your products · about 15 seconds</span>
      </span>
      <span className="plan-banner-go" aria-hidden>
        →
      </span>
    </button>
  ) : null;

  const back = (
    <button className="back-link" onClick={onBack}>
      ← Back to the store
    </button>
  );
  if (error) return <p className="notice">Search failed: {error}</p>;
  if (!result || result.query !== query) {
    return (
      <>
        {back}
        {planBanner}
        <div className="search-loading" aria-busy="true">
          Searching for “{query}”…
        </div>
      </>
    );
  }

  const results = generic ? result.generic : result.results;
  const personal = result.model === "behaviorgpt";

  return (
    <div className={`search${loading ? " is-busy" : ""}`}>
      {back}
      {planBanner}
      {result.yours.length > 0 && (
        <section className="search-block">
          <header className="search-block-head">
            <h2 className="search-heading">Your usual “{query}”</h2>
            <p className="search-sub">From your past orders, best match first</p>
          </header>
          <Tiles items={result.yours} layout="row" {...tiles} />
        </section>
      )}

      <section className="search-block">
        <header className="search-block-head search-block-head--split">
          <div>
            <h2 className="search-heading">
              {results.length} results for “{query}”
            </h2>
            <p className="search-sub">
              {!personal
                ? "Name matches, most popular first"
                : generic
                  ? "Ranked the same for every shopper"
                  : "Ranked for you by BehaviorGPT, from your orders and basket"}
            </p>
          </div>
          {personal && (
            <div className="segmented" role="group" aria-label="Ranking">
              <button aria-pressed={!generic} onClick={() => setGeneric(false)}>
                For you
              </button>
              <button aria-pressed={generic} onClick={() => setGeneric(true)}>
                Everyone
              </button>
            </div>
          )}
        </header>
        {results.length ? (
          <Tiles items={results} layout="grid" {...tiles} />
        ) : (
          <p className="search-sub">Nothing found. Try another word.</p>
        )}
      </section>

      {result.for_you.length > 0 && (
        <section className="search-block search-block--for-you">
          <header className="search-block-head">
            <h2 className="search-heading">{result.for_you_title}</h2>
            <p className="search-sub">
              From your past purchases{cart?.items.length ? " and what's in your basket" : ""}
            </p>
          </header>
          <Tiles items={result.for_you} layout="row" {...tiles} />
        </section>
      )}
    </div>
  );
}
