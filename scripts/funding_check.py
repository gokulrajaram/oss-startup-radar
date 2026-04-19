#!/usr/bin/env python3
import json, re, sys, time, requests

HDR = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
SERIES_A_RE = re.compile(r"\b(series[- ][a-z]|series a|series b|series c|series d|growth round|ipo|public company|late[- ]stage)\b", re.I)
SEED_RE = re.compile(r"\b(seed|pre[- ]seed|angel|pre[- ]series|friends and family|bootstrapped|self[- ]funded|accelerator|y combinator|yc [ws]\d+|techstars|500 startups)\b", re.I)
RAISE_RE = re.compile(r"raised\s+\$[\d,.]+\s*(million|billion|m\b|b\b)", re.I)
VC_NAMES = ["sequoia","andreessen horowitz","a16z","benchmark capital","accel","greylock","index ventures","lightspeed","general catalyst","founders fund","tiger global","coatue","insight partners","bessemer","kleiner perkins","battery ventures","first round","union square","redpoint","khosla ventures"]

def _highest(text):
    text = text.lower()
    for s, label in [("series d","series-b+"),("series c","series-b+"),("series b","series-b+"),("series a","series-a")]:
        if s in text: return label
    return "seed"

def try_crunchbase(org):
    slug = org.lower().replace("_","-").replace(".","-")
    try:
        r = requests.get(f"https://www.crunchbase.com/organization/{slug}", headers=HDR, timeout=10)
        if r.status_code not in (200,): return None
        text = r.text[:8000]
        if SERIES_A_RE.search(text):
            return {"stage": _highest(text), "source":"crunchbase", "note": "series signals found"}
        if SEED_RE.search(text):
            return {"stage":"seed","source":"crunchbase","note":"seed signals found"}
        return None
    except: return None

def try_homepage(homepage_url):
    """Scrape the org's website for funding keywords."""
    if not homepage_url or not homepage_url.startswith("http"): return None
    try:
        r = requests.get(homepage_url, headers=HDR, timeout=8)
        if r.status_code != 200: return None
        text = r.text[:6000].lower()
        if SERIES_A_RE.search(text):
            return {"stage": _highest(text), "source":"homepage", "note": "series signals on website"}
        if RAISE_RE.search(text):
            # Has "raised $X million" language — probably seed or series A
            if SERIES_A_RE.search(text):
                return {"stage": _highest(text), "source":"homepage", "note": "raise + series signals"}
            return {"stage":"seed","source":"homepage","note":"raise signals on website"}
        if any(vc in text for vc in VC_NAMES):
            if SERIES_A_RE.search(text):
                return {"stage": _highest(text), "source":"homepage", "note": "VC + series signals"}
            return {"stage":"seed","source":"homepage","note":"VC mention on website"}
        if SEED_RE.search(text):
            return {"stage":"seed","source":"homepage","note":"seed signals on website"}
        return None
    except: return None

def try_gh_org(org):
    """Check the GitHub org page for funding/company info."""
    try:
        r = requests.get(f"https://api.github.com/orgs/{org}",
                         headers={"Accept":"application/vnd.github+json"}, timeout=8)
        if r.status_code != 200: return None
        d = r.json()
        blog = d.get("blog","") or ""
        bio = d.get("description","") or ""
        company = d.get("company","") or ""
        combined = f"{blog} {bio} {company}".lower()
        if SERIES_A_RE.search(combined):
            return {"stage": _highest(combined), "source":"gh_org", "note": "series signals in GH org"}
        return blog  # return the blog URL for later scraping
    except: return None

def try_ddg_snippet(org, repo):
    """Search DuckDuckGo and parse the snippet for funding signals."""
    for q in [f'"{org}" funding "series a"', f'"{org}" crunchbase raised', f'"{org}" startup raised million']:
        try:
            r = requests.get("https://api.duckduckgo.com/", headers=HDR,
                params={"q":q,"format":"json","no_html":1,"skip_disambig":1}, timeout=8)
            if r.status_code != 200: continue
            d = r.json()
            text = " ".join(filter(None, [
                d.get("AbstractText",""), d.get("Answer",""),
                d.get("AbstractSource",""),
                " ".join(x.get("Text","") for x in d.get("RelatedTopics",[])[:5])
            ])).lower()
            if SERIES_A_RE.search(text):
                return {"stage":_highest(text),"source":"web_search","note":"series signals in DDG"}
            if SEED_RE.search(text):
                return {"stage":"seed","source":"web_search","note":"seed signals in DDG"}
            if RAISE_RE.search(text):
                return {"stage":"seed","source":"web_search","note":"raise signals in DDG"}
            time.sleep(0.4)
        except: pass
    return None

def check(org, repo, homepage=""):
    # 1. Try Crunchbase
    r = try_crunchbase(org)
    if r: return r
    time.sleep(0.3)

    # 2. Try org's stated homepage (from GitHub repo metadata)
    if homepage:
        r = try_homepage(homepage)
        if r and isinstance(r, dict): return r
    time.sleep(0.3)

    # 3. Try GitHub org API — also gets the blog URL if homepage was empty
    gh_result = try_gh_org(org)
    if isinstance(gh_result, dict): return gh_result
    if isinstance(gh_result, str) and gh_result and not homepage:
        # gh_result is the blog URL
        r = try_homepage(gh_result)
        if r and isinstance(r, dict): return r
    time.sleep(0.3)

    # 4. DDG snippet search
    r = try_ddg_snippet(org, repo)
    if r: return r

    return {"stage":"unknown","source":"all_failed","note":"no signals found"}

def main():
    repos = json.load(open(sys.argv[1]) if len(sys.argv)>1 else sys.stdin)
    enriched, cache = [], {}
    for i, repo in enumerate(repos):
        org = repo["org"]
        print(f"[{i+1}/{len(repos)}] Funding: {org}", file=sys.stderr)
        if org not in cache:
            homepage = repo.get("homepage","") or ""
            cache[org] = check(org, repo["repo"], homepage)
            print(f"  → {cache[org]['stage']} ({cache[org]['source']})", file=sys.stderr)
            time.sleep(0.8)
        else:
            print(f"  → {cache[org]['stage']} (cached)", file=sys.stderr)
        repo["funding"] = cache[org]
        repo["is_post_series_a"] = cache[org]["stage"] in ("series-a","series-b+")
        enriched.append(repo)
    excl = sum(1 for r in enriched if r["is_post_series_a"])
    print(f"[info] {excl}/{len(enriched)} flagged post-Series-A", file=sys.stderr)
    print(json.dumps(enriched, indent=2))

if __name__ == "__main__": main()
