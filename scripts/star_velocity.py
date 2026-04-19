#!/usr/bin/env python3
import json, math, os, sys, time
from datetime import datetime, timedelta, timezone
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN","")
if not GITHUB_TOKEN:
    print("[ERROR] GITHUB_TOKEN required. export GITHUB_TOKEN=ghp_...", file=sys.stderr)
    sys.exit(1)

STAR_H = {"Accept":"application/vnd.github.star+json","X-GitHub-Api-Version":"2022-11-28","Authorization":f"Bearer {GITHUB_TOKEN}"}
META_H = {"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","Authorization":f"Bearer {GITHUB_TOKEN}"}
MAX_PAGES, PER_PAGE = 15, 100
NOW = datetime.now(timezone.utc)
WINDOWS = {"30d": NOW-timedelta(days=30), "60d": NOW-timedelta(days=60), "90d": NOW-timedelta(days=90)}

def fetch_stars(fn, total):
    if total == 0: return []
    last_page = math.ceil(total/PER_PAGE)
    start = max(1, last_page - MAX_PAGES + 1)
    url = f"https://api.github.com/repos/{fn}/stargazers"
    ts = []
    for page in range(start, last_page+1):
        try:
            r = requests.get(url, headers=STAR_H, params={"per_page":PER_PAGE,"page":page}, timeout=15)
            if r.status_code == 403:
                print(f"  [warn] rate limited, sleeping 60s", file=sys.stderr); time.sleep(60)
                r = requests.get(url, headers=STAR_H, params={"per_page":PER_PAGE,"page":page}, timeout=15)
            if r.status_code != 200: break
            for e in r.json():
                t = e.get("starred_at")
                if t:
                    try: ts.append(datetime.fromisoformat(t.replace("Z","+00:00")))
                    except: pass
            time.sleep(0.15)
        except Exception as e: print(f"  [warn] page {page}: {e}", file=sys.stderr); break
    return ts

def age_mult(age_days, mom_pct):
    if mom_pct >= 0.30: return 2.0
    if mom_pct >= 0.15: return 1.6
    if age_days is None: return 1.0
    if age_days < 180: return 2.0
    if age_days < 365: return 1.6
    if age_days < 548: return 1.2
    if age_days < 730: return 0.9
    return 0.5

def vel_score(vel):
    total = vel.get("total_stars",0)
    if not total: return 0.0
    # Use best window (30d preferred, fall back to 60d/90d normalized to 30d equivalent)
    g30  = vel["30d"]["gained"]
    pd30 = vel["30d"]["per_day"]
    pd60 = vel["60d"]["per_day"]
    pd90 = vel["90d"]["per_day"]
    best_pd = max(pd30, pd60, pd90)
    best_g  = max(g30, vel["60d"]["gained"], vel["90d"]["gained"])
    mom = vel.get("recent_momentum_pct",0)
    ratio_s = min(100, best_g/total*400)
    abs_s   = min(100, math.log1p(best_pd)/math.log1p(500)*100)
    raw = ratio_s*0.6 + abs_s*0.4
    adj = raw * age_mult(vel.get("age_days"), mom)
    if total > 300_000: adj = min(30, adj)
    return round(min(100, adj), 1)

def main():
    repos = json.load(open(sys.argv[1]) if len(sys.argv)>1 else sys.stdin)
    enriched = []
    for i, repo in enumerate(repos):
        fn, total = repo["full_name"], repo.get("stars",0)
        print(f"[{i+1}/{len(repos)}] {fn} ({total:,}★)", file=sys.stderr)
        timestamps = fetch_stars(fn, total)
        vel = {"total_stars": total, "age_days": None}
        if repo.get("created_at"):
            try:
                created = datetime.fromisoformat(repo["created_at"].replace("Z","+00:00"))
                vel["age_days"] = (NOW-created).days
            except: pass
        age = vel["age_days"] or 9999
        for w, cutoff in WINDOWS.items():
            window_days = int(w[:-1])
            cnt = sum(1 for t in timestamps if t >= cutoff)
            # Young repo: all stars are within this window; use total if sample looks incomplete
            if age <= window_days and cnt < total * 0.5:
                cnt = total
            vel[w] = {"gained": cnt, "per_day": round(cnt/window_days, 1)}
        g90 = vel["90d"]["gained"]
        vel["recent_momentum_pct"] = round(g90/max(total,1), 4)
        vel["recent_momentum_label"] = ("very_hot" if vel["recent_momentum_pct"]>=0.30 else
                                        "hot" if vel["recent_momentum_pct"]>=0.15 else
                                        "growing" if vel["recent_momentum_pct"]>=0.05 else "mature")
        age = vel.get("age_days") or 0
        if vel["30d"]["gained"] < 30 and vel["recent_momentum_pct"] < 0.05 and age > 365:
            print(f"  → dropped (old+quiet)", file=sys.stderr); continue
        enriched.append({**repo, "velocity": vel, "velocity_score": vel_score(vel)})
        time.sleep(0.1)
    enriched.sort(key=lambda r: r["velocity_score"], reverse=True)
    print(f"[info] {len(enriched)} passed filter", file=sys.stderr)
    print(json.dumps(enriched, indent=2))

if __name__ == "__main__": main()
