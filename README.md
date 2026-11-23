# Social Media Analytics Dashboard

**Your social media analytics, on your own machine — no accounts, no API keys, nothing uploaded.**

Every platform already lets you download your post data as a CSV. This tool turns those exports into one clear dashboard: which platform earns the most engagement, when to post, which posts beat your own average, which hashtags actually work, and plain-language recommendations with real numbers behind them.

## The problem it fills

Creators and small businesses check analytics in five separate apps, and a unified view costs $20–50/month (Hootsuite, Buffer, Sprout). The free alternatives are either manual-entry web toys (you type every number in by hand), or self-hosted Docker suites that need a server and an API key per platform. Nothing simple, local and free reads the CSV exports platforms already give you — this does.

## Features

- **Import any platform export** — Instagram, Facebook, TikTok, LinkedIn and X, auto-detected from the file's headers. A generic format works for anything else. Header aliases mean real exports work, not just the samples.
- **No duplicates** — re-importing the same export skips posts already in the store.
- **Real engagement rates** — by reach (the honest rate) with a followers fallback when reach is missing. Numbers like `1.2k` and `1,234` are parsed correctly.
- **Best times to post** — weekday × hour heatmap ranked by average engagement rate. A slot only ranks with 2+ posts, so one lucky post is never called a pattern.
- **Top posts & outliers** — your best posts, plus the ones that beat your own median by 1.5× or more (the closest thing to a recipe for what to repeat).
- **Content-type performance** — reels vs images vs carousels vs text, ranked by engagement rate.
- **Hashtag performance** — every tag you used twice or more, ranked by the engagement rate it earned.
- **Weekly trends** — posts, reach and engagement per week.
- **Follower growth** — record follower counts over time (`snapshot`) and see growth per day.
- **Recommendations** — plain-language findings with evidence, e.g. "Post more reels — they earn 11% ER vs 2% for images" or "3 posts reached 1,000+ people but earned under 1% engagement — the hook needs work".
- **Reports** — terminal dashboard, Markdown, JSON, CSV, and a self-contained HTML dashboard (inline CSS + SVG charts, no JavaScript, no external requests) you can send to a client as-is.
- **Local-first** — data lives in one JSON file (`social-data.json`), written atomically with a `.bak` backup. Nothing leaves your machine.

## Quick start

Requires Python 3.9+ — no packages to install.

```bash
# 1. Try it on the samples (no export needed)
for f in instagram facebook tiktok linkedin x generic; do
  python smad.py import examples/${f}_sample.csv
done

# 2. See your dashboard
python smad.py dashboard

# 3. Write a shareable report
python smad.py report --format html --out report.html
```

## Getting your exports

| Platform | Where the export lives |
|---|---|
| Instagram | Settings → Privacy → Download your information → Posts / Insights |
| Facebook | Meta Business Suite → Insights → Export |
| TikTok | TikTok Studio → Analytics → Download data |
| LinkedIn | Analytics → Export (posts) |
| X | Settings → Your account → Download an archive of your data |

Any CSV with a date column and at least one metric column (likes, comments, shares, saves, reach, impressions, clicks) imports. See `python smad.py example <platform>` for the expected shape of each format.

## Usage

```bash
# Import (platform auto-detected; --platform forces it)
python smad.py import exports/instagram.csv
python smad.py import exports/my-posts.csv --platform tiktok

# Add one post by hand
python smad.py add --platform instagram --date 2026-11-20 --caption "New launch #freelance" \
    --type reel --likes 320 --comments 41 --shares 12 --saves 58 --reach 8400

# Dashboard and best times
python smad.py dashboard
python smad.py dashboard --platform instagram --days 30
python smad.py best-times
python smad.py top --count 10 --by rate
python smad.py hashtags

# Follower growth (record a snapshot whenever you like)
python smad.py snapshot --platform instagram --followers 1250
python smad.py snapshots

# Reports
python smad.py report --format md --out report.md
python smad.py report --format html --out report.html
python smad.py report --format json --out report.json
python smad.py report --format csv --out posts.csv

# Housekeeping
python smad.py list --limit 20
python smad.py remove --id 7482910031 --platform tiktok
python smad.py set-followers --platform instagram --followers 1250
python smad.py example tiktok        # print a sample CSV for a platform
```

Use `--data my-data.json` after any subcommand to keep a separate store (e.g. one per client).

## Example output

Real output from the sample data in `examples/` (19 posts across 5 platforms):

```
Social Media Analytics
========================

Posts analysed:  19
Total reach:     119,300
Total engagement:26,743 (likes 18,816, comments 1,475, shares 3,350, saves 3,102)
Avg ER:          8.99%

By platform:
  tiktok       4 posts  reach    48,200  ER  10.57%  avg 4415.5 engagements/post
  instagram    6 posts  reach    56,400  ER   8.36%  avg  785.5 engagements/post
  facebook     3 posts  reach    14,700  ER   6.27%  avg  307.3 engagements/post
  x            3 posts  reach         0  ER   5.36%  avg  775.0 engagements/post
  linkedin     3 posts  reach         0  ER   4.94%  avg  373.7 engagements/post

Best times to post:
  Tuesday   18:00   12.5% ER  (3 posts)
  Monday    19:00   8.56% ER  (3 posts)
  Wednesday 12:00   7.57% ER  (2 posts)
  Tuesday   15:00   6.61% ER  (2 posts)
  Monday    14:00   5.46% ER  (2 posts)

Recommendations:
  💡 Your best slot is Tuesday at 18:00 (12.5% avg ER across 3 posts)
  ⚠️ Linkedin lags badly: 4.94% ER vs 10.57% on Tiktok
  ℹ️ Instagram grew by 15.48% (4,200 → 4,850) over 19 days
```

Generated Markdown and HTML reports from the same sample data are in `examples/sample-report.md` and `examples/sample-report.html` (built from `examples/demo-data.json`).

## How engagement rate is calculated

- **Engagement** = likes + comments + shares + saves.
- **ER by reach** = engagement ÷ reach × 100. This is the rate shown wherever reach exists — it measures what the people who actually saw the post did.
- **ER by followers** = engagement ÷ followers × 100. Used only when a post has no reach figure (some LinkedIn exports).

## Project structure

```
smad.py                  # entry point: python smad.py <command>
smad/
  models.py              # Post / Snapshot / Store data models
  parseutils.py          # number + date parsing for messy exports
  importers.py           # CSV import, platform auto-detection, de-dup
  analytics.py           # rates, best times, outliers, hashtags, trends, recommendations
  store.py               # atomic JSON store with .bak backup
  reports.py             # terminal / Markdown / JSON / CSV / HTML reports
  cli.py                 # argparse subcommands
tests/                   # unittest suite (stdlib only)
examples/                # sample exports for all 6 formats + sample report
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Who it helps

- **Creators & freelancers** — stop guessing when to post and what to repeat.
- **Social media managers** — one report across all clients' platforms, from exports, with no logins to share.
- **Small businesses** — see which platform actually earns attention before spending more time (or money) on it.

## License

MIT — see [LICENSE](LICENSE).
