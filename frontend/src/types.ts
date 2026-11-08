// Mirrors backend/app/schemas.py — keep in sync.

export interface Product {
  id: number;
  name: string;
  department: string;
  aisle: string;
  price_cents: number;
  emoji: string;
}

export interface CartItem {
  product: Product;
  quantity: number;
}

export interface Cart {
  id: string;
  items: CartItem[];
  item_count: number;
  subtotal_cents: number;
}

export interface Recommendation {
  product: Product;
  score: number;
  source: "bought_together" | "popular";
  reason: string;
}

export interface CheckoutResult {
  order_id: number;
  item_count: number;
}
