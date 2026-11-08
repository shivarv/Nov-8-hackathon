// Mirrors backend/app/schemas.py — keep in sync.

export interface Product {
  id: number;
  name: string;
  department: string;
  aisle: string;
  price_cents: number;
  emoji: string;
  image_url: string | null;
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
  source: "behaviorgpt" | "bought_together" | "popular";
  reason: string;
}

export interface Shopper {
  id: number;
  label: string;
  blurb: string;
  usual_day: string;
  n_orders: number;
}

export type Confidence = "sure" | "good" | "explore";
export type ItemTag = "usual" | "pairs" | "new" | "due" | "treat";
export type SectionKind = "regulars" | "pairs" | "mission" | "aisle" | "due" | "treat";

export interface FeedItem {
  product: Product;
  tag: ItemTag;
  reason: string;
  confidence: number;
}

export interface FeedSection {
  key: string;
  kind: SectionKind;
  title: string;
  subtitle: string;
  confidence: Confidence;
  aisle_number: number | null;
  items: FeedItem[];
}

export interface Feed {
  shopper: Shopper;
  sections: FeedSection[];
  model: "behaviorgpt" | "fallback";
  /** Shopper's own items BehaviorGPT is surest about for this basket (empty without it). */
  ready_to_add: FeedItem[];
}

export interface CheckoutResult {
  order_id: number;
  item_count: number;
}
