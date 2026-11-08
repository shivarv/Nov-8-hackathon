import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { CartPanel } from "./components/CartPanel";
import { ProductCard } from "./components/ProductCard";
import { RecommendationRow } from "./components/RecommendationRow";
import { useCart } from "./hooks/useCart";
import type { Product, Recommendation } from "./types";

export default function App() {
  const { cart, error, setQuantity, checkout, quantityOf } = useCart();
  const [products, setProducts] = useState<Product[]>([]);
  const [departments, setDepartments] = useState<string[]>([]);
  const [department, setDepartment] = useState<string>("");
  const [query, setQuery] = useState("");
  const [cartRecs, setCartRecs] = useState<Recommendation[]>([]);
  const [lastAdded, setLastAdded] = useState<Product | null>(null);
  const [lastAddedRecs, setLastAddedRecs] = useState<Recommendation[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api.departments().then(setDepartments).catch(console.error);
  }, []);

  // Debounced product search.
  useEffect(() => {
    const t = setTimeout(() => {
      api.products({ q: query, department }).then(setProducts).catch(console.error);
    }, 150);
    return () => clearTimeout(t);
  }, [query, department]);

  // Re-score "complete your cart" whenever the cart's contents change.
  const cartKey = useMemo(
    () => cart?.items.map((i) => i.product.id).join(",") ?? null,
    [cart],
  );
  useEffect(() => {
    if (!cart) return;
    api.cartRecommendations(cart.id, 6).then(setCartRecs).catch(console.error);
    // Keyed on cart contents, not object identity (quantity changes don't need a re-score).
  }, [cart?.id, cartKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // "Frequently bought with X" for the most recently added product.
  useEffect(() => {
    if (!lastAdded) {
      setLastAddedRecs([]);
      return;
    }
    api.productRecommendations(lastAdded.id, 6).then(setLastAddedRecs).catch(console.error);
  }, [lastAdded]);

  const handleSetQuantity = (productId: number, quantity: number) => {
    const wasInCart = quantityOf(productId) > 0;
    setMessage(null);
    void setQuantity(productId, quantity);
    if (!wasInCart && quantity > 0) {
      const product =
        products.find((p) => p.id === productId) ??
        [...cartRecs, ...lastAddedRecs].find((r) => r.product.id === productId)?.product;
      if (product) setLastAdded(product);
    }
  };

  const handleCheckout = async () => {
    const result = await checkout();
    if (result) {
      setMessage(`Order #${result.order_id} placed — the recommender just learned from it.`);
      setLastAdded(null);
    }
  };

  return (
    <div className="layout">
      <header className="topbar">
        <div className="brand">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="m2.05 2.05 1.099-.028a1 1 0 0 1 1.008.815l2.69 14.347A1 1 0 0 0 7.83 18H18" />
            <path d="M4.563 5h16.435a1 1 0 0 1 .981 1.204l-1.026 6.226A2 2 0 0 1 18.962 14H6.25" />
            <circle cx="18" cy="20" r="2" />
            <circle cx="8" cy="20" r="2" />
          </svg>
          <span>QuickBuyIt</span>
        </div>
        <input
          className="search"
          type="search"
          placeholder="Search products…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </header>

      <main className="main">
        {error && <p className="notice error">{error}</p>}

        <nav className="chips" aria-label="Departments">
          {["", ...departments].map((d) => (
            <button
              key={d || "all"}
              className={d === department ? "chip active" : "chip"}
              onClick={() => setDepartment(d)}
            >
              {d || "All"}
            </button>
          ))}
        </nav>

        {lastAdded && (
          <RecommendationRow
            title={`Frequently bought with ${lastAdded.name}`}
            recs={lastAddedRecs}
            quantityOf={quantityOf}
            onSetQuantity={handleSetQuantity}
            onDismiss={() => setLastAdded(null)}
          />
        )}

        <section className="grid">
          {products.map((p) => (
            <ProductCard
              key={p.id}
              product={p}
              quantity={quantityOf(p.id)}
              onSetQuantity={handleSetQuantity}
            />
          ))}
          {products.length === 0 && <p className="muted">No products match.</p>}
        </section>
      </main>

      <CartPanel
        cart={cart}
        recs={cartRecs}
        onSetQuantity={handleSetQuantity}
        onCheckout={handleCheckout}
        message={message}
      />
    </div>
  );
}
