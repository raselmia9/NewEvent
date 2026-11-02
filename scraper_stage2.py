import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin
from playwright.async_api import async_playwright

INPUT_FILE = Path("matches.json")
OUTPUT_FILE = Path("matches_with_channels.json")
SITE_BASE = "https://proximitybd-mominrocks.lovable.app/"
TIMEOUT_MS = 45000

PLAYER_NAMES = ["Shaka", "Clappr", "dash.js", "Video.js"]
STATUS_WORDS = ["ONLINE", "OFFLINE", "LIVE", "UNAVAILABLE"]


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


async def inspect_match_page(page):
    """Read visible server cards/buttons and their public page links only."""
    return await page.evaluate(
        """({playerNames, statusWords}) => {
          const clean = s => (s || '').replace(/\\\\s+/g, ' ').trim();
          const visible = el => {
            const r = el.getBoundingClientRect();
            const st = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   st.display !== 'none' && st.visibility !== 'hidden';
          };

          const headings = [...document.querySelectorAll('h1,h2,h3,h4,div,span')]
            .filter(visible)
            .filter(el => clean(el.textContent).toUpperCase() === 'SERVERS')
            .sort((a,b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);

          let root = headings.length ? headings[0].parentElement : document.body;
          // Walk upward until a reasonably sized container includes several server-like cards.
          for (let i=0; i<4 && root.parentElement; i++) {
            const txt = clean(root.innerText).toUpperCase();
            if (txt.includes('ONLINE') || txt.includes('OFFLINE')) break;
            root = root.parentElement;
          }

          const candidates = [...root.querySelectorAll('button,a,[role="button"],[tabindex]')]
            .filter(visible)
            .filter(el => {
              const t = clean(el.innerText || el.getAttribute('aria-label'));
              return t.length > 1 && t.length < 180 &&
                     !playerNames.some(p => t.toLowerCase() === p.toLowerCase());
            });

          const servers = [];
          const seen = new Set();
          for (const el of candidates) {
            const text = clean(el.innerText || el.getAttribute('aria-label'));
            const parent = el.closest('a,button,[role="button"]') || el;
            const card = parent.parentElement || parent;
            const cardText = clean(card.innerText || text);
            const key = text + '|' + cardText;
            if (seen.has(key)) continue;
            seen.add(key);

            const href = parent.getAttribute('href') || '';
            const status = statusWords.find(s => cardText.toUpperCase().includes(s)) || '';
            const code = (cardText.match(/\\\\b[A-Z0-9]{2,8}\\\\b/) || [])[0] || '';
            servers.push({
              name: text.split('\\n')[0],
              visible_text: cardText,
              status,
              code,
              public_href: href,
              element_tag: parent.tagName.toLowerCase(),
              class_name: String(parent.className || '').slice(0,180)
            });
          }

          const players = [...document.querySelectorAll('button,[role="tab"],a')]
            .filter(visible)
            .map(el => clean(el.innerText || el.getAttribute('aria-label')))
            .filter(t => playerNames.some(p => t.toLowerCase() === p.toLowerCase()));

          return {
            title: clean(document.querySelector('h1')?.innerText || document.title),
            players: [...new Set(players)],
            servers,
            page_url: location.href
          };
        }""",
        {"playerNames": PLAYER_NAMES, "statusWords": STATUS_WORDS}
    )


async def main():
    if not INPUT_FILE.exists():
        raise SystemExit("matches.json is missing. Put the first-stage output beside scraper_stage2.py")

    matches = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    if not isinstance(matches, list):
        raise SystemExit("matches.json must contain a JSON array")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1365, "height": 1000},
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
        )
        page = await context.new_page()

        for index, match in enumerate(matches, start=1):
            match_url = match.get("link") or ""
            if not match_url:
                match["channels"] = []
                match["scrape_note"] = "Missing match link"
                continue

            try:
                await page.goto(urljoin(SITE_BASE, match_url), wait_until="domcontentloaded",
                                timeout=TIMEOUT_MS)
                await page.wait_for_timeout(2500)
                details = await inspect_match_page(page)

                channels = []
                for server in details.get("servers", []):
                    href = server.get("public_href", "")
                    channels.append({
                        "name": server.get("name", ""),
                        "status": server.get("status", ""),
                        "code": server.get("code", ""),
                        "player_options": details.get("players", []),
                        # Only explicit public page/navigation links are retained.
                        "page_link": urljoin(page.url, href) if href else ""
                    })

                match["channels"] = channels
                match["detail_page_title"] = details.get("title", "")
                match["scrape_note"] = (
                    "Server button metadata collected. Protected media manifests, "
                    "DRM license data and decryption keys are not collected."
                )
                print(f"[{index}/{len(matches)}] {match.get('title','(untitled)')}: "
                      f"{len(channels)} server entries")
            except Exception as exc:
                match["channels"] = []
                match["scrape_note"] = f"Page inspection failed: {type(exc).__name__}: {exc}"
                print(f"[{index}/{len(matches)}] ERROR: {exc}")

        await browser.close()

    OUTPUT_FILE.write_text(
        json.dumps(matches, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"Saved {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
