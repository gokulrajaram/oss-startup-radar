---
name: oss-startup-radar
description: >
  Finds fast-growing, pre-Series-A open source AI/ML startups using GitHub star velocity
  (30/60/90-day windows) and community buzz from Reddit + Hacker News. Surfaces the top 25
  repos with full blurbs plus top 5 trending themes. Use this skill whenever the user asks
  about: fast-growing AI open source projects, hot OSS startups, what's trending in AI GitHub,
  which AI repos are blowing up, pre-seed/seed AI companies to watch, emerging AI tools, or
  anything about discovering new AI projects via GitHub stars or Reddit buzz. Trigger even if
  they just ask "what's hot in AI OSS" or "any interesting AI repos lately".
---

# OSS Startup Radar

Finds fast-growing **pre-Series-A** open source AI/ML startups using two signals:
1. **GitHub star velocity** — 30/60/90-day star gains from the timestamped Stargazers API
2. **Community buzz** — Reddit + Hacker News posts via `last30days_signal.py` (powered by last30days)

Outputs: top 25 repos ranked by composite score (60% velocity + 40% community), plus top 5 trending theme synthesis.

## Requirements

- **GITHUB_TOKEN** — required for the Stargazers API. Hard exit if missing.
  - Check: `echo $GITHUB_TOKEN` or `cat ~/.github_token`
  - If missing, tell the user: "I need a GitHub personal access token with `public_repo` read scope to fetch star velocity data. Create one at github.com/settings/tokens."
- **Python 3.12+** — required for `last30days_signal.py`. Install with `brew install python@3.12` if missing.
- **last30days** — bundled at the skills vendor path. Uses browser cookies for Reddit (no API key needed). First run triggers a one-time setup wizard.

## Pipeline (run steps in order)

Scripts live at `$SKILL_ROOT/scripts/`. Each step reads from the previous step's output.

### Step 1 — Fetch candidates (~1 min)

```bash
source ~/.github_token 2>/dev/null || true
python3 $SKILL_ROOT/scripts/fetch_candidates.py --limit 200 > /tmp/candidates.json
```

Searches GitHub for recent AI/ML repos (created after 2024-01-01) and older repos with recent push activity. Returns ~150–200 repos. Filters: 50–300k stars, not a fork, passes AI keyword/topic check.

### Step 2 — Star velocity (~4–6 min)

```bash
python3 $SKILL_ROOT/scripts/star_velocity.py /tmp/candidates.json > /tmp/velocity.json
```

Fetches the last 1,500 stargazers (timestamped) for each repo. Computes 30d/60d/90d star gains and stars/day. Young repo correction: if the repo is younger than the window and the sample looks incomplete, uses total stars as the window count. Drops repos that are old AND quiet (<30 stars/30d and <5% momentum). Outputs ~100–150 repos.

### Step 3 — Community signal (~3–4 min)

```bash
python3 $SKILL_ROOT/scripts/last30days_signal.py /tmp/velocity.json > /tmp/community.json
```

Runs `last30days --github-repo owner/repo --search reddit,hackernews --quick --lookback-days 30` for each repo. Filters results to posts where title/snippet/body/URL contains the repo or org name (prevents false positives from common-word matches). HN posts weighted 2× Reddit. Outputs a `reddit` field per repo compatible with the scorer.

**If last30days setup is needed:** run `python3.12 <vendor-path>/scripts/last30days.py setup` once to configure browser cookies, then rerun this step.

### Step 4 — Funding check (~2–3 min)

```bash
python3 $SKILL_ROOT/scripts/funding_check.py /tmp/community.json > /tmp/funded.json
```

For each org: Crunchbase scrape → org homepage → GitHub org API → DuckDuckGo snippet. Conservative: `unknown` is included. Only `series-a` and `series-b+` are excluded. Known post-Series-A orgs are hardcoded in `score_and_rank.py` as a fallback.

### Step 5 — Score, rank, and report

```bash
python3 $SKILL_ROOT/scripts/score_and_rank.py /tmp/funded.json > /tmp/report.md
cat /tmp/report.md
```

Applies three filters (velocity floor ≥20 stars in best window, non-startup filter, funding filter), sorts by composite score, synthesizes top 5 themes, and outputs a full Markdown report.

Also save a dated copy:
```bash
cp /tmp/report.md ~/Documents/oss-startup-radar/latest_report.md
```

## Composite score

```
composite = 0.60 × velocity_score + 0.40 × community_score
```

**velocity_score** (0–100):
- `ratio_score = min(100, best_window_gained / total_stars × 400)` — momentum relative to base
- `abs_score = min(100, log1p(best_stars_per_day) / log1p(500) × 100)` — absolute growth rate
- `raw = ratio_score × 0.6 + abs_score × 0.4`
- `velocity_score = raw × age_multiplier` (capped at 100)
- **age_multiplier**: <6mo→2×, <1yr→1.6×, <1.5yr→1.2×, 1.5–2yr→0.9×, >2yr→0.5× — overridden if >30% of total stars are from the last 90d (→2×) or >15% (→1.6×)
- **best_window**: uses max of 30d/60d/90d gains so repos that peaked in any window score correctly

**community_score** (0–100):
- `weighted_posts = reddit_count + hn_count × 2` (HN weighted 2× for curation quality)
- `raw = log1p(weighted_posts)/log1p(50)×60 + log1p(avg_pts)/log1p(1000)×40`
- +10 bonus if any post has >500 upvotes
- Posts only counted if title/snippet/body/URL contains the repo or org name

## Error handling

| Error | Cause | Fix |
|-------|-------|-----|
| `GITHUB_TOKEN not set` | Missing env var | Ask user to set it; source `~/.github_token` |
| `GH rate limit (403)` | Too many API calls | Script sleeps 60s and retries automatically |
| `last30days: Python 3.12+ not found` | Old Python in PATH | Run `brew install python@3.12` |
| `Crunchbase blocked` | Bot protection | Script falls back to homepage → GitHub org → DDG |
| `OSSInsight 500` | External API down | Script skips it, uses GitHub Search only |

## Output format

The report contains:
- **Header**: date, methodology summary, count of post-Series-A repos excluded
- **Top 5 Trending Themes**: each with a 2–3 sentence observation and 3 key project names
- **Top 25 repos**: for each — GitHub link, language, age, momentum label, funding stage, 30/60/90d velocity table, community signal (post count + top post link), description, composite score breakdown

Present the full report in the conversation. If the user wants a shorter version, summarize the themes and show the ranked list without the velocity tables.

## Keeping the list clean

The non-startup filter in `score_and_rank.py` has three layers:

- **`NON_STARTUP_ORGS`** — big tech, well-known research orgs, personal GitHub accounts
- **`NON_STARTUP_DESC`** — description keywords that indicate awesome-lists, tutorials, Claude Code skill repos, personal tools
- **`NON_STARTUP_NAME`** — repo name prefixes that indicate lists or templates

If a repo appears that clearly shouldn't be there (big tech, personal project, curated list), add its org to `NON_STARTUP_ORGS` in the script and note it to the user. If a well-funded org slips through, add it to `KNOWN_POST_SERIES_A`.
