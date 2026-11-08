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

Intent: tacos for 4 on friday, under $40

Plan:
{"title": "Taco night for 4 \u00b7 Friday", "servings": 4, "constraints": ["under $40", "budget-minded: small, cheap trips"], "assumptions": ["Classic beef tacos; tap 'Make it vegetarian' to swap the beef for beans."]}
Budget (cents): 4000

Candidates per need (id | name | unit price | aisle | history):
## tortillas - Tortillas (about 20) - 2 unit(s) - core - query 'flour tortillas'
- 17725 | Organic Wraps Traditional - 6 CT | $3.49 | Tortillas Flat Bread | ranked #1
- 36591 | 100% Whole Wheat Medium Soft Taco Flour Tortillas | $3.29 | Tortillas Flat Bread | ranked #2
- 19508 | Corn Tortillas | $2.49 | Tortillas Flat Bread | ranked #3
- 39429 | Organic Large Flour Tortillas 6 Count | $3.49 | Tortillas Flat Bread | ranked #4
- 19816 | Sonoma Traditional Flour Tortillas 10 Count | $2.99 | Tortillas Flat Bread | ranked #5

## ground_beef - Ground beef (2 lb) - 2 unit(s) - core - query 'ground beef'
- 28437 | Organic 85% Ground Beef | $7.99 | Meat Counter | ranked #1
- 22888 | 90% Lean Ground Beef | $5.99 | Meat Counter | ranked #2
- 13198 | 85% Lean Ground Beef | $5.49 | Meat Counter | ranked #3
- 49236 | 80% Lean Ground Beef | $4.99 | Meat Counter | ranked #4
- 10603 | 93% Ground Beef | $6.49 | Meat Counter | ranked #5

## seasoning - Taco seasoning - 1 unit(s) - core - query 'taco seasoning'
- 35068 | Taco Mild Seasoning Mix | $0.79 | Marinades Meat Preparation | ranked #1
- 40136 | Original Taco Seasoning Mix | $0.99 | Spices Seasonings | ranked #2
- 47226 | Taco Seasoning Mix Original | $0.99 | Spices Seasonings | ranked #3
- 38470 | Mild Taco Seasoning Mix | $1.29 | Marinades Meat Preparation | ranked #4
- 35923 | Taco 25% Less Sodium Seasoning Mix | $0.99 | Marinades Meat Preparation | ranked #5

## cheese - Shredded cheese - 1 unit(s) - core - query 'shredded cheese'
- 46575 | Organic Finely Shredded Cheddar Cheese | $3.99 | Packaged Cheese | ranked #1
- 41178 | Natural Finely Shredded Triple Cheddar Cheese | $3.49 | Packaged Cheese | ranked #2
- 29921 | Cheese Finely Shredded Mexican Four Cheese Blend | $3.29 | Packaged Cheese | ranked #3
- 12078 | Shredded Mexican Blend Cheese | $2.99 | Packaged Cheese | ranked #4
- 27429 | 4 Cheese Mexican Fine Cut Shredded Cheese | $2.99 | Packaged Cheese | ranked #5

## salsa - Salsa - 1 unit(s) - core - query 'salsa'
- 13535 | Organic Medium Salsa | $4.49 | Preserved Dips Spreads | ranked #1
- 41433 | Fresh Roasted Tomate & Chile Asado Medium Salsa | $3.99 | Fresh Dips Tapenades | ranked #2
- 27817 | Fresh Medium Salsa | $3.99 | Fresh Dips Tapenades | ranked #3
- 40408 | SALSA        FRNTR CHPTL SALSA | $4.49 | Preserved Dips Spreads | ranked #4
- 22093 | Restaurant Style Medium Salsa | $2.99 | Preserved Dips Spreads | ranked #5

## lettuce - Lettuce - 1 unit(s) - optional - query 'iceberg lettuce'
- 6873 | Organic Iceberg Lettuce | $2.49 | Fresh Vegetables | ranked #1
- 41220 | Organic Romaine Lettuce | $2.49 | Fresh Vegetables | ranked #2
- 28993 | Iceberg Lettuce | $1.99 | Fresh Vegetables | ranked #3
- 17795 | Organic Green Leaf Lettuce | $2.49 | Fresh Vegetables | ranked #4
- 26497 | Romaine Lettuce | $1.99 | Fresh Vegetables | ranked #5

## tomatoes - Tomatoes - 2 unit(s) - optional - query 'tomatoes'
- 26369 | Organic Roma Tomato | $2.49 | Fresh Vegetables | ranked #1
- 47042 | Organic Red On the Vine Tomato | $3.49 | Fresh Vegetables | ranked #2
- 8048 | Packaged Grape Tomatoes | $2.99 | Packaged Produce | ranked #3
- 29487 | Roma Tomato | $1.79 | Fresh Vegetables | ranked #4
- 43772 | Cherubs Heavenly Salad Tomatoes | $3.99 | Fresh Vegetables | ranked #5

## sour_cream - Sour cream - 1 unit(s) - optional - query 'sour cream'
- 42701 | Organic Sour Cream | $3.49 | Other Creams Cheeses | ranked #1
- 27323 | Pure & Natural Sour Cream | $2.49 | Other Creams Cheeses | ranked #2
- 45842 | Natural Sour Cream | $2.49 | Other Creams Cheeses | ranked #3
- 17803 | Organic Cultured Sour Cream | $3.49 | Other Creams Cheeses | ranked #4
- 29295 | Organic Lowfat Sour Cream | $3.29 | Other Creams Cheeses | ranked #5

## oil (Cooking oil) - pantry, not searched

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
            6873,
            8048,
            10603,
            12078,
            13198,
            13535,
            17725,
            17795,
            17803,
            19508,
            19816,
            22093,
            22888,
            26369,
            26497,
            27323,
            27429,
            27817,
            28437,
            28993,
            29295,
            29487,
            29921,
            35068,
            35923,
            36591,
            38470,
            39429,
            40136,
            40408,
            41178,
            41220,
            41433,
            42701,
            43772,
            45842,
            46575,
            47042,
            47226,
            49236
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
         6873,
         8048,
         10603,
         12078,
         13198,
         13535,
         17725,
         17795,
         17803,
         19508,
         19816,
         22093,
         22888,
         26369,
         26497,
         27323,
         27429,
         27817,
         28437,
         28993,
         29295,
         29487,
         29921,
         35068,
         35923,
         36591,
         38470,
         39429,
         40136,
         40408,
         41178,
         41220,
         41433,
         42701,
         43772,
         45842,
         46575,
         47042,
         47226,
         49236
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
           "type": "integer
```
