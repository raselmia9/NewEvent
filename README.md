# Proximity Match Scraper

Python + Playwright scraper for:
https://proximitybd-mominrocks.lovable.app/

## Files
- `scraper.py`: loads the site, inspects rendered cards and captures JSON network responses.
- `matches.json`: extracted match data.
- `debug.json`: diagnostic snapshot used to identify the site's real DOM/API.
- `.github/workflows/scrape.yml`: scheduled GitHub Actions workflow (every 15 minutes).

## First run
1. Upload these files to the root of a GitHub repository.
2. Open **Actions** and enable workflows if GitHub asks.
3. Run **Scrape Proximity Match Cards** manually once.
4. Download the `proximity-scraper-debug` artifact.
5. Share `debug.json` here so the selectors/API can be made exact.

## Important
The website's public text rendering currently reports zero events, while the supplied screenshot shows 47.
This first version is therefore a discovery/diagnostic scraper. Its DOM card detection is heuristic,
not yet a confirmed site-specific selector. The debug artifact will show what Playwright actually sees
in GitHub Actions, including resource URLs and JSON responses. Do not treat an empty `matches.json`
as proof that the website has no events.
