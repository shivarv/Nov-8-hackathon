import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Basket } from "./components/Basket";
import { ForYouView } from "./components/ForYouView";
import { ProductPeek } from "./components/ProductPeek";
import { ReplayPanel } from "./components/ReplayPanel";
import { SearchBox } from "./components/SearchBox";
import { SearchView } from "./components/SearchView";
import { Shelf } from "./components/Shelf";
import { ShopperPicker } from "./components/ShopperPicker";
import { useCart } from "./hooks/useCart";
import { useBrowsingTracker } from "./hooks/useBrowsingTracker";
import { useFeed } from "./hooks/useFeed";
import { useForYou } from "./hooks/useForYou";
import { useReplay } from "./hooks/useReplay";
import { RevealContext } from "./reveal";
import { TrackingContext } from "./tracking";
import type { Feed, FeedItem, FeedSection, Pattern, Shopper } from "./types";

/**
 * Searches worth offering: what the shopper's regulars are ("Organic Large Brown Eggs"
 * -> "eggs"), most bought first. The last real word of a name is usually the food.
 */
function searchIdeas(feed: Feed | null): string[] {
  const regulars = feed?.sections.find((s) => s.kind === "regulars")?.items ?? [];
  const words = regulars
    .map((i) => i.product.name.toLowerCase().match(/[a-z]{3,}/g)?.at(-1))
    .filter((w): w is string => Boolean(w));
  return [...new Set(words)].slice(0, 8);
}

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
  const { cart, error: cartError, setQuantity, addMany, setMany, checkout, quantityOf } = useCart(
    shopper?.id ?? null,
  );
  // Bumped when the shopper's history or clock changes (checkout, next trip).
  const [visit, setVisit] = useState(0);
  const { feed, loading, error: feedError } = useFeed(shopper?.id ?? null, cart, visit);
  const [reveal, setReveal] = useState(false);
  const { replay, error: replayError } = useReplay(shopper?.id ?? 0, reveal && shopper != null, visit);
  const revealed = useMemo(() => (replay ? new Set(replay.items) : null), [replay]);
  // Key of the shelf the last add came from; the pairs section opens under it.
  const [pairsAnchor, setPairsAnchor] = useState<string | null>(null);
  // The search being shown; empty shows the store.
  const [query, setQuery] = useState("");
  const ideas = useMemo(() => searchIdeas(feed), [feed]);
  // "Forgot something?" in the basket: the top of the shelf that goes with the basket.
  const forgot = useMemo(
    () => (feed?.sections.find(isPairs)?.items ?? []).filter((i) => quantityOf(i.product.id) === 0).slice(0, 4),
    [feed, quantityOf],
  );

  // New shoppers: what they look at, click and buy is recorded and builds their For you tab.
  const newId = shopper?.is_new ? shopper.id : null;
  const [tab, setTab] = useState<"store" | "foryou">("store");
  const [livePattern, setLivePattern] = useState<Pattern | null>(null);
  const tracker = useBrowsingTracker(newId, setLivePattern);
  const [peek, setPeek] = useState<FeedItem | null>(null);
  // Refresh For you after checkout / next visit, and when their pattern changes.
  const patternKey = livePattern
    ? `${livePattern.enough}|${livePattern.tags.map((t) => t.key + t.strength).join(",")}`
    : "";
  const { forYou, loading: forYouLoading, error: forYouError } = useForYou(
    newId,
    cart,
    tab === "foryou",
    `${visit}|${patternKey}`,
  );
  const tracking = useMemo(
    () => (newId == null ? null : { track: tracker.track, open: setPeek }),
    [newId, tracker.track],
  );

  useEffect(() => storeShopper(shopper), [shopper]);
  useEffect(() => {
    setPairsAnchor(null);
    setQuery("");
    setReveal(false);
    // Deep link for demos: ?tab=foryou opens a new shopper on their For you tab.
    setTab(new URLSearchParams(window.location.search).get("tab") === "foryou" ? "foryou" : "store");
    setLivePattern(null);
    setPeek(null);
  }, [shopper?.id]);

  const checkoutAndRecord = async () => {
    const result = await checkout();
    if (result) setVisit((v) => v + 1);
    return result;
  };

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
  // The newest view of who they are: their entry's label once it has been generated.
  const current = forYou?.shopper ?? feed?.shopper ?? shopper;

  return (
    <div className="store">
      <header className="topbar">
        <span className="logo">Better Basket</span>
        <button className="who" onClick={() => setShopper(null)}>
          <span className="who-label">
            {current.label}
            {current.is_new && (
              <span className={`who-new${current.has_entry ? " has-entry" : ""}`}>
                {current.has_entry ? "your entry" : "new"}
              </span>
            )}
          </span>
          <span className="who-meta">
            {current.is_new ? "New shopper" : `Shopper ${current.id}`} · switch
          </span>
        </button>
        <SearchBox key={`search-${shopper.id}`} value={query} suggestions={ideas} onSearch={setQuery} />
        {feed && (
          <span className={`model-badge${loading ? " is-busy" : ""}`}>
            {loading
              ? "Restocking for your basket…"
              : feed.model === "behaviorgpt"
                ? "Personalized by BehaviorGPT"
                : "Offline: from past baskets"}
          </span>
        )}
        {!current.is_new && <button
          className={`reveal-toggle${reveal ? " is-on" : ""}`}
          aria-pressed={reveal}
          onClick={() => setReveal((r) => !r)}
          title="Demo: mark what this shopper really bought next (the model never saw it)"
        >
          {reveal ? "Hide" : "Reveal"} next order
        </button>}
        <Basket
          key={`basket-${shopper.id}`}
          cart={cart}
          shopper={feed?.shopper ?? shopper}
          forgot={forgot}
          loading={loading}
          onSetQuantity={setQuantity}
          onCheckout={checkoutAndRecord}
          onNextVisit={async () => {
            await api.nextVisit(shopper.id);
            setVisit((v) => v + 1);
          }}
        />
      </header>

      {newId != null && !query && (
        <nav className="tabs" aria-label="Views">
          <button className={tab === "store" ? "is-on" : ""} onClick={() => setTab("store")}>
            Store
          </button>
          <button className={tab === "foryou" ? "is-on" : ""} onClick={() => setTab("foryou")}>
            For you
            {(forYou?.pattern ?? livePattern)?.tags.map((t) => (
              <span key={t.key} className={`pattern-mark is-${t.key} is-${t.strength}`}>
                {t.label}
              </span>
            ))}
          </button>
        </nav>
      )}

      <TrackingContext.Provider value={tracking}>
      <RevealContext.Provider value={revealed}>
        {reveal && !query ? <ReplayPanel replay={replay} error={replayError} /> : null}
        {tab === "foryou" && newId != null && !query ? (
          <ForYouView
            forYou={forYou}
            live={livePattern}
            loading={forYouLoading}
            error={forYouError}
            quantityOf={quantityOf}
            onSetQuantity={setQuantity}
            onAddAll={addMany}
          />
        ) : query ? (
          <main className="walk">
            <SearchView
              shopperId={shopper.id}
              query={query}
              cart={cart}
              quantityOf={quantityOf}
              onSetQuantity={setQuantity}
              onSetMany={setMany}
              onBack={() => setQuery("")}
            />
          </main>
        ) : (
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
        )}
      </RevealContext.Provider>
      </TrackingContext.Provider>

      {peek && (
        <ProductPeek
          item={peek}
          quantity={quantityOf(peek.product.id)}
          onSetQuantity={setQuantity}
          onClose={(ms) => {
            tracker.opened(peek.product.id, ms);
            setPeek(null);
          }}
        />
      )}
    </div>
  );
}
