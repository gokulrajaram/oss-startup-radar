#!/usr/bin/env python3
"""Enrich repos with community signal from last30days (Reddit + HN)."""
import json, math, subprocess, sys, time
from pathlib import Path

VENDOR = Path.home() / "Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/23d46704-2629-4bea-b261-7ac2ca72830e/vendor/last30days-skill"
SCRIPT = VENDOR / "scripts/last30days.py"

def find_python():
    for py in ("python3.14", "python3.13", "python3.12"):
        try:
            r = subprocess.run([py, "-c", "import sys; raise SystemExit(0 if sys.version_info>=(3,12) else 1)"],
                               capture_output=True, timeout=5)
            if r.returncode == 0: return py
        except (FileNotFoundError, subprocess.TimeoutExpired): pass
    return None

def run_last30days(full_name, python_cmd):
    org, repo = full_name.split("/")
    topic = f"{org} {repo}"
    cmd = [python_cmd, str(SCRIPT), topic,
           f"--github-repo={full_name}",
           "--search=reddit,hackernews",
           "--quick", "--lookback-days=30", "--emit=json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90, cwd=str(VENDOR))
        if r.returncode != 0:
            print(f"  [warn] exit {r.returncode}: {r.stderr[:120]}", file=sys.stderr)
            return None
        return json.loads(r.stdout)
    except subprocess.TimeoutExpired:
        print(f"  [warn] timeout", file=sys.stderr); return None
    except Exception as e:
        print(f"  [warn] {e}", file=sys.stderr); return None

def is_relevant(item, repo_name, org_name):
    """Return True only if this post actually mentions the repo or org name."""
    needles = {repo_name.lower(), org_name.lower()}
    haystack = " ".join([
        (item.get("title") or ""),
        (item.get("snippet") or ""),
        (item.get("body") or ""),
        (item.get("url") or ""),
    ]).lower()
    return any(n in haystack for n in needles if len(n) > 2)

def compute_community(report, repo_name="", org_name=""):
    """Convert last30days JSON report into a reddit-compatible community signal dict."""
    if not report:
        return {"post_count": 0, "avg_score": 0, "reddit_score": 0, "top_post": None,
                "reddit_count": 0, "hn_count": 0}

    ibs = report.get("items_by_source", {})
    reddit_items = [i for i in ibs.get("reddit", []) if is_relevant(i, repo_name, org_name)]
    hn_items     = [i for i in ibs.get("hackernews", []) if is_relevant(i, repo_name, org_name)]

    def pts(item):
        e = item.get("engagement") or {}
        return (e.get("score") or e.get("points") or e.get("upvotes") or 0)

    reddit_pts = sum(pts(i) for i in reddit_items)
    hn_pts     = sum(pts(i) for i in hn_items)

    # HN posts weighted 2× (higher signal quality / curation)
    weighted_posts = len(reddit_items) + len(hn_items) * 2
    total_pts      = reddit_pts + hn_pts * 2
    avg_score      = total_pts / max(weighted_posts, 1)

    raw = (math.log1p(weighted_posts) / math.log1p(50) * 60 +
           math.log1p(avg_score)      / math.log1p(1000) * 40)

    all_items = reddit_items + hn_items
    top_pts   = max((pts(i) for i in all_items), default=0)
    if top_pts > 500: raw += 10

    score = round(min(100, raw), 1)

    top_post = None
    if all_items:
        best = max(all_items, key=pts)
        src  = best.get("source", "")
        top_post = {
            "title":     (best.get("title") or "")[:100],
            "score":     pts(best),
            "permalink": best.get("url", ""),
            "subreddit": best.get("container", src),  # subreddit name or HN
        }

    return {
        "post_count":   len(reddit_items) + len(hn_items),
        "reddit_count": len(reddit_items),
        "hn_count":     len(hn_items),
        "avg_score":    round(avg_score, 1),
        "reddit_score": score,   # kept as reddit_score for score_and_rank compatibility
        "top_post":     top_post,
    }

def main():
    repos = json.load(open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin)

    python_cmd = find_python()
    if not python_cmd:
        print("[ERROR] Python 3.12+ not found. Install via: brew install python@3.12", file=sys.stderr)
        sys.exit(1)

    if not SCRIPT.exists():
        print(f"[ERROR] last30days not found at {SCRIPT}", file=sys.stderr)
        sys.exit(1)

    enriched = []
    for i, repo in enumerate(repos):
        fn = repo["full_name"]
        print(f"[{i+1}/{len(repos)}] {fn}", file=sys.stderr)
        report = run_last30days(fn, python_cmd)
        signal = compute_community(report, repo_name=repo["repo"], org_name=repo["org"])
        repo["reddit"] = signal   # replaces any prior reddit field
        if signal["post_count"] > 0:
            print(f"  → {signal['reddit_count']}r + {signal['hn_count']}hn posts · score {signal['reddit_score']}", file=sys.stderr)
        enriched.append(repo)
        time.sleep(0.3)

    print(json.dumps(enriched, indent=2))

if __name__ == "__main__": main()
