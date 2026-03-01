#!/usr/bin/env python3
"""
Weekly lunch menu scraper for Helsinki restaurants.
Fetches menus from Puotilan Kartano and Villa Nepal Helsinki,
uses Claude API to parse free-text into structured JSON,
and writes the result to docs/menus.json for the dashboard.
"""

import json
import re
import os
import sys
from datetime import date, timedelta
import anthropic
import httpx
from bs4 import BeautifulSoup

# ── Configuration ────────────────────────────────────────────────────────────

RESTAURANTS = [
    {
        "id": "puotilan_kartano",
        "name": "Puotilan Kartano",
        "address": "Puotilantie 7, 00910 Helsinki",
        "url": "https://www.puotilankartano.fi/ruoka/lounas/",
        "hours": "11:00–14:30",
        "parse_method": "claude",  # free-text, needs LLM parsing
    },
    {
        "id": "villa_nepal",
        "name": "Villa Nepal Helsinki",
        "address": "Kauppakartanonkatu 3, 00930 Helsinki",
        "url": "https://restadeal.fi/menu/15/1/lunch?name=Villa%20Nepal%20Helsinki",
        "hours": "10:30–21:00",
        "parse_method": "structured",  # DOM-parseable
    },
]

DAYS_FI = {1: "Maanantai", 2: "Tiistai", 3: "Keskiviikko", 4: "Torstai", 5: "Perjantai"}

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "menus.json")

# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LunchBot/1.0)"}
    resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=20)
    resp.raise_for_status()
    return resp.text


def get_week_label() -> str:
    """Return a label like '2.3.–6.3.2026' for the current Mon–Fri week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    if monday.month == friday.month:
        return f"{monday.day}.–{friday.day}.{friday.month}.{friday.year}"
    return f"{monday.day}.{monday.month}.–{friday.day}.{friday.month}.{friday.year}"


# ── Puotilan Kartano — Claude-assisted parsing ────────────────────────────────

def parse_puotilan_kartano(html: str) -> dict:
    """Extract the lunch menu text and ask Claude to structure it."""
    soup = BeautifulSoup(html, "html.parser")

    # Grab the main content area — the menu lives in the page body
    # Remove nav and footer noise
    for tag in soup.select("nav, header, footer, script, style"):
        tag.decompose()

    text = soup.get_text(separator="\n")
    # Trim to the relevant section
    start = text.find("SALAATTIPÖYTÄ")
    if start == -1:
        start = text.find("Lounasmenu")
    end = text.find("HINTA:")
    if end == -1:
        end = start + 3000
    menu_text = text[start:end+500].strip()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""Below is the weekly lunch menu text from a Finnish restaurant (Puotilan Kartano).
Extract and return ONLY a JSON object with this exact structure — no explanation, no markdown:

{{
  "week_label": "e.g. 2.3.–6.3.2026",
  "prices": ["Lounas 15 €", "Keittolounas 13 €"],
  "common_items": ["item1", "item2"],
  "daily_menus": {{
    "1": {{ "soups": ["..."], "mains": ["...", "..."], "vegan": ["..."] }},
    "2": {{ "soups": ["..."], "mains": ["...", "..."], "vegan": null }},
    "3": {{ "soups": ["..."], "mains": ["...", "..."], "vegan": null }},
    "4": {{ "soups": ["..."], "mains": ["...", "..."], "vegan": ["..."] }},
    "5": {{ "soups": ["..."], "mains": ["...", "..."], "vegan": ["..."] }}
  }}
}}

Keys 1–5 = Monday–Friday. common_items = salad bar items available every day.
Keep dietary tags like (L,G), (VGN,G) inline in the item strings.
If vegan is not listed for a day, set it to null.

MENU TEXT:
{menu_text}
"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    parsed = json.loads(raw)
    return parsed


# ── Villa Nepal — DOM parsing ─────────────────────────────────────────────────

def parse_villa_nepal(html: str) -> dict:
    """Parse Villa Nepal's structured daily menu sections."""
    soup = BeautifulSoup(html, "html.parser")

    daily_menus = {}
    day_map = {
        "maanantai": "1",
        "tiistai": "2",
        "keskiviikko": "3",
        "torstai": "4",
        "perjantai": "5",
    }

    # Each day section is an <h4> followed by dish <h3> blocks
    current_day = None
    for tag in soup.find_all(["h4", "h3", "p"]):
        text = tag.get_text(strip=True).lower()

        # Detect day header
        for day_fi, day_num in day_map.items():
            if text == day_fi:
                current_day = day_num
                if current_day not in daily_menus:
                    daily_menus[current_day] = {"mains": []}
                break

        # Capture dish entries
        if current_day and tag.name == "h3":
            title = tag.get_text(strip=True)
            if not title or title.lower() in day_map:
                continue

            # Grab dietary tags and price from sibling <p> and nearby elements
            desc = ""
            price = ""
            parent = tag.find_parent()
            if parent:
                # description is usually in a <p> sibling
                p = tag.find_next_sibling("p")
                if p:
                    desc = p.get_text(strip=True)
                # price is usually in an element with € sign
                price_el = parent.find(string=re.compile(r"€\d"))
                if price_el:
                    price = price_el.strip()

            # Extract tags from the heading (e.g. "(G)" or "(L,G)")
            tag_match = re.search(r"\(([\w,\s]+)\)", title)
            tags = tag_match.group(0) if tag_match else ""
            clean_title = re.sub(r"\s*\([\w,\s]+\)\s*", " ", title).strip()

            item_str = clean_title
            if desc:
                item_str += f" — {desc}"
            if tags:
                item_str += f" {tags}"
            if price:
                item_str += f" · {price}"

            daily_menus[current_day]["mains"].append(item_str)

    return {
        "week_label": get_week_label(),
        "prices": ["alkaen 9,20 €"],
        "common_items": [],
        "daily_menus": daily_menus,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def scrape_all() -> list:
    results = []

    for restaurant in RESTAURANTS:
        print(f"Fetching: {restaurant['name']} ...")
        try:
            html = fetch_html(restaurant["url"])

            if restaurant["parse_method"] == "claude":
                menu_data = parse_puotilan_kartano(html)
            else:
                menu_data = parse_villa_nepal(html)

            results.append({
                "id": restaurant["id"],
                "name": restaurant["name"],
                "address": restaurant["address"],
                "url": restaurant["url"],
                "hours": restaurant["hours"],
                "week_label": menu_data.get("week_label", get_week_label()),
                "prices": menu_data.get("prices", []),
                "common_items": menu_data.get("common_items", []),
                "daily_menus": menu_data.get("daily_menus", {}),
            })
            print(f"  ✓ Parsed successfully")

        except Exception as e:
            print(f"  ✗ Error: {e}", file=sys.stderr)
            results.append({
                "id": restaurant["id"],
                "name": restaurant["name"],
                "address": restaurant["address"],
                "url": restaurant["url"],
                "hours": restaurant["hours"],
                "week_label": get_week_label(),
                "prices": [],
                "common_items": [],
                "daily_menus": {},
                "error": str(e),
            })

    return results


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    print(f"Scraping menus for week {get_week_label()} ...")
    data = {
        "scraped_at": date.today().isoformat(),
        "week_label": get_week_label(),
        "restaurants": scrape_all(),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
