import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

SITE_URL = "https://proximitybd-mominrocks.lovable.app/"
OUT_FILE = Path("matches.json")
DEBUG_FILE = Path("debug.json")

DATE_RE = re.compile(
    r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)?[,]?\s*"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}"
    r".{0,30}?\d{1,2}:\d{2}\s*(AM|PM)?",
    re.I,
)
STATUS_WORDS = ("LIVE", "UPCOMING", "ENDED")
SPORT_WORDS = (
    "CRICKET", "FOOTBALL", "TENNIS", "BASKETBALL", "HOCKEY",
    "RUGBY", "BADMINTON", "VOLLEYBALL", "BASEBALL"
)


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def absolute_url(value, base):
    if not value:
        return ""
    return urljoin(base, value.strip())


async def inspect_page(page):
    # Read cards from the rendered DOM. The selectors are intentionally
    # heuristic until the site's exact DOM/API has been confirmed.
    return await page.evaluate(r"""() => {
      const clean = s => (s || '').replace(/\s+/g, ' ').trim();
      const visible = el => {
        const r = el.getBoundingClientRect();
        const st = getComputedStyle(el);
        return r.width > 0 && r.height > 0 &&
               st.display !== 'none' && st.visibility !== 'hidden';
      };
      const dateRe = /(Mon|Tue|Wed|Thu|Fri|Sat|Sun)?[,]?\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}.{0,30}?\d{1,2}:\d{2}\s*(AM|PM)?/i;
      const sports = ['CRICKET','FOOTBALL','TENNIS','BASKETBALL','HOCKEY','RUGBY','BADMINTON','VOLLEYBALL','BASEBALL'];
      const statusWords = ['LIVE','UPCOMING','ENDED'];
      const found = [];
      const seen = new Set();

      // Card candidates: elements with at least two images and a date/time.
      const all = Array.from(document.querySelectorAll('a, article, li, div'))
        .filter(visible)
        .filter(el => {
          const imgs = el.querySelectorAll('img');
          if (imgs.length < 2) return false;
          const txt = clean(el.innerText);
          return dateRe.test(txt) && txt.length < 1800;
        })
        .sort((a,b) => {
          const aa = a.querySelectorAll('img').length;
          const bb = b.querySelectorAll('img').length;
          return aa - bb;
        });

      for (const el of all) {
        // Prefer the smallest qualifying ancestor/card.
        const imgs = Array.from(el.querySelectorAll('img')).filter(visible);
        const text = clean(el.innerText);
        const key = text + '|' + imgs.map(i => i.currentSrc || i.src).join('|');
        if (seen.has(key)) continue;
        seen.add(key);

        const anchor = el.matches('a') ? el : el.querySelector('a[href]');
        const href = anchor ? anchor.getAttribute('href') : '';
        const imgData = imgs.slice(0, 4).map(i => ({
          src: i.currentSrc || i.src || i.getAttribute('data-src') || '',
          alt: clean(i.alt)
        }));

        const lines = (el.innerText || '').split('\n').map(clean).filter(Boolean);
        const category = lines.find(x => sports.includes(x.toUpperCase())) || '';
        const status = statusWords.find(x => text.toUpperCase().includes(x)) || '';
        const dateMatch = text.match(dateRe);
        const title = lines.find(x =>
          x.length > 5 &&
          x !== category &&
          !statusWords.includes(x.toUpperCase()) &&
          !dateRe.test(x) &&
          !/^\d+$/.test(x)
        ) || '';

        found.push({
          title, category, date: dateMatch ? clean(dateMatch[0]) : '',
          status, link: href, images: imgData,
          text, tag: el.tagName.toLowerCase(),
          className: String(el.className || '').slice(0, 250)
        });
      }

      const resources = performance.getEntriesByType('resource')
        .map(x => x.name)
        .filter(x => /(api|graphql|supabase|firebase|event|match|json)/i.test(x))
        .slice(-250);

      return {
        pageTitle: document.title,
        pageUrl: location.href,
        bodyText: clean(document.body.innerText).slice(0, 12000),
        cards: found,
        resources,
        imageCount: document.images.length,
        anchorCount: document.querySelectorAll('a[href]').length
      };
    }""")


async def main():
    debug = {
        "site": SITE_URL,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_json_responses": [],
        "errors": []
    }
    matches = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1100},
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
        )
        page = await context.new_page()

        async def on_response(response):
            try:
                ctype = (response.headers.get("content-type") or "").lower()
                if "json" in ctype:
                    body = await response.json()
                    debug["network_json_responses"].append({
                        "url": response.url,
                        "status": response.status,
                        "sample": body if isinstance(body, (dict, list)) else str(body)[:1000]
                    })
            except Exception:
                pass

        page.on("response", on_response)

        try:
            await page.goto(SITE_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(12000)

            # Scroll progressively to trigger lazy-loaded event cards.
            for _ in range(8):
                await page.evaluate("window.scrollBy(0, Math.max(600, window.innerHeight * 0.8))")
                await page.wait_for_timeout(900)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1500)

            snapshot = await inspect_page(page)
            debug["page"] = snapshot

            for item in snapshot.get("cards", []):
                imgs = item.get("images", [])
                if not item.get("title") and not imgs:
                    continue

                image_urls = [
                    absolute_url(x.get("src", ""), SITE_URL)
                    for x in imgs if x.get("src")
                ]

                # First two images are treated as team logos. This will be
                # refined once the site's exact card DOM is inspected.
                matches.append({
                    "title": item.get("title", ""),
                    "team1_logo": image_urls[0] if len(image_urls) > 0 else "",
                    "team2_logo": image_urls[1] if len(image_urls) > 1 else "",
                    "date": item.get("date", ""),
                    "category": item.get("category", ""),
                    "status": item.get("status", ""),
                    "link": absolute_url(item.get("link", ""), SITE_URL)
                })

        except Exception as exc:
            debug["errors"].append(repr(exc))
        finally:
            await browser.close()

    # Remove duplicate records while preserving order.
    unique = []
    seen = set()
    for row in matches:
        key = (row["title"], row["date"], row["link"])
        if key not in seen:
            seen.add(key)
            unique.append(row)

    OUT_FILE.write_text(
        json.dumps(unique, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    DEBUG_FILE.write_text(
        json.dumps(debug, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )

    print(f"Scraped {len(unique)} candidate cards.")
    print(f"Saved: {OUT_FILE} and {DEBUG_FILE}")
    if not unique:
        print("No cards detected yet. Check debug.json for rendered page text,")
        print("network JSON responses, resource URLs, and DOM diagnostics.")


if __name__ == "__main__":
    asyncio.run(main())
