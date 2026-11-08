# system

You plan grocery purchases for an online grocery store (the Instacart catalog, US, 2017 prices).
Read the shopper's intent and their history, then call plan_basket. Be concrete and frugal: the fewest needs that
make the intent work, quantities sized to the servings, pantry staples marked as pantry. Respect stated budgets and
diets; infer diet only from strong evidence in the history (e.g. no meat at all, tofu every trip) and say so in
assumptions. Search queries must be plain catalog words, one product type each.

# user

Shopper 165391 - Mostly organic: 15 items a trip, usually Monday afternoons · 74% organic. Last order 20 days ago.
Their regulars (most likely this trip first):
- Organic Original Hommus ($3.99; Due · every ~14 days, last 20 days ago)
- Organic Avocado ($1.79; Every ~20 days · last 20 days ago)
- Organic Free Range Grade A Large Brown Eggs ($4.99; Every ~17 days · last 20 days ago)
- Organic Red Chard Greens ($2.49; Due · every ~23 days, last 48 days ago)
- Organic Garlic ($0.99; Every ~27 days · last 20 days ago)
- Organic Zucchini ($1.99; Every ~26 days · last 20 days ago)
- Organic Baby Spinach ($4.49; Due · every ~30 days, last 38 days ago)
- Sparkling Natural Mineral Water ($6.49; Every ~33 days · last 20 days ago)
- Organic Muenster Cheese Slices ($3.99; Due · every ~27 days, last 48 days ago)
- Organic Plain Kefir ($4.49; Every ~32 days · last 38 days ago)
- Extra Virgin Olive Oil ($8.99; Every ~35 days · last 20 days ago)
- Organic Baby Carrots ($2.29; Due · every ~32 days, last 48 days ago)

Intent: tacos for 4 on friday, under $40

# tool (forced): plan_basket

```json
{
 "type": "object",
 "additionalProperties": false,
 "required": [
  "title",
  "servings",
  "budget_cents",
  "constraints",
  "needs",
  "assumptions"
 ],
 "properties": {
  "title": {
   "type": "string",
   "description": "Short screen title, e.g. 'Taco night for 4'."
  },
  "servings": {
   "type": "integer",
   "description": "People or portions to cover (1 if not food for a meal)."
  },
  "budget_cents": {
   "type": [
    "integer",
    "null"
   ],
   "description": "Budget in cents if the intent states or clearly implies one, else null."
  },
  "constraints": {
   "type": "array",
   "items": {
    "type": "string"
   },
   "description": "Diet, price or style constraints read from the intent and history ('vegetarian', 'cheap', 'kid friendly')."
  },
  "needs": {
   "type": "array",
   "description": "At most 10. Core items first.",
   "items": {
    "type": "object",
    "additionalProperties": false,
    "required": [
     "key",
     "label",
     "query",
     "units",
     "role"
    ],
    "properties": {
     "key": {
      "type": "string",
      "description": "snake_case id, e.g. 'tortillas'."
     },
     "label": {
      "type": "string",
      "description": "What the shopper reads: 'Tortillas (12-16)'."
     },
     "query": {
      "type": "string",
      "description": "1-3 plain grocery words the store catalog would use ('corn tortillas', 'shredded cheese'). No brands, no 'organic' unless the shopper asked: the search is already personalized."
     },
     "units": {
      "type": "integer",
      "description": "How many packs/items to buy for the servings."
     },
     "role": {
      "enum": [
       "core",
       "optional",
       "pantry"
      ],
      "description": "core: the intent fails without it. optional: nice to have, first to drop for budget. pantry: most homes have it (salt, oil, spices) - not searched, offered as 'already at home?'."
     }
    }
   }
  },
  "assumptions": {
   "type": "array",
   "items": {
    "type": "string"
   },
   "description": "Assumptions worth telling the shopper ('Beef tacos; tap Vegetarian to switch')."
  }
 }
}
```
