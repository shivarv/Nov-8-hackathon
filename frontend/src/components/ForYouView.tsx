import type { FeedSection, ForYou, Pattern, Trait } from "../types";
import { Shelf } from "./Shelf";

interface Props {
  forYou: ForYou | null;
  /** Their pattern as of the latest browsing batch (newer than `forYou` between refreshes). */
  live: Pattern | null;
  loading: boolean;
  error: string | null;
  quantityOf: (productId: number) => number;
  onSetQuantity: (productId: number, quantity: number) => void;
  onAddAll: (productIds: number[]) => void;
}

const TRAIT_LABEL: Record<Trait, string> = {
  organic: "Organic",
  budget: "Budget",
  premium: "Premium",
};

/**
 * A new shopper's For you tab: the entry generated for them (or how close they are to
 * one), what we've seen them do, the pattern BehaviorGPT signed off on, then shelves
 * BehaviorGPT picked and ordered from their browsing and orders.
 */
export function ForYouView({
  forYou,
  live,
  loading,
  error,
  quantityOf,
  onSetQuantity,
  onAddAll,
}: Props) {
  // Tags and leanings: the pattern BehaviorGPT refereed (with the tab). Counts: the
  // latest browsing batch, which is newer between refreshes.
  const refereed = forYou?.pattern ?? null;
  const pattern = refereed
    ? live
      ? {
          ...refereed,
          products_seen: live.products_seen,
          seconds_looking: live.seconds_looking,
          clicks: live.clicks,
          adds: live.adds,
          purchases: live.purchases,
        }
      : refereed
    : live;
  const entry = forYou?.entry ?? null;
  const noop = (_: FeedSection) => {};

  return (
    <main className="walk foryou" aria-busy={loading}>
      <section className={`entry-card${entry ? " has-entry" : ""}${entry?.just_generated ? " is-fresh" : ""}`}>
        {entry ? (
          <>
            <p className="entry-eyebrow">
              Your entry{entry.just_generated ? " · just generated" : ""} · from what you look at,
              click and buy
            </p>
            <h2 className="entry-label">{entry.label}</h2>
            <p className="entry-blurb">{entry.blurb}</p>
          </>
        ) : (
          <>
            <p className="entry-eyebrow">Your entry · not generated yet</p>
            <h2 className="entry-label">Getting to know you</h2>
            <p className="entry-blurb">
              Browse the store: linger on what interests you, click a product for a closer look,
              add and buy. Once there's enough, BehaviorGPT reads your pattern and we create your
              entry.
            </p>
          </>
        )}

        {pattern && (
          <ul className="entry-stats" aria-label="What we've seen">
            <li>
              <strong>{pattern.products_seen}</strong> seen
            </li>
            <li>
              <strong>{Math.round(pattern.seconds_looking)}s</strong> looking
            </li>
            <li>
              <strong>{pattern.clicks}</strong> clicked
            </li>
            <li>
              <strong>{pattern.adds}</strong> added
            </li>
            <li>
              <strong>{pattern.purchases}</strong> bought
            </li>
          </ul>
        )}

        {pattern?.enough && (
          <div className="entry-pattern">
            {(Object.keys(TRAIT_LABEL) as Trait[]).map((t) => {
              const v = pattern.leanings[t] ?? 0;
              const m = pattern.model_leanings[t];
              const tag = pattern.tags.find((x) => x.key === t);
              return (
                <div key={t} className={`lean${tag ? " is-tagged" : ""}`}>
                  <span className="lean-label">{TRAIT_LABEL[t]}</span>
                  <span className="lean-bar" aria-hidden>
                    <span
                      className={`lean-fill ${v >= 0 ? "is-more" : "is-less"}`}
                      style={{
                        left: v >= 0 ? "50%" : `${50 + Math.max(v, -1) * 50}%`,
                        width: `${Math.min(Math.abs(v), 1) * 50}%`,
                      }}
                    />
                  </span>
                  <span className="lean-value">
                    you {v >= 0 ? "+" : "−"}
                    {Math.round(Math.abs(v) * 100)}
                    {m != null && ` · BehaviorGPT ${m >= 0 ? "+" : "−"}${Math.round(Math.abs(m) * 100)}`}
                  </span>
                </div>
              );
            })}
            {pattern.tags.length > 0 ? (
              <ul className="entry-tags">
                {pattern.tags.map((t) => (
                  <li key={t.key} className={`pattern-mark is-${t.key} is-${t.strength}`}>
                    <strong>{t.label}</strong>
                    {t.strength === "leaning" ? " · leaning" : ""} — {t.why}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="entry-note">No clear leaning yet: you browse a bit of everything.</p>
            )}
          </div>
        )}
        <p className="entry-note">
          We record what you look at, click and buy to tailor this page.
          {forYou && (forYou.model === "behaviorgpt" ? " Shelves picked by BehaviorGPT." : " Offline: shelves from popularity and your signals.")}
        </p>
      </section>

      {error && <p className="notice">Something went wrong: {error}</p>}
      {!forYou && !error && <div className="stop is-placeholder" />}

      {forYou?.sections.map((section) => (
        <Shelf
          key={section.key}
          section={section}
          quantityOf={quantityOf}
          onSetQuantity={onSetQuantity}
          onAddAll={onAddAll}
          onAddFrom={noop}
        />
      ))}
    </main>
  );
}
