import type {
  Cart,
  CheckoutResult,
  Feed,
  Plan,
  Product,
  Recommendation,
  Replay,
  SearchResult,
  Shopper,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  products: (params: { q?: string; department?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.department) qs.set("department", params.department);
    return request<Product[]>(`/products?${qs}`);
  },
  departments: () => request<string[]>("/departments"),

  createCart: () => request<Cart>("/carts", { method: "POST" }),
  getCart: (id: string) => request<Cart>(`/carts/${id}`),
  setQuantity: (cartId: string, productId: number, quantity: number) =>
    request<Cart>(`/carts/${cartId}/items/${productId}`, {
      method: "PUT",
      body: JSON.stringify({ quantity }),
    }),
  checkout: (cartId: string, shopperId: number) =>
    request<CheckoutResult>(`/carts/${cartId}/checkout?shopper_id=${shopperId}`, {
      method: "POST",
    }),

  cartRecommendations: (cartId: string, k = 8) =>
    request<Recommendation[]>(`/recommendations/cart/${cartId}?k=${k}`),
  productRecommendations: (productId: number, k = 6) =>
    request<Recommendation[]>(`/recommendations/product/${productId}?k=${k}`),

  shoppers: () => request<Shopper[]>("/shoppers"),
  feed: (shopperId: number, cartId: string, init?: RequestInit) =>
    request<Feed>(`/feed?shopper_id=${shopperId}&cart_id=${cartId}`, init),
  plan: (shopperId: number, text: string, cartId: string | null, init?: RequestInit) =>
    request<Plan>("/plan", {
      method: "POST",
      body: JSON.stringify({ shopper_id: shopperId, cart_id: cartId, request: text }),
      ...init,
    }),
  replay: (shopperId: number) => request<Replay>(`/shoppers/${shopperId}/replay`),
  nextVisit: (shopperId: number) =>
    request<{ days_ahead: number }>(`/shoppers/${shopperId}/next-visit`, { method: "POST" }),
  search: (shopperId: number, query: string, cartId: string | null, init?: RequestInit) => {
    const qs = new URLSearchParams({ shopper_id: String(shopperId), q: query });
    if (cartId) qs.set("cart_id", cartId);
    return request<SearchResult>(`/search?${qs}`, init);
  },
};

export const formatPrice = (cents: number) => `$${(cents / 100).toFixed(2)}`;
