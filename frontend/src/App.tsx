import { useEffect, useState } from "react";
import { api } from "./api";
import { Basket } from "./components/Basket";
import { Shelf } from "./components/Shelf";
import { ShopperPicker } from "./components/ShopperPicker";
import { useCart } from "./hooks/useCart";
import { useFeed } from "./hooks/useFeed";
import type { FeedSection, Shopper } from "./types";

const isPairs = (s: FeedSection) => s.kind === "pairs" || s.kind === "mission";

/**
 * Put the "goes with your basket" section right under the shelf the shopper just
 * added from, so suggestions open where they are looking. Without an anchor (first
 * load, an add from the basket) the server's order is kept.
 */
function placePairs(sections: FeedSection[], anchor: string | null): FeedSection[] {
  const pairs = sections.find(isPairs);
  if (!pairs || !anchor) return sections;
  const rest = sections.filter((s) => s !== pairs);
  const at = rest.findIndex((s) => s.key === anchor);
  if (at === -1) return sections;
  return [...rest.slice(0, at + 1), pairs, ...rest.slice(at + 1)];
}

const SHOPPER_KEY = "shopper";

function readShopper(): Shopper | null {
  try {
    const raw = sessionStorage.getItem(SHOPPER_KEY);
    return raw ? (JSON.parse(raw) as Shopper) : null;
  } catch {
    return null;
  }
}

function storeShopper(shopper: Shopper | null) {
  try {
    if (shopper) sessionStorage.setItem(SHOPPER_KEY, JSON.stringify(shopper));
    else sessionStorage.removeItem(SHOPPER_KEY);
  } catch {
    /* storage unavailable: the choice lasts until reload */
  }
}

export default function App() {
  const [shopper, setShopper] = useState<Shopper | null>(readShopper);
  const { cart, error: cartError, setQuantity, addMany, checkout, quantityOf } = useCart(
    shopper?.id ?? null,
  );
  const { feed, loading, error: feedError } = useFeed(shopper?.id ?? null, cart);
  // Key of the shelf the last add came from; the pairs section opens under it.
  const [pairsAnchor, setPairsAnchor] = useState<string | null>(null);

  useEffect(() => storeShopper(shopper), [shopper]);
  useEffect(() => setPairsAnchor(null), [shopper?.id]);

  // Adding from the pairs section itself keeps the anchor, so the refreshed
  // suggestions replace it in place instead of jumping back up the page.
  const addFrom = (section: FeedSection) => {
    if (!isPairs(section)) setPairsAnchor(section.key);
  };

  // Deep link for demos: ?shopper=<id> opens the store as that shopper.
  useEffect(() => {
    const wanted = Number(new URLSearchParams(window.location.search).get("shopper"));
    if (!wanted || shopper?.id === wanted) return;
    api
      .shoppers()
      .then((all) => {
        const match = all.find((s) => s.id === wanted);
        if (match) setShopper(match);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!shopper) return <ShopperPicker onPick={setShopper} />;

  const error = cartError ?? feedError;

  return (
    <div className="store">
      <header className="topbar">
        <span className="logo">Basket</span>
        <button className="who" onClick={() => setShopper(null)}>
          <span className="who-label">{shopper.label}</span>
          <span className="who-meta">Shopper {shopper.id} · switch</span>
        </button>
        {feed && (
          <span className={`model-badge${loading ? " is-busy" : ""}`}>
            {loading
              ? "Restocking for your basket…"
              : feed.model === "behaviorgpt"
                ? "Arranged by BehaviorGPT"
                : "Arranged from past baskets"}
          </span>
        )}
        <Basket
          cart={cart}
          ready={feed?.ready_to_add ?? []}
          loading={loading}
          onSetQuantity={setQuantity}
          onCheckout={checkout}
        />
      </header>

      <main className="walk" aria-busy={loading}>
        <p className="walk-intro">
          Your store for today, in the order you usually shop. Scroll to walk the aisles.
        </p>

        {error && <p className="notice">Something went wrong: {error}</p>}

        {!feed &&
          !error &&
          Array.from({ length: 3 }, (_, i) => <div key={i} className="stop is-placeholder" />)}

        {feed &&
          placePairs(feed.sections, pairsAnchor).map((section) => (
            <Shelf
              key={section.key}
              section={section}
              quantityOf={quantityOf}
              onSetQuantity={setQuantity}
              onAddAll={addMany}
              onAddFrom={addFrom}
            />
          ))}

        {feed && <p className="walk-end">That's the whole store. Your basket is up top.</p>}
      </main>
    </div>
  );
}
