
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright

INPUT_FILE = Path("matches.json")
OUTPUT_FILE = Path("matches_with_channels.json")

PLAYER_NAMES = ["Shaka", "Clappr", "dash.js", "Video.js"]


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


async def inspect_servers(page):
    return await page.evaluate("""() => {
        const clean = s => (s || '').replace(/\\s+/g, ' ').trim();

        const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                s.display !== 'none' && s.visibility !== 'hidden';
        };

        const elements = [...document.querySelectorAll(
            'button, a, [role="button"]'
        )].filter(visible);

        const servers = [];
        const seen = new Set();

        for (const el of elements) {
            const name = clean(el.innerText || el.getAttribute('aria-label'));

            if (!name || name.length > 120) continue;

            if (/^(Shaka|Clappr|dash\\.js|Video\\.js)$/i.test(name)) {
                continue;
            }

            const parent = el.parentElement || el;
            const card = parent.parentElement || parent;
            const cardText = clean(card.innerText);

            if (!cardText) continue;

            const key = name + "|" + cardText;
            if (seen.has(key)) continue;
            seen.add(key);

            servers.push({
                name: name,
                status: /offline/i.test(cardText) ? "OFFLINE" :
                        /online/i.test(cardText) ? "ONLINE" : "",
                page_link: el.getAttribute('href') || ""
            });
        }

        const players = elements
            .map(el => clean(el.innerText))
            .filter(name =>
                /^(Shaka|Clappr|dash\\.js|Video\\.js)$/i.test(name)
            );

        return {
            title: clean(document.querySelector('h1')?.innerText ||
                         document.title),
            players: [...new Set(players)],
            servers: servers
        };
    }""")


async def main():
    if not INPUT_FILE.exists():
        print("ERROR: matches.json পাওয়া যায়নি।")
        return

    matches = json.loads(INPUT_FILE.read_text(encoding="utf-8"))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            viewport={"width": 1365, "height": 1000}
        )

        page = await context.new_page()

        for index, match in enumerate(matches, 1):

            match_url = match.get("link", "")

            if not match_url:
                match["channels"] = []
                continue

            try:
                print(f"Opening {index}/{len(matches)}: {match_url}")

                await page.goto(
                    match_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )

                await page.wait_for_timeout(3000)

                data = await inspect_servers(page)

                channels = []

                for server in data["servers"]:
                    href = server.get("page_link", "")

                    channels.append({
                        "name": server["name"],
                        "status": server["status"],
                        "player_options": data["players"],
                        "page_link": urljoin(page.url, href) if href else ""
                    })

                match["channels"] = channels
                match["detail_page_title"] = data["title"]

                print(
                    f"Found {len(channels)} server entries"
                )

            except Exception as error:
                match["channels"] = []
                match["scrape_error"] = str(error)

                print("ERROR:", error)

        await browser.close()

    OUTPUT_FILE.write_text(
        json.dumps(matches, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("Completed:", OUTPUT_FILE)


if __name__ == "__main__":
    asyncio.run(main())
