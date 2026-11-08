"""Intent -> generated basket: "tacos for 4 on friday, under $40" becomes a screen.

  1. context   the shopper (label, blurb) and their regulars, from the running backend
  2. plan      Claude turns the intent into needs (one search query each), servings,
               budget and diet constraints  (tool `plan_basket`)
  3. ground    one personalized /api/search per need, in parallel: BehaviorGPT picks
               which exact products this shopper would take for each need, and the
               shopper's own past items for it come first ("yours")
  4. compose   Claude lays out the screen in the ui_schema.json vocabulary, choosing
               only among the ids step 3 returned  (tool `render_ui`; product_id is an
               enum of those ids, so with strict tool use it cannot invent one)
  5. validate  schema, ids, need coverage, duplicates, budget (summed here, never by
               the model); one repair turn with the errors, then a deterministic repair
  6. hydrate   ids -> full products (FeedItem shape) and print a readable rendering

LLM modes:
  --llm api      Anthropic Messages API over httpx (the SDK is not installed here).
                 Needs ANTHROPIC_API_KEY in the repo-root .env.
  --llm replay   No API call. Reads <out>/plan_basket.json and <out>/render_ui.json if
                 present; otherwise writes the exact prompt it would have sent to
                 <out>/<tool>.prompt.md and stops (plan) or falls back (compose). Lets
                 an in-session Claude act as the model, and makes runs reproducible.
  --llm none     Deterministic plan is impossible without a model, so this needs an
                 existing plan_basket.json; compose is the rule-based fallback.

Every run also writes the rule-based composition (spec_fallback.json) for comparison:
it is what the app would show if Claude is slow or down.

Usage:
  prototype/.venv/bin/python prototype/genui/intent_basket.py \
      --shopper 165391 --intent "tacos for 4 on friday, under 40 dollars" [--budget 40] \
      [--llm api|replay|none] [--model claude-sonnet-5-5] [--out DIR]
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "ui_schema.json").read_text())
BACKEND = os.environ.get("GENUI_BACKEND", "http://localhost:8000")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
YOURS_PER_NEED = 3  # the shopper's own items for a need
RESULTS_PER_NEED = 5  # BehaviorGPT's personalized ranking of the catalog for it
MAX_NEEDS = 10


# --- 0. bookkeeping ----------------------------------------------------------------------


class Meter:
    """Wall-clock per phase and a count of every outbound call."""

    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.phases: dict[str, float] = {}
        self.calls = {"backend": 0, "behaviorgpt_est": 0, "llm": 0}
        self.llm: list[dict] = []

    def phase(self, name: str, started: float) -> None:
        self.phases[name] = round(time.perf_counter() - started, 2)

    def total(self) -> float:
        return round(time.perf_counter() - self.t0, 2)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# --- 1. context --------------------------------------------------------------------------


def get(client: httpx.Client, meter: Meter, path: str, **params) -> dict | list:
    meter.calls["backend"] += 1
    r = client.get(f"{BACKEND}{path}", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def shopper_context(client: httpx.Client, meter: Meter, shopper_id: int) -> dict:
    with ThreadPoolExecutor(2) as pool:
        shoppers_f = pool.submit(get, client, meter, "/api/shoppers")
        feed_f = pool.submit(get, client, meter, "/api/feed", shopper_id=shopper_id)
        shoppers, feed = shoppers_f.result(), feed_f.result()
    meter.calls["behaviorgpt_est"] += 2  # the feed ranks the shopper's items and pairs
    me = next(s for s in shoppers if s["id"] == shopper_id)
    regulars = next((s for s in feed["sections"] if s["kind"] == "regulars"), {"items": []})
    return {
        "id": shopper_id,
        "label": me["label"],
        "blurb": me["blurb"],
        "days_since_last_order": feed.get("days_since_last_order"),
        "regulars": [
            f"{i['product']['name']} ({money(i['product']['price_cents'])}; {i['reason']})"
            for i in regulars["items"][:12]
        ],
    }


# --- 2./4. the model ---------------------------------------------------------------------

PLAN_TOOL = {
    "name": "plan_basket",
    "description": "Turn a shopper's free-text grocery intent into a shopping plan: one entry per thing to buy, each with a short store search query.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "servings", "budget_cents", "constraints", "needs", "assumptions"],
        "properties": {
            "title": {"type": "string", "description": "Short screen title, e.g. 'Taco night for 4'."},
            "servings": {"type": "integer", "description": "People or portions to cover (1 if not food for a meal)."},
            "budget_cents": {
                "type": ["integer", "null"],
                "description": "Budget in cents if the intent states or clearly implies one, else null.",
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Diet, price or style constraints read from the intent and history ('vegetarian', 'cheap', 'kid friendly').",
            },
            "needs": {
                "type": "array",
                "description": "At most 10. Core items first.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["key", "label", "query", "units", "role"],
                    "properties": {
                        "key": {"type": "string", "description": "snake_case id, e.g. 'tortillas'."},
                        "label": {"type": "string", "description": "What the shopper reads: 'Tortillas (12-16)'."},
                        "query": {
                            "type": "string",
                            "description": "1-3 plain grocery words the store catalog would use ('corn tortillas', 'shredded cheese'). No brands, no 'organic' unless the shopper asked: the search is already personalized.",
                        },
                        "units": {"type": "integer", "description": "How many packs/items to buy for the servings."},
                        "role": {
                            "enum": ["core", "optional", "pantry"],
                            "description": "core: the intent fails without it. optional: nice to have, first to drop for budget. pantry: most homes have it (salt, oil, spices) - not searched, offered as 'already at home?'.",
                        },
                    },
                },
            },
            "assumptions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Assumptions worth telling the shopper ('Beef tacos; tap Vegetarian to switch').",
            },
        },
    },
}

PLAN_SYSTEM = """You plan grocery purchases for an online grocery store (the Instacart catalog, US, 2017 prices).
Read the shopper's intent and their history, then call plan_basket. Be concrete and frugal: the fewest needs that
make the intent work, quantities sized to the servings, pantry staples marked as pantry. Respect stated budgets and
diets; infer diet only from strong evidence in the history (e.g. no meat at all, tofu every trip) and say so in
assumptions. Search queries must be plain catalog words, one product type each."""

COMPOSE_SYSTEM = """You compose the screen a grocery shopper sees after typing an intent, then call render_ui.
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
Never write product names into notes that are not in the candidates. Do not compute totals in copy; the app shows them."""


def strict_safe(schema: dict) -> dict:
    """Inline $refs and drop keywords strict tool use may reject; the validator still checks them."""
    defs = schema.get("$defs", {})
    drop = {"minimum", "maximum", "maxLength", "minItems", "maxItems", "$id", "description"}

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k not in drop and k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def render_tool(allowed_ids: list[int]) -> dict:
    schema = copy.deepcopy(SCHEMA)
    schema["$defs"]["product_id"] = {"type": "integer", "enum": sorted(allowed_ids)}
    return {
        "name": "render_ui",
        "description": "Render the generated grocery screen. Only candidate product ids are valid.",
        "input_schema": strict_safe(schema),
    }


class NeedsModel(Exception):
    """Replay mode has no stored answer for this tool; the prompt was written to disk."""


class LLM:
    def __init__(self, mode: str, model: str, out: Path, meter: Meter) -> None:
        self.mode, self.model, self.out, self.meter = mode, model, out, meter
        self.key = os.environ.get("ANTHROPIC_API_KEY", "")
        if mode == "api" and not self.key:
            sys.exit("ANTHROPIC_API_KEY is empty in .env: use --llm replay, or set the key.")

    def call(self, tool: dict, system: str, messages: list[dict], name: str | None = None) -> dict:
        name = name or tool["name"]
        stored = self.out / f"{name}.json"
        if self.mode != "api":
            prompt = self.out / f"{name}.prompt.md"
            prompt.write_text(
                f"# system\n\n{system}\n\n"
                + "".join(f"# {m['role']}\n\n{_text(m['content'])}\n\n" for m in messages)
                + f"# tool (forced): {tool['name']}\n\n```json\n{json.dumps(tool['input_schema'], indent=1)[:4000]}\n```\n"
            )
            if stored.exists():
                return json.loads(stored.read_text())
            raise NeedsModel(str(prompt))
        return self._api(tool, system, messages, name, stored)

    def _api(self, tool, system, messages, name, stored, strict=True) -> dict:
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system,
            "tools": [{**tool, "strict": True} if strict else tool],
            "tool_choice": {"type": "tool", "name": tool["name"]},
            "messages": messages,
        }
        headers = {
            "x-api-key": self.key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        t = time.perf_counter()
        self.meter.calls["llm"] += 1
        r = httpx.post(ANTHROPIC_URL, headers=headers, json=body, timeout=120)
        if r.status_code == 400 and strict:  # strict tool use not accepted for this schema/model
            print(f"  [{name}] strict tool use rejected ({r.json()['error']['message'][:120]}); retrying non-strict")
            return self._api(tool, system, messages, name, stored, strict=False)
        r.raise_for_status()
        data = r.json()
        block = next(b for b in data["content"] if b["type"] == "tool_use")
        self.meter.llm.append(
            {
                "call": name,
                "model": self.model,
                "strict": strict,
                "seconds": round(time.perf_counter() - t, 2),
                "input_tokens": data["usage"]["input_tokens"],
                "output_tokens": data["usage"]["output_tokens"],
            }
        )
        stored.write_text(json.dumps(block["input"], indent=1))
        return block["input"]


def _text(content) -> str:
    return content if isinstance(content, str) else json.dumps(content, indent=1)


# --- 3. grounding ------------------------------------------------------------------------


def ground(client: httpx.Client, meter: Meter, shopper_id: int, plan: dict, cache: Path) -> dict:
    """{need_key: [candidate, ...]} from one personalized search per searched need."""
    if cache.exists():  # replay: same candidates as the run the stored answers were made for
        cached = json.loads(cache.read_text())
        meter.calls["backend"] += len(cached["candidates"])
        meter.calls["behaviorgpt_est"] += 3 * len(cached["candidates"])
        meter.phases["ground"] = cached["seconds"]
        return cached
    needs = [n for n in plan["needs"][:MAX_NEEDS] if n["role"] != "pantry"]
    started = time.perf_counter()

    def one(need: dict) -> tuple[str, list[dict], float]:
        t = time.perf_counter()
        res = get(client, meter, "/api/search", shopper_id=shopper_id, q=need["query"])
        seen: set[int] = set()
        out: list[dict] = []
        for src, rows, k in (("yours", res["yours"], YOURS_PER_NEED), ("ranked", res["results"], RESULTS_PER_NEED)):
            for rank, row in enumerate(rows[:k], 1):
                p = row["product"]
                if p["id"] in seen:
                    continue
                seen.add(p["id"])
                bought = re.search(r"(\d+)×", row["reason"])
                out.append(
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "price_cents": p["price_cents"],
                        "aisle": p["aisle"],
                        "times_bought": int(bought.group(1)) if bought else 0,
                        "source": src,
                        "rank": rank,
                        "product": p,
                    }
                )
        return need["key"], out, round(time.perf_counter() - t, 2)

    with ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(one, needs))
    meter.calls["behaviorgpt_est"] += 3 * len(needs)  # per search: anonymous, personal, for-you
    result = {
        "candidates": {k: c for k, c, _ in rows},
        "search_seconds": {k: s for k, _, s in rows},
        "seconds": round(time.perf_counter() - started, 2),
    }
    cache.write_text(json.dumps(result, indent=1))
    return result


def candidates_prompt(plan: dict, cands: dict[str, list[dict]]) -> str:
    lines = []
    for need in plan["needs"]:
        if need["role"] == "pantry":
            lines.append(f"\n## {need['key']} ({need['label']}) - pantry, not searched")
            continue
        lines.append(f"\n## {need['key']} - {need['label']} - {need['units']} unit(s) - {need['role']} - query '{need['query']}'")
        for c in cands.get(need["key"], []):
            mine = f"yours, bought {c['times_bought']}x" if c["times_bought"] else f"{c['source']} #{c['rank']}"
            lines.append(f"- {c['id']} | {c['name']} | {money(c['price_cents'])} | {c['aisle']} | {mine}")
        if not cands.get(need["key"]):
            lines.append("- (no candidates)")
    return "\n".join(lines)


# --- 4b. rule-based composition (fallback and baseline) -------------------------------


def _on_topic(c: dict, query: str) -> bool:
    words = [w.rstrip("s") for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2]
    name = c["name"].lower()
    return any(w in name for w in words)


def compose_rules(plan: dict, cands: dict[str, list[dict]], budget: int | None) -> dict:
    """The shopper's own item for each need if they have one, else BehaviorGPT's top
    on-topic pick; swaps = cheapest alternative and their usual; then fit the budget."""
    items, swaps = [], []
    for need in plan["needs"]:
        pool = cands.get(need["key"], [])
        if not pool:
            continue
        topical = [c for c in pool if _on_topic(c, need["query"])] or pool
        pick = topical[0]  # 'yours' rows come first, most bought first
        items.append(
            {
                "product_id": pick["id"],
                "quantity": max(1, min(need["units"], 12)),
                "need_key": need["key"],
                "note": f"Your usual, bought {pick['times_bought']}x" if pick["times_bought"] else f"#{pick['rank']} for you",
                "tag": "usual" if pick["times_bought"] else "new",
            }
        )
        cheaper = min((c for c in topical if c["id"] != pick["id"]), key=lambda c: c["price_cents"], default=None)
        if cheaper and cheaper["price_cents"] < pick["price_cents"]:
            swaps.append(
                {
                    "type": "swap_row",
                    "for_product_id": pick["id"],
                    "options": [{"product_id": cheaper["id"], "label": "cheaper", "note": f"Saves {money(pick['price_cents'] - cheaper['price_cents'])} each"}],
                }
            )
    spec = {
        "title": plan["title"][:60],
        "blocks": [
            {"type": "header", "title": plan["title"][:60], "subtitle": "Picked from your past orders and what shoppers like you buy"[:140]},
            *([{"type": "budget_meter", "budget_cents": budget}] if budget else []),
            {
                "type": "basket_section",
                "key": "intent",
                "title": plan["title"][:60],
                "subtitle": f"{len(items)} things for {plan['servings']}"[:120],
                "reason": "One personalized search per ingredient"[:160],
                "confidence": "good",
                "items": items,
            },
            *swaps[:3],
        ],
    }
    pantry = [n for n in plan["needs"] if n["role"] == "pantry"]
    if pantry:
        spec["blocks"].append(
            {"type": "pantry_check", "prompt": "Already at home?", "needs": [{"need_key": n["key"], "label": n["label"][:40]} for n in pantry][:8]}
        )
    return spec


# --- 5. validation and repair ------------------------------------------------------------


def check(node, schema: dict, path: str, errors: list[str]) -> None:
    """The subset of JSON Schema ui_schema.json uses (jsonschema isn't installed)."""
    if "$ref" in schema:
        schema = SCHEMA["$defs"][schema["$ref"].split("/")[-1]]
    if "anyOf" in schema:
        options = [SCHEMA["$defs"][s["$ref"].split("/")[-1]] if "$ref" in s else s for s in schema["anyOf"]]
        kind = node.get("type") if isinstance(node, dict) else None
        match = [o for o in options if o.get("properties", {}).get("type", {}).get("const") == kind]
        if not match:
            errors.append(f"{path}: unknown block type {kind!r}")
            return
        schema = match[0]
    if "const" in schema and node != schema["const"]:
        errors.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and node not in schema["enum"]:
        errors.append(f"{path}: {node!r} not in {schema['enum'][:8]}")
    types = schema.get("type")
    if types:
        types = types if isinstance(types, list) else [types]
        ok = {
            "object": isinstance(node, dict),
            "array": isinstance(node, list),
            "string": isinstance(node, str),
            "integer": isinstance(node, int) and not isinstance(node, bool),
            "boolean": isinstance(node, bool),
            "null": node is None,
        }
        if not any(ok[t] for t in types):
            errors.append(f"{path}: expected {types}, got {type(node).__name__}")
            return
    if isinstance(node, str) and len(node) > schema.get("maxLength", 10**9):
        errors.append(f"{path}: longer than {schema['maxLength']} chars")
    if isinstance(node, int) and not isinstance(node, bool):
        if node < schema.get("minimum", -(10**12)) or node > schema.get("maximum", 10**12):
            errors.append(f"{path}: {node} out of range")
    if isinstance(node, list):
        if len(node) > schema.get("maxItems", 10**9) or len(node) < schema.get("minItems", 0):
            errors.append(f"{path}: {len(node)} items, allowed {schema.get('minItems', 0)}-{schema.get('maxItems')}")
        for i, v in enumerate(node):
            check(v, schema.get("items", {}), f"{path}[{i}]", errors)
    if isinstance(node, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in node:
                errors.append(f"{path}: missing {k!r}")
        for k, v in node.items():
            if k in props:
                check(v, props[k], f"{path}.{k}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected {k!r}")


def basket_items(spec: dict) -> list[dict]:
    return [it for b in spec["blocks"] if b.get("type") == "basket_section" for it in b.get("items", [])]


def total_cents(spec: dict, products: dict[int, dict]) -> int:
    return sum(products[it["product_id"]]["price_cents"] * it["quantity"] for it in basket_items(spec) if it["product_id"] in products)


def validate(spec: dict, plan: dict, cands: dict[str, list[dict]], budget: int | None) -> list[str]:
    errors: list[str] = []
    check(spec, SCHEMA, "$", errors)
    if errors:
        return errors
    products = {c["id"]: c for pool in cands.values() for c in pool}
    by_need = {k: {c["id"] for c in pool} for k, pool in cands.items()}
    picked: list[int] = []
    for i, it in enumerate(basket_items(spec)):
        pid = it["product_id"]
        if pid not in products:
            errors.append(f"item {i}: product {pid} was not a candidate (hallucinated id)")
        elif it["need_key"] in by_need and pid not in by_need[it["need_key"]]:
            errors.append(f"item {i}: product {pid} is not a candidate for need {it['need_key']!r}")
        elif it["need_key"] not in by_need:
            errors.append(f"item {i}: unknown need_key {it['need_key']!r}")
        picked.append(pid)
    dupes = {p for p in picked if picked.count(p) > 1}
    if dupes:
        errors.append(f"duplicate picks {sorted(dupes)}: use quantity instead")
    covered = {it["need_key"] for it in basket_items(spec)}
    for need in plan["needs"]:
        if need["role"] == "core" and cands.get(need["key"]) and need["key"] not in covered:
            errors.append(f"core need {need['key']!r} has no pick")
    for b in spec["blocks"]:
        if b["type"] == "swap_row":
            if b["for_product_id"] not in picked:
                errors.append(f"swap_row for {b['for_product_id']}, which is not picked")
            for o in b["options"]:
                if o["product_id"] not in products or o["product_id"] == b["for_product_id"]:
                    errors.append(f"swap option {o['product_id']} invalid")
        if b["type"] == "recipe_card":
            stray = [p for p in b["product_ids"] if p not in picked]
            if stray:
                errors.append(f"recipe_card uses unpicked products {stray}")
    if budget is not None:
        total = total_cents(spec, products)
        if total > budget:
            errors.append(f"over budget: {money(total)} > {money(budget)}")
    return errors


def repair_rules(spec: dict, plan: dict, cands: dict[str, list[dict]], budget: int | None) -> dict:
    """Deterministic last resort: drop bad items and stray blocks, then cheapen until under budget."""
    spec = copy.deepcopy(spec)
    products = {c["id"]: c for pool in cands.values() for c in pool}
    by_need = {k: {c["id"] for c in pool} for k, pool in cands.items()}
    for b in spec["blocks"]:
        if b.get("type") == "basket_section":
            seen: set[int] = set()
            b["items"] = [
                it
                for it in b["items"]
                if it["product_id"] in by_need.get(it["need_key"], set()) and not (it["product_id"] in seen or seen.add(it["product_id"]))
            ]
    roles = {n["key"]: n["role"] for n in plan["needs"]}
    # Refill core needs left empty (a dropped hallucination) with the rule-based pick.
    sections = [b for b in spec["blocks"] if b.get("type") == "basket_section"]
    covered = {it["need_key"] for it in basket_items(spec)}
    if sections:
        rules_items = basket_items(compose_rules(plan, cands, None))
        taken = {it["product_id"] for it in basket_items(spec)}
        for it in rules_items:
            if roles.get(it["need_key"]) == "core" and it["need_key"] not in covered and it["product_id"] not in taken:
                sections[0]["items"].append(it)
                taken.add(it["product_id"])
    while budget is not None and total_cents(spec, products) > budget:
        best = None  # the swap to the cheapest on-topic candidate that saves the most
        for it in basket_items(spec):
            need = next(n for n in plan["needs"] if n["key"] == it["need_key"])
            pool = [c for c in cands[it["need_key"]] if _on_topic(c, need["query"])] or cands[it["need_key"]]
            cheapest = min(pool, key=lambda c: c["price_cents"])
            save = (products[it["product_id"]]["price_cents"] - cheapest["price_cents"]) * it["quantity"]
            if save > 0 and (best is None or save > best[0]):
                best = (save, it, cheapest)
        if best:
            _, it, cheapest = best
            it["product_id"], it["note"], it["tag"] = cheapest["id"], "Cheapest pick to fit the budget", "usual" if cheapest["times_bought"] else "new"
            continue
        optional = [it for it in basket_items(spec) if roles.get(it["need_key"]) == "optional"]
        victim = optional[-1] if optional else max(basket_items(spec), key=lambda it: it["quantity"])
        for b in spec["blocks"]:
            if b.get("type") == "basket_section" and victim in b["items"]:
                if victim["quantity"] > 1 and not optional:
                    victim["quantity"] -= 1
                else:
                    b["items"].remove(victim)
        if not basket_items(spec):
            break
    picked = {it["product_id"] for it in basket_items(spec)}
    spec["blocks"] = [
        b
        for b in spec["blocks"]
        if not (b.get("type") == "swap_row" and b["for_product_id"] not in picked)
        and not (b.get("type") == "basket_section" and not b["items"])
    ]
    for b in spec["blocks"]:
        if b.get("type") == "recipe_card":
            b["product_ids"] = [p for p in b["product_ids"] if p in picked]
    return spec


# --- 6. hydrate and render ---------------------------------------------------------------


def hydrate(spec: dict, cands: dict[str, list[dict]], budget: int | None) -> dict:
    """What the endpoint would return: ids replaced by full products, totals computed."""
    products = {c["id"]: c for pool in cands.values() for c in pool}
    out = copy.deepcopy(spec)
    for b in out["blocks"]:
        if b["type"] == "basket_section":
            b["kind"] = "mission"  # -> FeedSection, rendered by <Shelf>
            b["items"] = [
                {
                    "product": products[it["product_id"]]["product"],
                    "tag": it["tag"],
                    "reason": it["note"],
                    "confidence": 0.9 if it["tag"] == "usual" else 0.6,
                    "quantity": it["quantity"],
                    "need_key": it["need_key"],
                }
                for it in b["items"]
            ]
        elif b["type"] == "swap_row":
            b["for_product"] = products[b.pop("for_product_id")]["product"]
            for o in b["options"]:
                o["product"] = products[o.pop("product_id")]["product"]
        elif b["type"] == "recipe_card":
            b["products"] = [products[p]["product"] for p in b.pop("product_ids")]
        elif b["type"] == "budget_meter":
            b["spent_cents"] = total_cents(spec, products)
    return out


def render(spec: dict, cands: dict[str, list[dict]], budget: int | None) -> str:
    products = {c["id"]: c for pool in cands.values() for c in pool}
    total = total_cents(spec, products)
    lines = []
    for b in spec["blocks"]:
        t = b["type"]
        if t == "header":
            lines += [f"=== {b['title']} ===", f"    {b['subtitle']}"]
        elif t == "budget_meter":
            filled = min(20, round(20 * total / max(b["budget_cents"], 1)))
            lines.append(f"[budget] {money(total)} of {money(b['budget_cents'])}  [{'#' * filled}{'.' * (20 - filled)}]")
        elif t == "basket_section":
            lines += ["", f"[{b['title']}]  {b['subtitle']}  ({b['confidence']})", f"    why: {b['reason']}"]
            for it in b["items"]:
                p = products[it["product_id"]]
                lines.append(
                    f"  {it['quantity']} x {p['name'][:44]:<44} {money(p['price_cents']):>7} = {money(p['price_cents'] * it['quantity']):>7}"
                    f"  {it['tag']:<5} {it['note']}  <{it['need_key']}>"
                )
            lines.append(f"  {'':>4}{'total':<44} {'':>7}   {money(total):>7}")
        elif t == "swap_row":
            p = products[b["for_product_id"]]
            opts = " | ".join(f"{o['label']}: {products[o['product_id']]['name'][:34]} {money(products[o['product_id']]['price_cents'])} ({o['note']})" for o in b["options"])
            lines.append(f"  swap {p['name'][:30]} -> {opts}")
        elif t == "recipe_card":
            lines += ["", f"[recipe] {b['title']} · serves {b['servings']} · {b['minutes']} min"]
            lines += [f"  {i}. {s}" for i, s in enumerate(b["steps"], 1)]
        elif t == "pantry_check":
            lines.append(f"[{b['prompt']}] " + ", ".join(f"( ) {n['label']}" for n in b["needs"]))
        elif t == "question_chips":
            lines.append(f"[{b['prompt']}] " + "  ".join(f"<{c['label']}>" for c in b["chips"]))
        elif t == "note":
            lines.append(f"  {'!' if b['tone'] == 'warn' else 'i'} {b['text']}")
    if budget is not None:
        lines.append(f"\n(total {money(total)} vs budget {money(budget)}: {'OK' if total <= budget else 'OVER'})")
    return "\n".join(lines)


# --- main --------------------------------------------------------------------------------


def run(shopper_id: int, intent: str, budget_arg: float | None, mode: str, model: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    meter = Meter()
    llm = LLM(mode, model, out, meter)
    client = httpx.Client()

    t = time.perf_counter()
    ctx_file = out / "context.json"
    if mode != "api" and ctx_file.exists():  # replay: same prompt as the first run
        ctx = json.loads(ctx_file.read_text())
        meter.phases["context"] = ctx.pop("_seconds")
        meter.calls["backend"] += 2
        meter.calls["behaviorgpt_est"] += 2
    else:
        ctx = shopper_context(client, meter, shopper_id)
        meter.phase("context", t)
        ctx_file.write_text(json.dumps({**ctx, "_seconds": meter.phases["context"]}, indent=1))

    user = (
        f"Shopper {ctx['id']} - {ctx['label']}: {ctx['blurb']}. Last order {ctx['days_since_last_order']} days ago.\n"
        "Their regulars (most likely this trip first):\n- " + "\n- ".join(ctx["regulars"]) + f"\n\nIntent: {intent}"
        + (f"\nBudget: {money(int(budget_arg * 100))}" if budget_arg else "")
    )
    t = time.perf_counter()
    try:
        plan = llm.call(PLAN_TOOL, PLAN_SYSTEM, [{"role": "user", "content": user}])
    except NeedsModel as e:
        print(f"replay: no plan yet; prompt written to {e}")
        return 2
    meter.phase("plan", t)
    budget = int(budget_arg * 100) if budget_arg else plan.get("budget_cents")

    grounded = ground(client, meter, shopper_id, plan, out / "candidates.json")
    cands = grounded["candidates"]
    meter.phases.setdefault("ground", grounded["seconds"])

    fallback = compose_rules(plan, cands, budget)
    if validate(fallback, plan, cands, budget):
        fallback = repair_rules(fallback, plan, cands, budget)
    (out / "spec_fallback.json").write_text(json.dumps(fallback, indent=1))
    (out / "render_fallback.txt").write_text(render(fallback, cands, budget) + "\n")

    allowed = sorted({c["id"] for pool in cands.values() for c in pool})
    compose_user = (
        f"{user}\n\nPlan:\n{json.dumps({k: plan[k] for k in ('title', 'servings', 'constraints', 'assumptions')})}\n"
        f"Budget (cents): {budget}\n\nCandidates per need (id | name | unit price | aisle | history):{candidates_prompt(plan, cands)}"
    )
    t = time.perf_counter()
    source = "claude"
    try:
        if mode == "none":
            raise NeedsModel("--llm none")
        spec = llm.call(render_tool(allowed), COMPOSE_SYSTEM, [{"role": "user", "content": compose_user}])
        errors = validate(spec, plan, cands, budget)
        if errors and mode == "api":  # one repair turn, with the exact errors
            print("  compose errors, asking for a repair:", errors)
            spec = llm.call(
                render_tool(allowed),
                COMPOSE_SYSTEM,
                [
                    {"role": "user", "content": compose_user},
                    {"role": "assistant", "content": [{"type": "text", "text": json.dumps(spec)}]},
                    {"role": "user", "content": "The screen failed validation:\n- " + "\n- ".join(errors) + "\nCall render_ui again with these fixed."},
                ],
                name="render_ui_repair",
            )
            errors = validate(spec, plan, cands, budget)
        if errors:
            print("  still invalid, deterministic repair:", errors)
            spec, source = repair_rules(spec, plan, cands, budget), "claude+rules_repair"
    except NeedsModel as e:
        print(f"replay: no composition yet; prompt written to {e}; showing the rule-based one")
        spec, source = fallback, "rules"
    meter.phase("compose", t)

    final_errors = validate(spec, plan, cands, budget)
    (out / "spec.json").write_text(json.dumps(spec, indent=1))
    (out / "hydrated.json").write_text(json.dumps(hydrate(spec, cands, budget), indent=1))
    text = render(spec, cands, budget)
    (out / "render.txt").write_text(text + "\n")
    metrics = {
        "shopper": shopper_id,
        "intent": intent,
        "llm_mode": mode,
        "model": model if mode == "api" else "in-session Claude (replay; not timed)",
        "composition": source,
        "valid": not final_errors,
        "errors": final_errors,
        "needs": len(plan["needs"]),
        "searched_needs": len(cands),
        "candidates": len(allowed),
        "phases_s": meter.phases,
        "search_s_per_need": grounded.get("search_seconds"),
        "total_s": round(sum(meter.phases.values()), 2),
        "calls": meter.calls,
        "llm_calls": meter.llm,
        "prompt_chars": {"plan": len(PLAN_SYSTEM) + len(user), "compose": len(COMPOSE_SYSTEM) + len(compose_user)},
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1))
    print(text)
    print(f"\nvalid={not final_errors} composition={source} phases={meter.phases} calls={meter.calls}")
    return 0 if not final_errors else 1


def main() -> None:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shopper", type=int, required=True)
    ap.add_argument("--intent", required=True)
    ap.add_argument("--budget", type=float, help="dollars; overrides one read from the intent")
    ap.add_argument("--llm", choices=["api", "replay", "none"], default="api")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    out = a.out or HERE / "samples" / f"{a.shopper}_{slug(a.intent)}"
    sys.exit(run(a.shopper, a.intent, a.budget, a.llm, a.model, out))


if __name__ == "__main__":
    main()
