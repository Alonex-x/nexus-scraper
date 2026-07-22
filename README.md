# scraper-v1

Autonomous stealth web scraping agent, part of the Nexus ecosystem (central agent management API). It registers with the API, maintains a periodic heartbeat, queries pending scraping missions, executes them with Playwright, and reports the results.

## Architecture

- Heartbeat: every 60s, POST /api/v1/agents/heartbeat.
- Mission polling: every 30s, GET /api/v1/missions/pending?agent=scraper-v1.
- Execution: Playwright + Chromium headless, with stealth context (rotating user-agent, random viewport/locale/timezone, automation flags disabled).
- Reporting: POST /api/v1/missions/{id}/report with the result or error.

Both loops (heartbeat and missions) run concurrently on asyncio, and respond to SIGTERM/SIGINT by shutting down cleanly.

## Installation

python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

## Execution

python -m src.main

Stop the agent with Ctrl+C (SIGINT) or by sending SIGTERM to the process; both cases close the browser and flush logs before exiting.

## Tests

pytest tests/ -v
