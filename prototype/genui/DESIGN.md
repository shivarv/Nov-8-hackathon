# Generative UI for the grocery app

Claude composes parts of the screen per shopper and moment: intent, layout, copy and constraints (budget, servings, diet). BehaviorGPT picks which exact products this shopper takes. Purchase counts lead re-buys (36% vs 8% next-basket recall, `prototype/out/eval/results.md`). Claude only references ids the backend returned for this request; the server hydrates and prices them.

## Ideas, ranked by demo impact against risk

| # | Idea | Shopper sees | Claude does | BehaviorGPT / counts do | Latency, failure | Effort |
|---|---|---|---|---|---|---|
| 1 | **"What are you shopping for?"** (prototyped) | "tacos for 4 friday, under $40" becomes a shelf of 8-10 picks (their own avocados, organic where they buy organic), budget meter, swaps, recipe card, "already at home?", refinement chips | Plans needs, quantities and pantry items; one query per need; then picks, notes, swaps within budget | One personalized search per need; the shopper's own items come first | ~15-20 s (est.); first products at ~5-8 s if progressive. Rule-based shelf if Claude fails | M |
| 2 | **Refinement chips / conversational edits** ("make it vegetarian", "cheaper", "for 2") | Tap a chip; the shelf re-renders with a diff | Edits the previous plan and recomposes | Re-searches only the needs that changed | Plan + changed searches + compose; fallbacks as #1 | S after #1 |
| 3 | **Checkout nudge card** | One card: "Taco night but no salsa?", "Eggs are due (every ~17 days)" | Picks at most 3 gaps vs the intent; copy | `goes_with(cart)` and the feed's "due" rhythm supply ids | One short call (~3 s); on failure show nothing | S |
| 4 | **Meal-plan cards on home** ("3 dinners this week") | 3 recipe cards from what they buy, "Add all ingredients" | Proposes meals fitting their history (no meat for 165391) | Per-ingredient search (~24) | ~25 s; pre-generate on "next visit" | M |
| 5 | **Adaptive home layout** | Same shelves reordered and retitled ("Back after 20 days, restock first") | Orders and titles existing section keys (an enum) | Build the sections (counts lead "Buy it again") | Hidden behind the feed; fixed order on failure; can't invent products | S |
| 6 | **Budget fit** | "Make it fit $X" on any basket | Nothing | Cheapest on-topic candidate per need | Instant; `repair_rules` in the prototype | S |
| 7 | **Natural-language "why this?"** | Per-section explanation | Rewrites the data-backed reasons | n/a | Plausible but false reasons; keep item reasons deterministic | S |

Build order: 1, then 2, then 3; 5 is a safe extra; 4 if time allows. Why this beats a fixed layout: the feed answers "what do you usually buy"; 1, 2 and 4 answer "what do you need for *this*", and the screen's shape follows the intent (a meal gets a recipe card, a budget a meter, pantry items a checklist).

## Component vocabulary (`ui_schema.json`)

A spec is `{title, blocks[]}`. Each block has a `type`:

| block | fields | renders as |
|---|---|---|
| `header` | title, subtitle | AisleSign-style heading |
| `basket_section` | key, title, subtitle, reason, confidence, items[{product_id, quantity, need_key, note, tag}] | **FeedSection{kind:"mission"} → `<Shelf>`**. Items become FeedItem (note → reason) → `<ProductTile>`. `confidence:"sure"` shows "Add all" |
| `swap_row` | for_product_id, options[{product_id, label: cheaper/your_usual/organic/healthier/bigger_pack/different_style, note}] | new `<SwapRow>` (mini tiles; tap = remove the old item, add the new one at the same quantity) |
| `budget_meter` | budget_cents (the server adds spent_cents) | new `<BudgetMeter>`, live from the cart subtotal |
| `recipe_card` | title, servings, minutes, steps[], product_ids[] | new `<RecipeCard>` with "Add all ingredients" → `addMany` |
| `pantry_check` | prompt, needs[{need_key, label}] | toggle chips; toggling one on searches for that need |
| `question_chips` | prompt, chips[{label, intent}] | chip row (SearchBox idea-chip style); a tap sends a follow-up turn |
| `note` | tone info/warn, text | one line under the shelf |

Guarantees, in layers:
1. **Enum ids.** For each request, `product_id` becomes `{"enum": [the ids the searches returned]}`. With strict tool use the model can't emit any other id.
2. **Ids only.** The spec carries ids. The server hydrates name, price and image, so the model can't misstate a price.
3. **Validation.** Schema; each id a candidate for *that* need; no duplicates; core needs covered; swaps/recipes reference picks; budget holds (summed by the server, never the model).
4. **Repair.** One repair turn with the exact errors; then `repair_rules` drops bad items, refills empty core needs and cheapens until it fits.
5. **Fallback.** The rule-based composition (shopper's own item, else BehaviorGPT's top on-topic pick) is always computed and can render immediately.

## Prototype: `intent_basket.py`

Context (`/api/shoppers`, `/api/feed`) → **Claude plan** (`plan_basket`) → parallel `/api/search` per need → **Claude compose** (`render_ui`, enum ids) → validate, repair, hydrate, render. Each run writes prompts, plan, candidates, spec, hydrated response, rule baseline and metrics to `samples/<shopper>_<intent>/`.

**Caveat:** `ANTHROPIC_API_KEY` in the repo `.env` is empty, so `--llm api` couldn't run. The stored `plan_basket.json` and `render_ui.json` were written by Claude in-session from the same prompts (`*.prompt.md`), and replayed with `--llm replay`. Grounding, validation, repair and rendering ran for real against the live backend and BehaviorGPT. Once the key is set, `--llm api` records real timings and tokens in `metrics.json`.

### Results (4 runs, 2 shoppers; all specs valid)

| run | picks | total | budget |
|---|---|---|---|
| 165391 "Mostly organic", tacos for 4 under $40 | 9: bean tacos (no meat in their regulars), own avocados (18×), organic otherwise | $36.84 | $40 |
| 175894 "Budget-minded", same intent | 8: beef tacos, the cheapest good match per need | $30.79 | $40 |
| 165391, healthy lunches this week | 9: own spinach, eggs and carrots (all due), quinoa bowls and hummus wraps | $33.79 | none |
| 175894, breakfasts under $20 | 5: own milk and bananas; dropped almond butter, with a note | $18.80 | $20 |

What the runs showed:
- **Composition needs judgment.** Search's "yours" rows leak off-topic items (Organic Bananas for "black beans", "shredded cheese", "sour cream"; a kale-cucumber juice for "cucumber"; avocado-oil mayo for "avocado"). The rule baseline put **2 cold-pressed juices in as cucumbers** and canned tomatoes on tacos; Claude skipped them. (Backend fix: name/aisle-filter `yours`.)
- **Candidate gaps.** The shopper's own "Organic Original Hommus" (25×) is not returned for "hummus", so Claude could only pick the closest organic hummus. Fix: add the shopper's regulars to the allowed ids.
- **Where personalization comes from.** For categories neither shopper buys, BehaviorGPT ranks almost the same products for both (organic first, even for the budget shopper). The contrast comes from "yours" rows plus Claude reading the constraints ($30.79 vs $36.84 for the same intent).
- **Drift.** A fresh rerun changed 1 candidate in 1 of 32 needs, so one stored spec needed repair. Always validate against the candidates of the same request.

### Latency and calls per intent

| phase | measured | calls |
|---|---|---|
| context | 0.2-0.9 s | 2 backend (~2 BehaviorGPT) |
| ground, 6-9 parallel searches | 0.8-2.6 s | 6-9 backend, ~3 BehaviorGPT each (18-27) |
| plan (Claude) | not measured; ~1.1k tokens in, 260-380 out → est. 3-6 s | 1 LLM |
| compose (Claude) | not measured; 2.6-3.1k tokens in (35-53 candidate ids), 660-960 out → est. 8-15 s | 1 LLM (+1 if repair) |

Compose output is the bottleneck. Mitigations: stream it; render the rule-based shelf at plan+ground (~5-8 s) and let Claude's version replace it; use Sonnet for both calls and cache the system prompts.
