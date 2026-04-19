#!/usr/bin/env python3
"""Reddit signal via two approaches:
1. Reddit search JSON (with generous backoff)
2. DuckDuckGo search for Reddit posts (fallback when rate-limited)
"""
import json, math, sys, time, re, requests

PRIMARY_SUBS = ["LocalLLaMA", "MachineLearning"]
HDR_REDDIT = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
HDR_DDG = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
CUTOFF = int(time.time()) - 30 * 24 * 3600

# Track consecutive rate-limit hits to decide when to give up
_consecutive_rl = 0

def reddit_search(q, sub, limit=10):
    global _consecutive_rl
    url = f"https://www.reddit.com/r/{sub}/search.json"
    params = {"q": q, "restrict_sr": "1", "sort": "relevance", "t": "month", "limit": limit}
    try:
        r = requests.get(url, headers=HDR_REDDIT, params=params, timeout=12)
        if r.status_code == 429:
            _consecutive_rl += 1
            wait = min(120 * _consecutive_rl, 300)
            print(f"  [warn] Reddit 429 (hit #{_consecutive_rl}) — sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
            r = requests.get(url, headers=HDR_REDDIT, params=params, timeout=12)
            if r.status_code == 429:
                return None  # Signal caller to fall back to DDG
        _consecutive_rl = 0  # Reset on success
        if r.status_code != 200:
            return []
        posts = []
        for c in r.json().get("data", {}).get("children", []):
            p = c.get("data", {})
            if p.get("created_utc", 0) < CUTOFF:
                continue
            posts.append({
                "title": p.get("title", ""), "score": p.get("score", 0),
                "num_comments": p.get("num_comments", 0), "subreddit": p.get("subreddit", ""),
                "permalink": "https://reddit.com" + p.get("permalink", ""),
                "is_primary": sub in PRIMARY_SUBS,
            })
        return posts
    except Exception as e:
        print(f"  [warn] reddit_search: {e}", file=sys.stderr)
        return []

def ddg_reddit_search(repo_name, org_name):
    """Search DuckDuckGo for Reddit discussions about this repo."""
    posts = []
    queries = [
        f'site:reddit.com "{repo_name}" (LocalLLaMA OR MachineLearning)',
        f'site:reddit.com "{repo_name}" AI',
    ]
    for q in queries:
        try:
            r = requests.get("https://api.duckduckgo.com/", headers=HDR_DDG,
                params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1}, timeout=10)
            if r.status_code != 200:
                continue
            d = r.json()
            # Parse related topics as proxy for Reddit posts
            for item in d.get("RelatedTopics", [])[:8]:
                text = item.get("Text", "")
                url = item.get("FirstURL", "")
                if "reddit.com" in url and repo_name.lower() in text.lower():
                    sub = "LocalLLaMA" if "localllama" in url.lower() else \
                          "MachineLearning" if "machinelearning" in url.lower() else "reddit"
                    posts.append({
                        "title": text[:120], "score": 50, "num_comments": 0,
                        "subreddit": sub, "permalink": url,
                        "is_primary": sub in PRIMARY_SUBS,
                    })
            time.sleep(0.5)
        except Exception as e:
            print(f"  [warn] ddg: {e}", file=sys.stderr)
    return posts

def is_relevant(post, repo_name, org_name):
    title = post.get("title", "").lower()
    url = post.get("permalink", "").lower()
    terms = set([
        repo_name.lower(), org_name.lower(),
        repo_name.lower().replace("-", "").replace("_", ""),
        org_name.lower().replace("-", "").replace("_", ""),
    ])
    combined = title + " " + url
    return any(t in combined for t in terms if len(t) > 2)

def gather(repo):
    global _consecutive_rl
    repo_name = repo["repo"]
    org_name = repo["org"]
    all_posts = {}
    use_ddg = _consecutive_rl >= 2  # Fall back to DDG if Reddit keeps blocking

    if not use_ddg:
        for sub in PRIMARY_SUBS:
            result = reddit_search(repo_name, sub)
            if result is None:
                use_ddg = True
                break
            for p in result:
                if is_relevant(p, repo_name, org_name):
                    all_posts[p["permalink"]] = p
            time.sleep(2.5)

    if use_ddg:
        print(f"  [info] Using DDG fallback for {repo_name}", file=sys.stderr)
        for p in ddg_reddit_search(repo_name, org_name):
            if is_relevant(p, repo_name, org_name):
                all_posts[p["permalink"]] = p

    return list(all_posts.values())

def score(posts):
    if not posts:
        return {"post_count": 0, "weighted_count": 0, "avg_score": 0,
                "top_post": None, "total_comments": 0, "reddit_score": 0}
    w = sum(2 if p.get("is_primary") else 1 for p in posts)
    avg = round(sum(p["score"] for p in posts) / len(posts), 1)
    top = max(posts, key=lambda p: p["score"])
    buzz = math.log1p(w) / math.log1p(50) * 60 + math.log1p(avg) / math.log1p(1000) * 40
    if top["score"] > 500:
        buzz += 10
    return {
        "post_count": len(posts), "weighted_count": w, "avg_score": avg,
        "total_comments": sum(p["num_comments"] for p in posts),
        "top_post": {"title": top["title"], "score": top["score"],
                     "num_comments": top["num_comments"], "subreddit": top["subreddit"],
                     "permalink": top["permalink"]},
        "reddit_score": round(min(100, buzz), 1),
    }

def main():
    repos = json.load(open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin)
    enriched = []
    for i, repo in enumerate(repos):
        print(f"[{i+1}/{len(repos)}] Reddit: {repo['full_name']}", file=sys.stderr)
        sig = score(gather(repo))
        print(f"  → {sig['post_count']} posts, score={sig['reddit_score']}", file=sys.stderr)
        enriched.append({**repo, "reddit": sig})
        time.sleep(1.5)
    print(json.dumps(enriched, indent=2))

if __name__ == "__main__":
    main()
