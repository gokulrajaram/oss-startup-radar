# OSS Startup Radar

A Claude Code and Codex skill that finds fast-growing **pre-Series-B** open source AI/ML startups using GitHub star velocity and community buzz from Reddit + Hacker News, then surfaces founder LinkedIn profiles for outreach.

Outputs:
- **Top 25 repos** ranked by composite score (60% velocity + 40% community), with a compact summary table and per-repo velocity/community breakdown
- **Top 5 trending themes** synthesized from the ranked set
- **Founder & contributor LinkedIn profiles** for each of the top 25 repos

## Install

```bash
cp -r oss-startup-radar ~/.claude/skills/oss-startup-radar
```

Then type `/oss-startup-radar` in any Claude conversation.

## Requirements

- **GitHub token** — needed for the Stargazers API and contributor lookups. Create one at [github.com/settings/tokens](https://github.com/settings/tokens) with `public_repo` read scope, then save it:
  ```bash
  echo 'export GITHUB_TOKEN=ghp_yourtoken' >> ~/.github_token
  ```
- **Python 3.12+** — required for the community signal step. Install with `brew install python@3.12` if missing.
- **last30days** — bundled in your Claude skills vendor path. Uses browser cookies for Reddit (no API key needed).

## How it works

The pipeline runs 6 steps, each building on the last:

1. **Fetch candidates** — searches GitHub for recent AI/ML repos with 50–300k stars
2. **Star velocity** — fetches timestamped stargazers to compute 30/60/90-day gains
3. **Community signal** — searches Reddit + HN for posts mentioning each repo (HN weighted 2×)
4. **Funding check** — scrapes Crunchbase + org homepage to exclude Series B+ companies (Series A is included and labeled)
5. **Score & rank** — composite score (60% velocity + 40% community), filters for startups, outputs the ranked report
6. **LinkedIn lookup** — pulls top 2–3 contributors per repo from GitHub, resolves their names, and finds LinkedIn profiles via web search

## Scoring

```
composite = 0.60 × velocity_score + 0.40 × community_score
```

Velocity uses a ratio score (momentum relative to base) + absolute growth rate, boosted by an age multiplier that rewards newer repos. Community counts only posts where the repo or org name appears in the title/snippet/body/URL — no false positives.

## Filtering for real startups

Three filter layers run before the final ranking:

- **Velocity floor** — drops repos with <20 stars in the best 30/60/90d window
- **Inflation filter** — drops young repos (<60d old) with >3000 stars but fewer than 5 weighted community posts. Catches star-bombing and AI-generated farm content.
- **Non-startup filter** — drops big tech orgs, personal accounts, awesome-lists, tutorial repos, and Claude Code skill repositories
- **Funding filter** — excludes orgs flagged as Series B or later (Crunchbase + homepage + GitHub org API + DuckDuckGo)

The output is biased toward genuinely investable, pre-Series-B AI startups with real user attention, plus the founders' contact paths for outreach.
