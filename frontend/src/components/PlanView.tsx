import { useEffect, useState } from "react";
import { api, formatPrice } from "../api";
import type { Cart, Plan } from "../types";
import { ProductTile } from "./ProductTile";

interface Props {
  shopperId: number;
  request: string;
  cart: Cart | null;
  quantityOf: (productId: number) => number;
  onSetQuantity: (productId: number, quantity: number) => void;
  onSetMany: (entries: [number, number][]) => Promise<void>;
  onClose: () => void;
}

// What the planner is doing, shown while it works (~15 s): Claude plans, BehaviorGPT
// finds this shopper's products, Claude composes, the server checks.
const STEPS = [
  "Claude is reading your request…",
  "BehaviorGPT is finding your products for each item…",
  "Claude is choosing within your budget…",
  "Checking every pick…",
];

/** A basket built for a request ("tacos for 4 friday under $40"), ready to add in one tap. */
export function PlanView({
  shopperId,
  request,
  cart,
  quantityOf,
  onSetQuantity,
  onSetMany,
  onClose,
}: Props) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [adding, setAdding] = useState(false);
  const cartId = cart?.id ?? null;

  useEffect(() => {
    const controller = new AbortController();
    setPlan(null);
    setError(null);
    setStep(0);
    const tick = window.setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 4500);
    api
      .plan(shopperId, request, cartId, { signal: controller.signal })
      .then(setPlan)
      .catch((e) => e?.name !== "AbortError" && setError(String(e)))
      .finally(() => window.clearInterval(tick));
    return () => {
      controller.abort();
      window.clearInterval(tick);
    };
    // Plan once per request; adding its items to the cart must not re-plan.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shopperId, request]);

  const head = (
    <button className="back-link" onClick={onClose}>
      ← Back to the results
    </button>
  );

  if (error) {
    return (
      <>
        {head}
        <p className="notice">Couldn't build that basket: {error}</p>
      </>
    );
  }
  if (!plan) {
    return (
      <>
        {head}
        <section className="plan plan--loading" aria-busy="true">
          <p className="eyebrow">Building a basket for “{request}”</p>
          <ol className="plan-steps">
            {STEPS.map((s, i) => (
              <li key={s} className={i < step ? "is-done" : i === step ? "is-now" : undefined}>
                {s}
              </li>
            ))}
          </ol>
        </section>
      </>
    );
  }

  const missing = plan.picks.filter((p) => quantityOf(p.item.product.id) < p.quantity);
  const over = plan.budget_cents != null && plan.total_cents > plan.budget_cents;

  async function addAll() {
    setAdding(true);
    try {
      await onSetMany(missing.map((p) => [p.item.product.id, p.quantity]));
    } finally {
      setAdding(false);
    }
  }

  return (
    <>
      {head}
      <section className="plan">
        <header className="plan-head">
          <div>
            <p className="eyebrow">
              {plan.by === "claude" ? "Planned by Claude · products by BehaviorGPT" : "Quick picks (Claude unavailable)"}
            </p>
            <h2>{plan.title}</h2>
            {plan.summary ? <p className="plan-summary">{plan.summary}</p> : null}
          </div>
          <div className="plan-total">
            <strong>{formatPrice(plan.total_cents)}</strong>
            {plan.budget_cents != null ? (
              <>
                <span className={`plan-meter${over ? " is-over" : ""}`} aria-hidden>
                  <span style={{ width: `${Math.min(100, (100 * plan.total_cents) / plan.budget_cents)}%` }} />
                </span>
                <span>of your {formatPrice(plan.budget_cents)} budget</span>
              </>
            ) : (
              <span>{plan.picks.length} items</span>
            )}
            <button className="checkout plan-add" disabled={!missing.length || adding} onClick={addAll}>
              {adding ? "Adding…" : missing.length ? `Add all ${missing.length} to basket` : "All in your basket"}
            </button>
          </div>
        </header>
        {plan.tip ? <p className="plan-tip">💡 {plan.tip}</p> : null}
        <div className="results-grid" role="list">
          {plan.picks.map((p) => (
            <div role="listitem" key={`${p.need_key}-${p.item.product.id}`} className="plan-pick">
              <span className="plan-need">
                {p.label}
                {p.quantity > 1 ? ` · ×${p.quantity}` : ""}
              </span>
              <ProductTile
                item={p.item}
                quantity={quantityOf(p.item.product.id)}
                onSetQuantity={onSetQuantity}
              />
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
