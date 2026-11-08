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

  const sectionTitle = query
    ? `Results for “${query}”`
    : department
      ? department
      : "Popular right now";

  return (
    <div className="layout">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            🥕
          </span>
          Basket
        </div>
        <label className="search">
          <span className="search-icon" aria-hidden>
            🔍
          </span>
          <input
            type="search"
            placeholder="Search 3,000 products…"
            aria-label="Search products"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <a className="cart-button" href="#cart" aria-label={`Cart, ${cart?.item_count ?? 0} items`}>
          🛒 <span>{cart?.item_count ?? 0}</span>
        </a>
      </header>

      <main className="main">
        {error && <p className="notice error">{error}</p>}

        {!query && !department && !lastAdded && (
          <section className="hero">
            <div>
              <h1>Groceries that know what goes together</h1>
              <p>
                Suggestions learned from 62,000 real Instacart orders. Add something to your cart
                and see what shoppers usually buy with it.
              </p>
            </div>
            <div className="hero-art" aria-hidden>
              🥑🍓🥖
            </div>
          </section>
        )}

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

        <h2 className="section-title">{sectionTitle}</h2>
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

        <footer className="credits">
          Order data: Instacart Market Basket Analysis (Kaggle). Product photos: Open Food Facts
          contributors, CC BY-SA 4.0. Prices are estimates.
        </footer>
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
