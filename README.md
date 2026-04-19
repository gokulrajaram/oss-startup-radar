# OSS Startup Radar

A Claude Code skill that finds fast-growing **pre-Series-A** open source AI/ML startups using GitHub star velocity and community buzz from Reddit + Hacker News.

Outputs: top 25 repos ranked by composite score (60% velocity + 40% community), plus top 5 trending themes.

## Install

```bash
cp -r oss-startup-radar ~/.claude/skills/oss-startup-radar
```

Then type `/oss-startup-radar` in any Claude conversation.

## Requirements

- **GitHub token** — needed for the Stargazers API. Create one at [github.com/settings/tokens](https://github.com/settings/tokens) with `public_repo` read scope, then save it:
  ```bash
  echo 'export GITHUB_TOKEN=ghp_yourtoken' >> ~/.github_token
  ```
- **Python 3.12+** — required for the community signal step. Install with `brew install python@3.12` if missing.
- **last30days** — bundled in your Claude skills vendor path. Uses browser cookies for Reddit (no API key needed).

## How it works

The pipeline runs 5 steps, each building on the last:

1. **Fetch candidates** — searches GitHub for recent AI/ML repos with 50–300k stars
2. **Star velocity** — fetches timestamped stargazers to compute 30/60/90-day gains
3. **Community signal** — searches Reddit + HN for posts mentioning each repo (HN weighted 2×)
4. **Funding check** — scrapes Crunchbase + org homepage to exclude Series A+ companies
5. **Score & rank** — composite score (60% velocity + 40% community), outputs a full report

## Scoring

```
composite = 0.60 × velocity_score + 0.40 × community_score
```

Velocity uses a ratio score (momentum relative to base) + absolute growth rate, boosted by an age multiplier that rewards newer repos. Community counts only posts where the repo or org name appears in the title/snippet/body/URL — no false positives.
