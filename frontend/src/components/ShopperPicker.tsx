import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Shopper } from "../types";

interface Props {
  onPick: (shopper: Shopper) => void;
}

const MINE = "newShopperId";

function readMine(): number | null {
  try {
    return Number(localStorage.getItem(MINE)) || null;
  } catch {
    return null;
  }
}

function storeMine(id: number) {
  try {
    localStorage.setItem(MINE, String(id));
  } catch {
    /* storage unavailable: they can't continue as this shopper after a reload */
  }
}

/**
 * "Who's shopping?" Start as a new shopper (no history), continue as the new shopper
 * this browser started before, or shop as a real Instacart shopper.
 */
export function ShopperPicker({ onPick }: Props) {
  const [shoppers, setShoppers] = useState<Shopper[] | null>(null);
  const [mine, setMine] = useState<Shopper | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.shoppers().then(setShoppers).catch((e) => setError(String(e)));
    const id = readMine();
    if (id)
      api
        .shopper(id)
        .then(setMine)
        .catch((e) => {
          if (!(e instanceof ApiError && e.status === 404)) setError(String(e));
        });
  }, []);

  const startNew = () =>
    api
      .newShopper()
      .then((s) => {
        storeMine(s.id);
        onPick(s);
      })
      .catch((e) => setError(String(e)));

  return (
    <main className="picker">
      <header className="picker-head">
        <p className="eyebrow">Better Basket</p>
        <h1 className="picker-title">Who's shopping today?</h1>
        <p className="picker-lede">
          Start as a new shopper and the store learns from what you look at, click and buy, or
          pick a real Instacart shopper and it lays itself out around what they buy.
        </p>
      </header>

      {error && <p className="notice">Couldn't load shoppers: {error}</p>}

      <ul className="picker-grid">
        <li>
          <button className="shopper-card is-new" onClick={startNew}>
            <span className="new-flag">New shopper</span>
            <span className="shopper-label">Start fresh</span>
            <span className="shopper-blurb">
              No history. What you look at, click and buy builds your For you tab, and your entry
              is generated once there's enough.
            </span>
            <span className="shopper-meta">Read by BehaviorGPT · saved to your profile</span>
          </button>
        </li>
        {mine && (
          <li>
            <button
              className={`shopper-card is-mine${mine.has_entry ? "" : " is-pending"}`}
              onClick={() => onPick(mine)}
            >
              <span className="new-flag is-mine">{mine.has_entry ? "Your entry" : "You, so far"}</span>
              <span className="shopper-label">{mine.label}</span>
              <span className="shopper-blurb">{mine.blurb}</span>
              <span className="shopper-meta">
                {mine.n_orders} {mine.n_orders === 1 ? "order" : "orders"} · continue
              </span>
            </button>
          </li>
        )}
        {(shoppers ?? []).map((s) => (
          <li key={s.id}>
            <button className="shopper-card" onClick={() => onPick(s)}>
              <span className="shopper-label">{s.label}</span>
              <span className="shopper-blurb">{s.blurb}</span>
              <span className="shopper-meta">
                Shopper {s.id} · {s.n_orders} past orders
              </span>
            </button>
          </li>
        ))}
        {shoppers === null &&
          !error &&
          Array.from({ length: 6 }, (_, i) => (
            <li key={i}>
              <div className="shopper-card is-placeholder" aria-hidden />
            </li>
          ))}
      </ul>
    </main>
  );
}
