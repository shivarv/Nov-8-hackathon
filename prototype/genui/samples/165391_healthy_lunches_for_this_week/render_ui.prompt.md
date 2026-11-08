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

Intent: healthy lunches for this week

Plan:
{"title": "Healthy lunches \u00b7 Mon to Fri", "servings": 5, "constraints": ["healthy", "mostly organic", "5 weekday lunches for one"], "assumptions": ["Five weekday lunches for one: quinoa bowls and hummus wraps.", "Olive oil assumed at home: you bought it 20 days ago."]}
Budget (cents): None

Candidates per need (id | name | unit price | aisle | history):
## greens - Baby spinach - 1 unit(s) - core - query 'baby spinach'
- 21903 | Organic Baby Spinach | $4.49 | Packaged Vegetables Fruits | yours, bought 11x
- 25931 | Organic Baby Spinach Salad | $4.49 | Packaged Vegetables Fruits | ranked #1
- 18234 | Organic Spinach Bunch | $2.49 | Fresh Vegetables | ranked #2
- 35547 | Organic Baby Kale | $3.99 | Fresh Vegetables | ranked #3
- 36070 | Super Spinach! Baby Spinach, Baby Bok Choy, Sweet Baby Kale | $3.99 | Packaged Vegetables Fruits | ranked #4
- 21174 | I Heart Baby Kale | $3.49 | Packaged Vegetables Fruits | ranked #5

## hummus - Hummus - 1 unit(s) - core - query 'hummus'
- 30489 | Original Hummus | $3.49 | Fresh Dips Tapenades | ranked #1
- 44097 | Organic Original Hummus | $3.99 | Fresh Dips Tapenades | ranked #2
- 13646 | Lemon Hummus | $3.49 | Fresh Dips Tapenades | ranked #3
- 46106 | Organic Sriracha Hummus | $3.99 | Fresh Dips Tapenades | ranked #4
- 30777 | Organic Classic Hummus | $3.99 | Fresh Dips Tapenades | ranked #5

## wraps - Whole wheat wraps - 1 unit(s) - core - query 'whole wheat wraps'
- 24160 | Organic Whole Wheat Tortillas | $3.99 | Tortillas Flat Bread | ranked #1
- 36591 | 100% Whole Wheat Medium Soft Taco Flour Tortillas | $3.29 | Tortillas Flat Bread | ranked #2
- 9786 | Organic Whole Wheat Pita | $3.49 | Bread | ranked #3
- 10521 | Carb Balance Small Fajita Whole Wheat Tortillas | $2.99 | Tortillas Flat Bread | ranked #4
- 12499 | Fiber Rich Wheat Tortillas Fajita Size | $2.99 | Tortillas Flat Bread | ranked #5

## quinoa - Quinoa - 1 unit(s) - core - query 'quinoa'
- 3142 | Organic Short Grain Brown Rice | $3.99 | Grains Rice Dried Goods | yours, bought 1x
- 39485 | Organic Traditional Gluten Freen Quinoa | $4.49 | Grains Rice Dried Goods | ranked #1
- 29669 | Organic Tri-Color Blend Quinoa | $3.99 | Grains Rice Dried Goods | ranked #2
- 20776 | Organic Quinoa | $4.49 | Grains Rice Dried Goods | ranked #3
- 49156 | Organic Whole Grain Sprouted Quinoa | $4.49 | Grains Rice Dried Goods | ranked #4
- 45870 | Quinoa, Organic, Whole Grain | $4.29 | Grains Rice Dried Goods | ranked #5

## chickpeas - Chickpeas (2 cans) - 2 unit(s) - core - query 'chickpeas'
- 42768 | Organic Garbanzo Beans | $1.79 | Canned Meals Beans | ranked #1
- 35750 | Organic Garbanzo Beans No Salt Added | $1.79 | Canned Meals Beans | ranked #2
- 17634 | Chick Peas | $1.29 | Canned Meals Beans | ranked #3
- 32412 | Garbanzo Beans No Salt Added | $1.29 | Latino Foods | ranked #4
- 45854 | Garbanzos Chick Peas | $1.29 | Canned Meals Beans | ranked #5

## eggs - Eggs (for hard-boiling) - 1 unit(s) - core - query 'eggs'
- 30385 | Organic Free Range Grade A Large Brown Eggs | $4.99 | Eggs | yours, bought 18x
- 35921 | Organic Large Grade A Brown Eggs | $5.49 | Eggs | yours, bought 1x
- 16083 | Organic Large Brown Eggs | $5.49 | Eggs | ranked #1
- 26384 | Large Brown Eggs | $3.49 | Eggs | ranked #2
- 30233 | Organic Large Brown Grade AA Cage Free Eggs | $5.99 | Eggs | ranked #3
- 46654 | Organic Grade A Large Brown Eggs | $5.49 | Eggs | ranked #4
- 36550 | Organic Extra Large Grade AA Brown Eggs | $6.49 | Eggs | ranked #5

## carrots - Baby carrots - 1 unit(s) - optional - query 'baby carrots'
- 42265 | Organic Baby Carrots | $2.29 | Packaged Vegetables Fruits | yours, bought 11x
- 13176 | Bag of Organic Bananas | $2.49 | Fresh Fruits | yours, bought 5x
- 43961 | Organic Peeled Whole Baby Carrots | $2.49 | Packaged Vegetables Fruits | yours, bought 3x
- 22849 | Bunny-Luv Fresh Organic Carrots | $2.99 | Packaged Vegetables Fruits | ranked #1
- 16759 | Organic Carrot Bunch | $2.49 | Fresh Vegetables | ranked #2
- 32851 | Organic Carrots Baby Peeled Prepacked | $2.99 | Packaged Vegetables Fruits | ranked #3
- 17794 | Carrots | $1.99 | Fresh Vegetables | ranked #4
- 28413 | Bunny-Luv Organic Carrots | $2.99 | Fresh Vegetables | ranked #5

## cucumber - Cucumbers - 2 unit(s) - optional - query 'cucumber'
- 13292 | Juice Beverage, Cold Pressed, Kale Apple Ginger Romaine Spinach Cucumber Celery Parsley Lemon | $4.99 | Refrigerated | yours, bought 1x
- 10385 | Organic English Cucumber | $1.49 | Fresh Vegetables | ranked #1
- 30391 | Organic Cucumber | $1.49 | Fresh Vegetables | ranked #2
- 45 | European Cucumber | $1.49 | Fresh Vegetables | ranked #3
- 36695 | Organic Hothouse Cucumbers | $1.49 | Fresh Vegetables | ranked #4
- 4562 | English Seedless Cucumber | $1.49 | Fresh Vegetables | ranked #5

## feta - Feta - 1 unit(s) - optional - query 'feta cheese'
- 40604 | Feta Cheese Crumbles | $2.99 | Packaged Cheese | ranked #1
- 20887 | Feta Crumbles Cheese | $3.49 | Packaged Cheese | ranked #2
- 38291 | Traditional Crumbled Feta Cheese | $2.99 | Packaged Cheese | ranked #3
- 8362 | Feta Cheese | $3.49 | Packaged Cheese | ranked #4
- 2408 | Feta Crumbled Traditional Cheese | $2.99 | Packaged Cheese | ranked #5

## olive_oil (Olive oil and lemon) - pantry, not searched

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
            45,
            2408,
            3142,
            4562,
            8362,
            9786,
            10385,
            10521,
            12499,
            13176,
            13292,
            13646,
            16083,
            16759,
            17634,
            17794,
            18234,
            20776,
            20887,
            21174,
            21903,
            22849,
            24160,
            25931,
            26384,
            28413,
            29669,
            30233,
            30385,
            30391,
            30489,
            30777,
            32412,
            32851,
            35547,
            35750,
            35921,
            36070,
            36550,
            36591,
            36695,
            38291,
            39485,
            40604,
            42265,
            42768,
            43961,
            44097,
            45854,
            45870,
            46106,
            46654,
            49156
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
         45,
         2408,
         3142,
         4562,
         8362,
         9786,
         10385,
         10521,
         12499,
         13176,
         13292,
         13646,
         16083,
         16759,
         17634,
         17794,
         18234,
         20776,
         20887,
         21174,
         21903,
         22849,
         24160,
         25931,
         26384,
         28413,
         29669,
         30233,
         30385,
         30391,
         30489,
         30777,
         32412,
         32851,
         35547,
         35750,
         35921,
         36070,
         36550,
         36591,
         36695,
         38291,
         39485,
         40604,
         42265,
        
```
