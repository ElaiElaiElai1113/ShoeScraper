# ShoeScraper

ShoeScraper monitors configured sneaker search pages and saves new product sightings in a local SQLite database.

## Run The Browser Dashboard

From PowerShell:

```powershell
cd C:\Users\Admin\Desktop\Projects\Portfolio\ShoeScraper
.\run_frontend.ps1
```

The app opens at:

```text
http://127.0.0.1:8765
```

You can also run it with cloud-style settings:

```powershell
$env:HOST="0.0.0.0"
$env:PORT="8765"
$env:SHOESCRAPER_OPEN_BROWSER="0"
.\.venv\Scripts\python.exe web_app.py
```

Use the **Run scan** button to check all configured products and retailers. The dashboard shows scan progress, new matches from the latest scan, tracked products, and recent saved sightings.

Use the search box to look up any shoe name, SKU, or keyword across supported Australian retailers and public second-hand marketplace pages. You can also enter a US shoe size. The results show likely availability, whether the requested size appears on the result page, price signals, deal detection, source type, marketplace location when visible, and direct product links.

## Playwright Browser Support

ShoeScraper uses normal HTTP requests first, then falls back to Playwright for sources configured with `render_mode: auto` when static HTML is incomplete. Sources configured with `render_mode: browser`, such as public Facebook Marketplace search pages, use headless Chromium directly.

Install Python dependencies, then install the Chromium browser once:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

The scraper does not automate marketplace logins or use private sessions. If a public marketplace page requires login, the scan records a source health failure and continues with the other sources.

## Run From Terminal

```powershell
.\.venv\Scripts\python.exe ja_denim_monitor.py
```

## Telegram Alerts

Set these environment variables before running a scan if Telegram alerts are needed:

```powershell
$env:TELEGRAM_BOT_TOKEN="your-bot-token"
$env:TELEGRAM_CHAT_ID="your-chat-id"
```

Then start the dashboard or terminal scanner.

## Put It On The Web

The easiest deployment path for this project is a Python web service on Render, Railway, Fly.io, or a small VPS. Do not deploy it as a static site because the dashboard needs the Python backend in `web_app.py` for scanning, searching, and reading the SQLite database.

### Recommended: Render

1. Push this repository to GitHub.
2. In Render, create a new **Blueprint** from the repository. Render will use `render.yaml`.
3. Set these environment variables:

```text
HOST=0.0.0.0
SHOESCRAPER_OPEN_BROWSER=0
SHOESCRAPER_USERNAME=your-client-username
SHOESCRAPER_PASSWORD=a-long-random-password
TELEGRAM_BOT_TOKEN=optional
TELEGRAM_CHAT_ID=optional
```

Render supplies the public `PORT` automatically. After deploy, give your client the Render URL and the username/password.

### Manual Web Service Settings

If your host does not use `render.yaml`, configure it with:

```text
Build command: pip install -r requirements.txt
Start command: python web_app.py
```

Environment variables:

```text
HOST=0.0.0.0
PORT=<the port your host provides>
SHOESCRAPER_OPEN_BROWSER=0
SHOESCRAPER_USERNAME=your-client-username
SHOESCRAPER_PASSWORD=a-long-random-password
```

### Important Notes

- The included SQLite database is file-based. On hosts with ephemeral disks, saved sightings may reset after redeploys unless you add persistent storage or move the data to a hosted database.
- The scanner sends requests to retailer websites. Keep scan frequency reasonable and make sure your use complies with those websites' terms.
- Basic auth is optional locally, but it should be enabled before sharing the app publicly.

## Products And Sources

The active scanner reads products and sources from `config/products.yaml`. Add products there with SKUs, keywords, retailer/source ids, alert rules, and optional `required_sizes`.

Configured second-hand sources currently include eBay AU, Gumtree AU, and public Facebook Marketplace search pages.
