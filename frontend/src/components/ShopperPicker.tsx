import { useEffect, useState } from "react";
import { api } from "../api";
import type { Shopper } from "../types";

interface Props {
  onPick: (shopper: Shopper) => void;
}

/** "Who's shopping?" Real Instacart shoppers, described by their own order history. */
export function ShopperPicker({ onPick }: Props) {
  const [shoppers, setShoppers] = useState<Shopper[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.shoppers().then(setShoppers).catch((e) => setError(String(e)));
  }, []);

  return (
    <main className="picker">
      <header className="picker-head">
        <p className="eyebrow">Basket</p>
        <h1 className="picker-title">Who's shopping today?</h1>
        <p className="picker-lede">
          Each of these is a real Instacart shopper. Pick one and the store lays itself out
          around what they buy.
        </p>
      </header>

      {error && <p className="notice">Couldn't load shoppers: {error}</p>}

      <ul className="picker-grid">
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
