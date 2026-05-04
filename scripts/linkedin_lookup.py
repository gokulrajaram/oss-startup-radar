#!/usr/bin/env python3
"""
linkedin_lookup.py — enrich top repos with founder/contributor LinkedIn profiles.

For each repo in /tmp/ranked.json:
  1. GitHub Contributors API → top 3 contributors (by commit count)
  2. GitHub Users API → resolve display name + blog
  3. DuckDuckGo HTML search → find linkedin.com/in/ URL
     Fallback: Exa search API (set EXA_API_KEY env var)

Writes /tmp/linkedin.json, fills FOUNDERS_PLACEHOLDER_{rank} cells in the
summary table in /tmp/report.md, and appends a detailed Founders section.
"""

import json, os, re, sys, time
import urllib.request, urllib.parse, urllib.error

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
EXA_API_KEY  = os.environ.get("EXA_API_KEY", "")

HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "oss-startup-radar/1.0"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

DDG_URL = "https://html.duckduckgo.com/html/"
EXA_URL = "https://api.exa.ai/search"

# GitHub accounts that are bots / CI systems, not people
BOT_LOGINS = {
    "dependabot", "dependabot[bot]", "github-actions[bot]", "renovate[bot]",
    "semantic-release-bot", "allcontributors[bot]", "stale[bot]", "codecov",
    "snyk-bot", "greenkeeper[bot]", "renovate", "pre-commit-ci[bot]",
    "imgbot[bot]", "deepsource-autofix[bot]", "sonarcloud[bot]",
}


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------

def gh_get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[warn] GitHub API error {url}: {e}", file=sys.stderr)
        return None


def get_contributors(full_name, n=5):
    """Return top n non-bot contributor logins for a repo."""
    data = gh_get(f"https://api.github.com/repos/{full_name}/contributors?per_page={n+5}&anon=0")
    if not data:
        return []
    out = []
    for c in data:
        login = c.get("login", "")
        if login.lower() in BOT_LOGINS or "[bot]" in login:
            continue
        out.append(login)
        if len(out) == n:
            break
    return out


def resolve_user(login):
    """Fetch display name, blog, and bio for a GitHub login."""
    data = gh_get(f"https://api.github.com/users/{login}")
    if not data:
        return {"login": login, "name": login, "blog": "", "bio": "", "company": ""}
    return {
        "login": login,
        "name": data.get("name") or login,
        "blog": data.get("blog") or "",
        "bio": data.get("bio") or "",
        "company": data.get("company") or "",
    }


# ---------------------------------------------------------------------------
# LinkedIn search — DDG first, Exa fallback
# ---------------------------------------------------------------------------

def _extract_linkedin_url(text):
    """Return first clean linkedin.com/in/ URL found in text, or None."""
    urls = re.findall(r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+', text)
    seen = set()
    for u in urls:
        clean = u.rstrip("/").split("?")[0]
        if clean not in seen:
            seen.add(clean)
            return clean
    return None


def ddg_linkedin(name, context=None):
    """Search DuckDuckGo HTML for a LinkedIn profile. Returns URL or None."""
    query = f'site:linkedin.com/in "{name}" "{context}"' if context else f'site:linkedin.com/in "{name}"'
    params = urllib.parse.urlencode({"q": query, "kl": "us-en"})
    req = urllib.request.Request(
        DDG_URL,
        data=params.encode(),
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:   # 20s — up from 12s
            html = r.read().decode("utf-8", errors="ignore")
        return _extract_linkedin_url(html)
    except Exception as e:
        print(f"[warn] DDG timeout/error for '{name}': {e}", file=sys.stderr)
        return None


def exa_linkedin(name, context=None):
    """Search Exa for a LinkedIn profile. Returns URL or None. Requires EXA_API_KEY."""
    if not EXA_API_KEY:
        return None
    query = f'site:linkedin.com/in "{name}" "{context}"' if context else f'site:linkedin.com/in "{name}"'
    payload = json.dumps({
        "query": query,
        "numResults": 3,
        "type": "keyword",
        "includeDomains": ["linkedin.com"],
    }).encode()
    req = urllib.request.Request(
        EXA_URL,
        data=payload,
        headers={
            "x-api-key": EXA_API_KEY,
            "Content-Type": "application/json",
            "User-Agent": "oss-startup-radar/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        for result in data.get("results", []):
            url = result.get("url", "")
            if "linkedin.com/in/" in url:
                clean = url.rstrip("/").split("?")[0]
                return clean
    except Exception as e:
        print(f"[warn] Exa search error for '{name}': {e}", file=sys.stderr)
    return None


def find_linkedin(name, org, repo_name):
    """Try DDG then Exa for a LinkedIn URL. Three tiers:
    1. name + org context
    2. name + repo context
    3. name-only (only if ≥8 non-space chars to avoid false positives on short/generic names)
    """
    for context in [org, repo_name]:
        url = ddg_linkedin(name, context)
        if url:
            return url
        time.sleep(0.8)
        url = exa_linkedin(name, context)
        if url:
            print(f"[info] Exa found LinkedIn for '{name}'", file=sys.stderr)
            return url

    # Tier 3: name-only — only for distinctive names (≥8 non-space chars)
    if len(name.replace(" ", "")) >= 8:
        time.sleep(0.8)
        url = ddg_linkedin(name)
        if url:
            return url
        url = exa_linkedin(name)
        if url:
            print(f"[info] Exa (name-only) found LinkedIn for '{name}'", file=sys.stderr)
            return url

    return None


# ---------------------------------------------------------------------------
# Per-repo enrichment
# ---------------------------------------------------------------------------

def lookup_repo(repo, top_n=3):
    """Return list of contributor dicts with linkedin_url for a repo."""
    full_name = repo.get("full_name", "")
    org       = repo.get("org", full_name.split("/")[0] if "/" in full_name else "")
    repo_name = repo.get("repo", full_name.split("/")[-1] if "/" in full_name else full_name)

    logins = get_contributors(full_name, n=top_n)
    results = []
    for login in logins:
        user         = resolve_user(login)
        display_name = user["name"]
        linkedin     = find_linkedin(display_name, org, repo_name)
        results.append({
            "login":       login,
            "name":        display_name,
            "linkedin_url": linkedin,
            "blog":        user.get("blog", ""),
            "bio":         user.get("bio", ""),
        })
        time.sleep(0.5)

    return results


# ---------------------------------------------------------------------------
# Report patching — fill summary table + append detailed section
# ---------------------------------------------------------------------------

def format_founders_for_table(contributors):
    """Return a compact comma-separated string of name + LinkedIn for table cell."""
    parts = []
    for c in contributors:
        name = c["name"]
        li   = c.get("linkedin_url")
        if li:
            parts.append(f"[{name}]({li})")
        else:
            parts.append(name)
    return ", ".join(parts) if parts else "—"


def patch_report(report_path, enriched):
    """Replace FOUNDERS_PLACEHOLDER_{rank} cells in the summary table."""
    with open(report_path) as f:
        content = f.read()

    for rank, item in enumerate(enriched, 1):
        placeholder = f"`FOUNDERS_PLACEHOLDER_{rank}`"
        replacement = format_founders_for_table(item["contributors"])
        content = content.replace(placeholder, replacement)

    with open(report_path, "w") as f:
        f.write(content)


def build_founders_section(enriched):
    """Build detailed Founders section to append to report."""
    lines = ["\n\n---\n", "## Founder & Contributor Profiles\n",
             "_Top 2–3 contributors per repo by commit count. "
             "LinkedIn via DuckDuckGo + Exa — verify before outreach._\n"]
    for item in enriched:
        repo         = item["repo"]
        contributors = item["contributors"]
        lines.append(f"\n### [{repo['full_name']}]({repo.get('html_url', '')})\n")
        desc = repo.get("description", "").strip()
        if desc:
            lines.append(f"_{desc}_\n\n")
        if not contributors:
            lines.append("_No contributors found._\n")
            continue
        for c in contributors:
            li      = c.get("linkedin_url")
            gh_link = f"[{c['name']}](https://github.com/{c['login']})"
            li_link = f" · [LinkedIn]({li})" if li else " · LinkedIn: _not found_"
            bio     = f" — {c['bio'][:90]}" if c.get("bio") else ""
            lines.append(f"- **{gh_link}**{li_link}{bio}\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ranked_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ranked.json"
    report_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/report.md"

    with open(ranked_path) as f:
        repos = json.load(f)

    if EXA_API_KEY:
        print("[info] Exa API key found — will use as fallback if DDG times out", file=sys.stderr)
    else:
        print("[info] No EXA_API_KEY — set it for better LinkedIn hit rate", file=sys.stderr)

    print(f"[info] Looking up contributors for {len(repos)} repos…", file=sys.stderr)
    enriched = []
    for i, repo in enumerate(repos, 1):
        full_name = repo.get("full_name", "?")
        print(f"[{i}/{len(repos)}] {full_name}", file=sys.stderr)
        contributors = lookup_repo(repo, top_n=3)
        enriched.append({"repo": repo, "contributors": contributors})

    # 1. Fill founder placeholders in the summary table
    patch_report(report_path, enriched)

    # 2. Append detailed section
    section = build_founders_section(enriched)
    with open(report_path, "a") as f:
        f.write(section)

    # 3. Save full enriched JSON
    with open("/tmp/linkedin.json", "w") as f:
        json.dump(enriched, f, indent=2)

    print(f"[info] Done → /tmp/linkedin.json, report updated at {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
