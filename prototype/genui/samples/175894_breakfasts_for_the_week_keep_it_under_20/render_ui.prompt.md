# system

You compose the screen a grocery shopper sees after typing an intent, then call render_ui.
You may only use product ids from the candidate lists given (each list is personalized for this shopper by a behavior
model; 'yours' rows are products this shopper already bought, with how often). Rules:
- One basket_section with one pick per searched need (more units via quantity, not duplicates). Prefer the shopper's own
  usual product when it fits the need and the budget; otherwise the best-ranked candidate that truly matches the need.
  Skip candidates that are off-topic for the need.
- Stay under the budget if there is one. Prices are per unit; the total is quantity x price. If the budget is tight,
  drop optional needs before core ones and pick cheaper candidates; say what you dropped in a note.
- note on each item: why this one, in under 70 chars, grounded in the data ('Your usual, bought 9x', 'Cheapest here').
- Add a swap_row for up to 3 picks where a real alternative exists (cheaper / your_usual / organic / healthier).
- Add a recipe_card when the intent is a meal (ingredients = picked product ids), a pantry_check for pantry needs,
  a budget_meter when there is a budget, and question_chips with 2-4 useful refinements ('Make it vegetarian').
- Order blocks: header, budget_meter (if any), basket_section, swap_rows, recipe_card, pantry_check, notes, question_chips.
Never write product names into notes that are not in the candidates. Do not compute totals in copy; the app shows them.

# user

Shopper 175894 - Budget-minded: 3 items a trip, usually Saturday mornings · 23% organic. Last order 7 days ago.
Their regulars (most likely this trip first):
- Tofu Spring Roll ($1.99; Every ~20 days · last 7 days ago)
- Artesian Sparkling Water ($1.99; Bought 4× · last 92 days ago)
- 0% Fat Free Organic Milk ($6.29; Every ~15 days · last 7 days ago)
- Organic Skim Milk ($6.29; Bought 2× · last 120 days ago)
- Pomegranate ($1.99; Every ~30 days · last 7 days ago)
- Maple Almond Butter ($6.99; Bought 2× · last 37 days ago)
- Banana ($0.29; Bought once · 37 days ago)
- Sparkling Natural Mineral Water ($6.49; Bought once · 127 days ago)
- Classic Almond Butter All Natural ($6.49; Bought once · 71 days ago)
- Organic Kiwi ($0.69; Bought once · 37 days ago)
- Sesame Seaweed Salad ($3.99; Bought once · 120 days ago)
- Chocolate Hazelnut Butter ($4.49; Bought once · 71 days ago)

Intent: breakfasts for the week, keep it under $20

Plan:
{"title": "Breakfasts for the week", "servings": 7, "constraints": ["under $20", "budget-minded"], "assumptions": ["Seven breakfasts for one: oatmeal with banana, or toast and eggs.", "Almond butter is optional: you may still have some from 37 days ago."]}
Budget (cents): 2000

Candidates per need (id | name | unit price | aisle | history):
## oats - Rolled oats - 1 unit(s) - core - query 'oats'
- 46847 | Quick Cooking Rolled Oats Irish Oatmeal | $3.49 | Hot Cereal Pancake Mixes | ranked #1
- 30340 | Oatmeal Squares Brown Sugar | $3.99 | Cereal | ranked #2
- 45977 | Breakfast Honey Oat Gluten Free Non GMO 5 Super Grains Bar Packs | $4.49 | Breakfast Bakery | ranked #3
- 1848 | Rockin' Raspberry 3.1 Fl Oz | $1.49 | Yogurt | ranked #4
- 27681 | Lower Sugar Instant Oatmeal  Variety | $3.49 | Hot Cereal Pancake Mixes | ranked #5

## milk - Milk - 1 unit(s) - core - query 'milk'
- 49517 | 0% Fat Free Organic Milk | $6.29 | Milk | yours, bought 3x
- 26346 | Organic Skim Milk | $6.29 | Milk | yours, bought 2x
- 27845 | Organic Whole Milk | $6.49 | Milk | ranked #1
- 17316 | Vitamin D Organic Whole Milk | $6.29 | Milk | ranked #2
- 329 | Organic Whole Grassmilk Milk | $7.49 | Milk | ranked #3
- 36011 | Organic Fat Free Milk | $6.29 | Milk | ranked #4
- 13166 | Organic Milk Reduced Fat, 2% Milkfat | $6.29 | Milk | ranked #5

## bananas - Bananas (6) - 6 unit(s) - core - query 'banana'
- 24852 | Banana | $0.29 | Fresh Fruits | yours, bought 1x
- 37067 | Organic Banana | $0.39 | Fresh Fruits | ranked #1
- 13176 | Bag of Organic Bananas | $2.49 | Fresh Fruits | ranked #2
- 39276 | Bananas | $0.29 | Fresh Fruits | ranked #3
- 9901 | Original Strawberry Banana Yogurt | $1.19 | Yogurt | ranked #4
- 10944 | Organic Russian Banana Fingerling Potato | $2.49 | Fresh Fruits | ranked #5

## bread - Whole wheat bread - 1 unit(s) - core - query 'whole wheat bread'
- 45123 | Organic 21 Grain Thin Sliced Bread | $5.49 | Bread | ranked #1
- 48628 | Organic Whole Wheat Bread | $4.99 | Bread | ranked #2
- 18362 | Organic Bread with 21 Whole Grains | $4.99 | Bread | ranked #3
- 3896 | Organic Honey Sweet Whole Wheat Bread | $4.99 | Bread | ranked #4
- 5077 | 100% Whole Wheat Bread | $3.79 | Bread | ranked #5

## eggs - Eggs - 1 unit(s) - optional - query 'eggs'
- 30233 | Organic Large Brown Grade AA Cage Free Eggs | $5.99 | Eggs | ranked #1
- 26384 | Large Brown Eggs | $3.49 | Eggs | ranked #2
- 35921 | Organic Large Grade A Brown Eggs | $5.49 | Eggs | ranked #3
- 36550 | Organic Extra Large Grade AA Brown Eggs | $6.49 | Eggs | ranked #4
- 46654 | Organic Grade A Large Brown Eggs | $5.49 | Eggs | ranked #5

## nut_butter - Almond butter - 1 unit(s) - optional - query 'almond butter'
- 27044 | Maple Almond Butter | $6.99 | Spreads | yours, bought 2x
- 18891 | Classic Almond Butter All Natural | $6.49 | Spreads | yours, bought 1x
- 30450 | Creamy Almond Butter | $6.49 | Spreads | ranked #1
- 31338 | Classic Almond Butter | $6.99 | Spreads | ranked #2
- 32611 | Honey Almond Butter Single | $0.79 | Spreads | ranked #3
- 46321 | Vanilla Almond Butter | $6.99 | Spreads | ranked #4
- 43713 | Organic Creamy Peanut Butter | $4.99 | Spreads | ranked #5

## honey (Honey) - pantry, not searched

# tool (forced): render_ui

```json
{
 "type": "object",
 "additionalProperties": false,
 "required": [
  "title",
  "blocks"
 ],
 "properties": {
  "title": {
   "type": "string"
  },
  "blocks": {
   "type": "array",
   "items": {
    "anyOf": [
     {
      "type": "object",
      "additionalProperties": false,
      "required": [
       "type",
       "title",
       "subtitle"
      ],
      "properties": {
       "type": {
        "const": "header"
       },
       "title": {
        "type": "string"
       },
       "subtitle": {
        "type": "string"
       }
      }
     },
     {
      "type": "object",
      "additionalProperties": false,
      "required": [
       "type",
       "key",
       "title",
       "subtitle",
       "reason",
       "confidence",
       "items"
      ],
      "properties": {
       "type": {
        "const": "basket_section"
       },
       "key": {
        "type": "string"
       },
       "title": {
        "type": "string"
       },
       "subtitle": {
        "type": "string"
       },
       "reason": {
        "type": "string"
       },
       "confidence": {
        "enum": [
         "sure",
         "good",
         "explore"
        ]
       },
       "items": {
        "type": "array",
        "items": {
         "type": "object",
         "additionalProperties": false,
         "required": [
          "product_id",
          "quantity",
          "need_key",
          "note",
          "tag"
         ],
         "properties": {
          "product_id": {
           "type": "integer",
           "enum": [
            329,
            1848,
            3896,
            5077,
            9901,
            10944,
            13166,
            13176,
            17316,
            18362,
            18891,
            24852,
            26346,
            26384,
            27044,
            27681,
            27845,
            30233,
            30340,
            30450,
            31338,
            32611,
            35921,
            36011,
            36550,
            37067,
            39276,
            43713,
            45123,
            45977,
            46321,
            46654,
            46847,
            48628,
            49517
           ]
          },
          "quantity": {
           "type": "integer"
          },
          "need_key": {
           "type": "string"
          },
          "note": {
           "type": "string"
          },
          "tag": {
           "enum": [
            "usual",
            "pairs",
            "new",
            "due",
            "treat"
           ]
          }
         }
        }
       }
      }
     },
     {
      "type": "object",
      "additionalProperties": false,
      "required": [
       "type",
       "for_product_id",
       "options"
      ],
      "properties": {
       "type": {
        "const": "swap_row"
       },
       "for_product_id": {
        "type": "integer",
        "enum": [
         329,
         1848,
         3896,
         5077,
         9901,
         10944,
         13166,
         13176,
         17316,
         18362,
         18891,
         24852,
         26346,
         26384,
         27044,
         27681,
         27845,
         30233,
         30340,
         30450,
         31338,
         32611,
         35921,
         36011,
         36550,
         37067,
         39276,
         43713,
         45123,
         45977,
         46321,
         46654,
         46847,
         48628,
         49517
        ]
       },
       "options": {
        "type": "array",
        "items": {
         "type": "object",
         "additionalProperties": false,
         "required": [
          "product_id",
          "label",
          "note"
         ],
         "properties": {
          "product_id": {
           "type": "integer",
           "enum": [
            329,
            1848,
            3896,
            5077,
            9901,
            10944,
            13166,
            13176,
            1
```
