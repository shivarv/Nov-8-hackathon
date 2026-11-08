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
  usual_hour: number;
  usual_gap_days: number;
  n_orders: number;
  days_ahead: number;
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
  /** Days since their last order on the shopper's timeline. */
  days_since_last_order: number | null;
  /** How far the demo has moved the shopper's clock forward ("next visit"). */
  days_ahead: number;
}

export interface CheckoutResult {
  order_id: number;
  item_count: number;
}

export interface SearchResult {
  query: string;
  model: "behaviorgpt" | "fallback";
  /** The shopper's own past items for this query, best first. */
  yours: FeedItem[];
  /** The whole catalog for this query, personalized by history and cart. */
  results: FeedItem[];
  /** Not about the query: what fits their past orders and the cart. */
  for_you: FeedItem[];
  for_you_title: string;
  /** The same query for an anonymous shopper. */
  generic: FeedItem[];
}

export interface ReplayScore {
  name: string;
  description: string;
  hits: number;
  k: number;
}

/** The shopper's real next order (never shown to the model) and how each strategy scores. */
export interface Replay {
  items: number[];
  n: number;
  days_since_prior: number | null;
  scoreboard: ReplayScore[];
  on_home_page: number;
}

export interface PlanPick {
  need_key: string;
  label: string;
  quantity: number;
  /** The product; its reason is Claude's note for the shopper. */
  item: FeedItem;
}

/** A basket built for a request: Claude planned it, BehaviorGPT found the products. */
export interface Plan {
  request: string;
  title: string;
  summary: string;
  tip: string;
  budget_cents: number | null;
  total_cents: number;
  picks: PlanPick[];
  alternatives: Record<string, Product[]>;
  by: "claude" | "rules";
}
