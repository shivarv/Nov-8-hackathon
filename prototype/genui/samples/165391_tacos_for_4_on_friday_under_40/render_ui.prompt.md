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

Plan:
{"title": "Taco night for 4 \u00b7 Friday", "servings": 4, "constraints": ["under $40", "vegetarian-leaning: no meat in 12 regulars over 27 orders", "mostly organic"], "assumptions": ["Bean tacos: none of your regulars are meat. Tap 'Add ground beef' to switch.", "Two packs of corn tortillas, about 6 tacos each."]}
Budget (cents): 4000

Candidates per need (id | name | unit price | aisle | history):
## tortillas - Corn tortillas (about 24) - 2 unit(s) - core - query 'corn tortillas'
- 36256 | Yellow Soft Corn Tortillas 8 Count | $2.49 | Tortillas Flat Bread | ranked #1
- 31378 | Traditional Size Corn Tortillas, 6\" | $2.99 | Tortillas Flat Bread | ranked #2
- 19816 | Sonoma Traditional Flour Tortillas 10 Count | $2.99 | Tortillas Flat Bread | ranked #3
- 25686 | Super Soft Flour Tortillas Fajita Size 20 ct | $3.49 | Tortillas Flat Bread | ranked #4
- 28883 | Organic Yellow Corn Taco Shells 12 Count | $2.99 | Latino Foods | ranked #5

## beans - Black beans (2 cans) - 2 unit(s) - core - query 'black beans'
- 13176 | Bag of Organic Bananas | $2.49 | Fresh Fruits | yours, bought 5x
- 27156 | Organic Black Beans | $1.79 | Canned Meals Beans | ranked #1
- 35042 | Black Beans | $1.29 | Canned Meals Beans | ranked #2
- 49175 | Organic Pinto Beans | $1.79 | Canned Meals Beans | ranked #3
- 14267 | Organic Refried Black Beans | $2.49 | Canned Meals Beans | ranked #4
- 28849 | No Salt Added Black Beans | $1.29 | Canned Meals Beans | ranked #5

## cheese - Shredded cheese - 1 unit(s) - core - query 'shredded cheese'
- 13176 | Bag of Organic Bananas | $2.49 | Fresh Fruits | yours, bought 5x
- 46575 | Organic Finely Shredded Cheddar Cheese | $3.99 | Packaged Cheese | ranked #1
- 31343 | Shredded Mild Cheddar Cheese | $2.99 | Packaged Cheese | ranked #2
- 41178 | Natural Finely Shredded Triple Cheddar Cheese | $3.49 | Packaged Cheese | ranked #3
- 22750 | Finely Shredded Mild Cheddar Cheese | $2.99 | Packaged Cheese | ranked #4
- 12078 | Shredded Mexican Blend Cheese | $2.99 | Packaged Cheese | ranked #5

## salsa - Salsa - 1 unit(s) - core - query 'salsa'
- 13535 | Organic Medium Salsa | $4.49 | Preserved Dips Spreads | ranked #1
- 40501 | Salsa, Verde, Roasted | $3.99 | Fresh Dips Tapenades | ranked #2
- 40408 | SALSA        FRNTR CHPTL SALSA | $4.49 | Preserved Dips Spreads | ranked #3
- 42315 | Tomatillo | $0.79 | Fresh Vegetables | ranked #4
- 41433 | Fresh Roasted Tomate & Chile Asado Medium Salsa | $3.99 | Fresh Dips Tapenades | ranked #5

## avocado - Avocados (3) - 3 unit(s) - core - query 'avocado'
- 47766 | Organic Avocado | $1.79 | Fresh Fruits | yours, bought 18x
- 6972 | Mayo Made With Avocado Oil | $5.49 | Condiments | yours, bought 6x
- 31391 | Gourmet Delicate Avocado Oil | $9.49 | Oils Vinegars | yours, bought 4x
- 47209 | Organic Hass Avocado | $1.99 | Fresh Fruits | ranked #1
- 5450 | Small Hass Avocado | $0.99 | Fresh Fruits | ranked #2
- 38739 | Hass Avocado | $1.19 | Fresh Vegetables | ranked #3
- 12341 | Hass Avocados | $1.29 | Packaged Produce | ranked #4
- 39001 | Organic Avocados Hass Variety | $1.49 | Fresh Fruits | ranked #5

## lettuce - Lettuce - 1 unit(s) - optional - query 'romaine lettuce'
- 41220 | Organic Romaine Lettuce | $2.49 | Fresh Vegetables | ranked #1
- 40516 | Organic Romaine Hearts | $4.49 | Packaged Vegetables Fruits | ranked #2
- 11140 | Organic Romaine Leaf | $2.49 | Packaged Vegetables Fruits | ranked #3
- 17795 | Organic Green Leaf Lettuce | $2.49 | Fresh Vegetables | ranked #4
- 26497 | Romaine Lettuce | $1.99 | Fresh Vegetables | ranked #5

## tomatoes - Tomatoes - 2 unit(s) - optional - query 'tomatoes'
- 405 | 100% Organic Diced Tomatoes | $1.99 | Canned Jarred Vegetables | yours, bought 2x
- 26369 | Organic Roma Tomato | $2.49 | Fresh Vegetables | ranked #1
- 47042 | Organic Red On the Vine Tomato | $3.49 | Fresh Vegetables | ranked #2
- 29487 | Roma Tomato | $1.79 | Fresh Vegetables | ranked #3
- 12980 | Large Greenhouse Tomato | $1.79 | Fresh Vegetables | ranked #4
- 8048 | Packaged Grape Tomatoes | $2.99 | Packaged Produce | ranked #5

## limes - Limes - 2 unit(s) - optional - query 'limes'
- 26209 | Limes | $0.39 | Fresh Fruits | ranked #1
- 44750 | Organic Lime | $0.49 | Fresh Fruits | ranked #2
- 8953 | Key Limes | $0.19 | Packaged Produce | ranked #3
- 7969 | Lime | $0.39 | Fresh Fruits | ranked #4
- 32677 | Bag of Key Limes | $2.99 | Fresh Fruits | ranked #5

## sour_cream - Sour cream - 1 unit(s) - optional - query 'sour cream'
- 13176 | Bag of Organic Bananas | $2.49 | Fresh Fruits | yours, bought 5x
- 42701 | Organic Sour Cream | $3.49 | Other Creams Cheeses | ranked #1
- 27323 | Pure & Natural Sour Cream | $2.49 | Other Creams Cheeses | ranked #2
- 17803 | Organic Cultured Sour Cream | $3.49 | Other Creams Cheeses | ranked #3
- 45842 | Natural Sour Cream | $2.49 | Other Creams Cheeses | ranked #4
- 29295 | Organic Lowfat Sour Cream | $3.29 | Other Creams Cheeses | ranked #5

## spices (Cumin and chili powder) - pantry, not searched

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
            405,
            5450,
            6972,
            7969,
            8048,
            8953,
            11140,
            12078,
            12341,
            12980,
            13176,
            13535,
            14267,
            17795,
            17803,
            19816,
            22750,
            25686,
            26209,
            26369,
            26497,
            27156,
            27323,
            28849,
            28883,
            29295,
            29487,
            31343,
            31378,
            31391,
            32677,
            35042,
            36256,
            38739,
            39001,
            40408,
            40501,
            40516,
            41178,
            41220,
            41433,
            42315,
            42701,
            44750,
            45842,
            46575,
            47042,
            47209,
            47766,
            49175
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
         405,
         5450,
         6972,
         7969,
         8048,
         8953,
         11140,
         12078,
         12341,
         12980,
         13176,
         13535,
         14267,
         17795,
         17803,
         19816,
         22750,
         25686,
         26209,
         26369,
         26497,
         27156,
         27323,
         28849,
         28883,
         29295,
         29487,
         31343,
         31378,
         31391,
         32677,
         35042,
         36256,
         38739,
         39001,
         40408,
         40501,
         40516,
         41178,
         41220,
         41433,
         42315,
         42701,
         44750,
         45842,
         46575,
         47042,
         47209,
         47766,
```
