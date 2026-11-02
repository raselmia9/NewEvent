# Stage 2: Match server metadata

Put `matches.json` (the first-stage output) in the repository root.

This stage opens each match detail page and records visible server button labels,
visible status text, player option labels, and explicit public page/navigation hrefs.

It does not click stream launch controls and does not inspect or collect protected
media manifests, DRM license data, or decryption keys.

Run locally:
    pip install -r requirements-stage2.txt
    playwright install chromium
    python scraper_stage2.py

GitHub Actions runs every 15 minutes or manually via Actions > Run workflow.
