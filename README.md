# 🍽 Lounasdashboard

A self-updating weekly lunch menu dashboard for nearby Helsinki restaurants.
Hosted on **GitHub Pages**, refreshed automatically every **Monday at 07:00 Helsinki time** via **GitHub Actions**.

**Restaurants currently tracked:**
- Puotilan Kartano (Puotilantie 7)
- Villa Nepal Helsinki (Kauppakartanonkatu 3)

---

## How it works

```
Every Monday 07:00 (Helsinki)
        │
        ▼
GitHub Actions runs scrape.py
        │
        ├── Fetches Puotilan Kartano HTML → Claude API parses free-text menu → JSON
        └── Fetches Villa Nepal HTML → BeautifulSoup parses structured DOM → JSON
        │
        ▼
Writes docs/menus.json → commits to repo
        │
        ▼
GitHub Pages re-deploys docs/index.html (reads menus.json on load)
```

---

## Setup (one-time, ~10 minutes)

### 1. Create the GitHub repository

```bash
gh repo create lunch-dashboard --public
cd lunch-dashboard
git init
# copy all files here
git add .
git commit -m "initial commit"
git push -u origin main
```

Or just upload the files via github.com → New repository → upload files.

### 2. Add your Anthropic API key as a secret

This is used by the scraper to parse Puotilan Kartano's free-text menu.

1. Go to your repo on GitHub
2. **Settings → Secrets and variables → Actions → New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: your key from console.anthropic.com

### 3. Enable GitHub Pages

1. Go to **Settings → Pages**
2. Source: **GitHub Actions**
3. Save

### 4. Enable GitHub Actions

Go to the **Actions** tab in your repo and click **"I understand my workflows, go ahead and enable them"** if prompted.

### 5. Trigger the first scrape manually

Go to **Actions → Scrape Weekly Menus → Run workflow** to fetch this week's menus right away.
After it completes, your dashboard will be live at:

```
https://<your-github-username>.github.io/lunch-dashboard/
```

---

## Running the scraper locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python scrape.py
```

This writes `docs/menus.json`. Open `docs/index.html` in a browser to preview.

---

## Adding more restaurants

Edit `scrape.py` and add an entry to the `RESTAURANTS` list:

```python
{
    "id": "my_restaurant",
    "name": "My Restaurant",
    "address": "Somestreet 1, 00100 Helsinki",
    "url": "https://example.com/lunch",
    "hours": "11:00–14:00",
    "parse_method": "claude",  # or "structured" if DOM is clean
}
```

For `parse_method: "claude"`, the scraper will extract all page text and ask Claude
to identify the weekly menu structure. For `"structured"`, you'll need to add a custom
`parse_*` function (see `parse_villa_nepal` as a template).

---

## File structure

```
lunch-dashboard/
├── .github/
│   └── workflows/
│       └── scrape.yml      ← GitHub Actions: runs every Monday
├── docs/
│   ├── index.html          ← The dashboard (served by GitHub Pages)
│   └── menus.json          ← Menu data (auto-updated by scraper)
├── scrape.py               ← Scraper + Claude-powered parser
├── requirements.txt
└── README.md
```

---

## Costs

| Service | Cost |
|---|---|
| GitHub Actions (public repo) | Free |
| GitHub Pages | Free |
| Anthropic API (1 call/week to parse Puotilan Kartano) | ~$0.01/week |

Total: essentially **free**.
