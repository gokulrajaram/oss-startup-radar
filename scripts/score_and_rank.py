#!/usr/bin/env python3
import json, math, sys
from datetime import datetime, timezone

TOP_N = 25
NOW = datetime.now(timezone.utc)

THEMES = {
    "Agentic AI & Autonomous Workflows": ["agent","agentic","autonomous","workflow","orchestrat","multi-agent","tool use","plan","execute"],
    "LLM Inference & Serving": ["inference","serv","deploy","runtime","quantiz","gguf","throughput","latency","vllm","llama.cpp"],
    "RAG & Knowledge Retrieval": ["rag","retrieval","vector","embed","knowledge","search","index","chunk","document","semantic","graph"],
    "Developer Tooling & Code Generation": ["code","coding","developer","copilot","autocomplete","ide","engineer","debug","terminal","cli"],
    "Multimodal & Vision Models": ["multimodal","vision","image","video","audio","speech","vlm","ocr","caption","visual"],
    "Fine-tuning & Training": ["fine-tun","finetun","train","lora","rlhf","dpo","distill","synthetic data","align"],
    "AI Memory & Personalization": ["memory","persist","session","personaliz","long-term","remember","recall"],
    "Evaluation & Benchmarking": ["eval","benchmark","assess","metric","judge","leaderboard","accuracy"],
}
THEME_OBS = {
    "Agentic AI & Autonomous Workflows": "Agentic frameworks are the dominant new-company formation theme in AI right now. Most launched in the last 12 months, and the fastest-growing use tool-use + planning loops rather than simple prompt chaining.",
    "LLM Inference & Serving": "With open models matching closed ones on quality, infrastructure efficiency has become the moat. Projects that unlock local or cheap deployment are growing fastest.",
    "RAG & Knowledge Retrieval": "Graph-enhanced retrieval (knowledge graphs + vector search) is pulling ahead of naive chunking. The new standard for enterprise RAG is hybrid retrieval + reranking.",
    "Developer Tooling & Code Generation": "Code-gen tooling is moving up the stack from autocomplete to full software-engineering agents that plan, edit, and test. CLI-native tools are outgrowing IDE plugins.",
    "Multimodal & Vision Models": "Multimodal is now table stakes for new model releases. Startup action is in efficient on-device VLMs and video understanding pipelines.",
    "Fine-tuning & Training": "LoRA variants dominate because they make fine-tuning accessible without massive GPU budgets. Newest wave: synthetic data generation to bootstrap fine-tuning datasets cheaply.",
    "AI Memory & Personalization": "Persistent memory for AI agents is the newest high-growth subcategory — several repos launched to tens of thousands of stars in weeks. The core problem: LLMs forget everything between sessions.",
    "Evaluation & Benchmarking": "Eval has emerged as a standalone discipline as model proliferation makes systematic measurement essential. Several companies are forming specifically around LLM evaluation infrastructure.",
}

def composite(r): return round(0.60*r.get("velocity_score",0) + 0.40*r.get("reddit",{}).get("reddit_score",0), 1)

def classify_themes(repos):
    buckets = {t: [] for t in THEMES}
    for repo in repos:
        text = " ".join([repo.get("description",""), " ".join(repo.get("topics",[])),
                         (repo.get("reddit",{}).get("top_post") or {}).get("title","")]).lower()
        matched = sorted([(t, sum(1 for k in kws if k in text)) for t,kws in THEMES.items() if any(k in text for k in kws)],
                         key=lambda x: x[1], reverse=True)
        for t,_ in matched[:2]: buckets[t].append(repo)
    ranked = sorted([(t,rs) for t,rs in buckets.items() if rs], key=lambda x: len(x[1]), reverse=True)[:5]
    out = []
    for name, members in ranked:
        seen, top3 = set(), []
        for r in sorted(members, key=lambda x: x.get("composite_score",0), reverse=True):
            if r["full_name"] not in seen: seen.add(r["full_name"]); top3.append(r)
            if len(top3)==3: break
        out.append({"name":name,"count":len(members),"top_repo_names":[r["repo"] for r in top3],"observation":THEME_OBS.get(name,"")})
    return out

def fmt(n):
    if isinstance(n,(int,float)):
        if n>=1_000_000: return f"{n/1_000_000:.1f}M"
        if n>=1_000: return f"{n/1_000:.1f}k"
        return str(int(n))
    return str(n)

def fmt_age(d):
    if d is None: return "unknown age"
    if d<30: return f"{d}d old"
    if d<365: return f"{round(d/30)}mo old"
    return f"{d/365:.1f}yr old"

LANG_E = {"Python":"🐍","Rust":"🦀","TypeScript":"🔷","JavaScript":"🟨","Go":"🐹","C++":"⚡","C":"⚡"}
MOM_L = {"very_hot":"🔥🔥 Very Hot","hot":"🔥 Hot","growing":"📈 Growing","mature":"📊 Mature"}
FUND_L = {"pre-seed":"Pre-seed","seed":"Seed 🌱","series-a":"Series A 🅰️","series-b+":"Series B+","unknown":"Unknown (pre-A)"}

def build_report(repos, themes, n_excl):
    date_str = NOW.strftime("%B %d, %Y")
    L = [
        f"# OSS Startup Radar — {date_str}",
        f"*Pre-Series-B open source AI/ML · 30/60/90-day star velocity + Reddit buzz · {n_excl} Series B+ repos excluded · Series A included and labeled 🅰️*",
        "", "---", "", "## Top 5 Trending Themes", "",
    ]
    for i,t in enumerate(themes,1):
        L += [f"### {i}. {t['name']}", t["observation"],
              f"**Key projects:** {', '.join(f'`{n}`' for n in t['top_repo_names'])}", ""]

    L += ["---", "", f"## Top {len(repos)} Fast-Growing Pre-Series-B Projects", ""]

    # Compact summary table — founders column filled in by linkedin_lookup.py (Step 6)
    L.append("| # | Repo | ⭐ | +30d | Description | Founders |")
    L.append("|---|------|----|------|-------------|----------|")
    for rank, repo in enumerate(repos, 1):
        vel  = repo.get("velocity", {})
        total      = vel.get("total_stars", repo.get("stars", 0))
        gained_30d = vel.get("30d", {}).get("gained", 0)
        desc = (repo.get("description") or "").strip()
        desc_short = (desc[:75] + "…") if len(desc) > 75 else desc
        L.append(f"| {rank} | [{repo['repo']}]({repo['html_url']}) | {fmt(total)} | +{fmt(gained_30d)} | {desc_short} | `FOUNDERS_PLACEHOLDER_{rank}` |")
    L.append("")

    for rank, repo in enumerate(repos, 1):
        vel   = repo.get("velocity", {})
        reddit= repo.get("reddit", {})
        fund  = repo.get("funding", {})
        top   = reddit.get("top_post") or {}
        lang  = repo.get("language","")
        total = vel.get("total_stars", repo.get("stars",0))
        age   = vel.get("age_days")
        mom   = vel.get("recent_momentum_label","")
        fs    = fund.get("stage","unknown")

        L.append(f"### #{rank} · {repo['repo']} ⭐ {fmt(total)}")
        meta = [f"[{repo['full_name']}]({repo['html_url']})"]
        if lang: meta.append(f"{LANG_E.get(lang,'')} {lang}".strip())
        meta += [fmt_age(age), MOM_L.get(mom,mom), f"Funding: {FUND_L.get(fs,'?')}"]
        L.append("**" + " | ".join(meta) + "**")
        L.append("")
        L.append("| Window | Stars gained | Stars/day |")
        L.append("|--------|-------------|-----------|")
        for w in ["30d","60d","90d"]:
            wd = vel.get(w,{})
            g = wd.get("gained","—"); pd = wd.get("per_day","—")
            L.append(f"| {w} | {('+'+fmt(g)) if isinstance(g,int) else '—'} | {f'{pd}/day' if isinstance(pd,(int,float)) else '—'} |")
        L.append("")
        rc,ra,rs = reddit.get("post_count",0), reddit.get("avg_score",0), reddit.get("reddit_score",0)
        rr,rh = reddit.get("reddit_count",rc), reddit.get("hn_count",0)
        src_label = "Community (30d)" if rh > 0 else "Reddit (30d)"
        breakdown = f"{rr}r+{rh}hn" if rh > 0 else f"{rc} posts"
        if top:
            t80 = top.get("title","")[:80]; ts = top.get("score",0)
            sub = top.get("subreddit","")
            src = f"r/{sub}" if sub and not sub.startswith("r/") else (sub or "")
            L.append(f"**{src_label}:** {breakdown} · avg {ra:.0f}↑ · score: {rs} · top: [\"{t80}\"]({top.get('permalink','')}) ({fmt(ts)}↑ {src})")
        else:
            L.append(f"**{src_label}:** {breakdown} · avg {ra:.0f}↑ · score: {rs}")
        L.append("")
        L.append(f"**What it is:** {repo.get('description','').strip() or '*(no description)*'}")
        L.append("")
        comm_label = "Community" if rh > 0 else "Reddit"
        L.append(f"*Composite: {repo.get('composite_score',0)} · Velocity: {repo.get('velocity_score',0)} · {comm_label}: {rs}*")
        L.append(""); L.append("---"); L.append("")

    L.append("## Methodology")
    L.append("Star velocity via GitHub Stargazers API (timestamped). Age multiplier: <6mo→2×, <1yr→1.6×, <1.5yr→1.2×, >2yr→0.5× (overridden if >30% of total stars came in last 90d). Community signal via last30days (Reddit + HN) — posts counted only if title/snippet/URL contains the repo or org name; HN posts weighted 2×. Funding: Crunchbase + org homepage + GitHub org API + DDG — Series A+ excluded. Composite: 60% velocity + 40% community.")
    return "\n".join(L)

NON_STARTUP_ORGS = {
    "microsoft","google","googleworkspace","meta","amazon","apple","facebook","openai","deepmind",
    "ibm","nvidia","salesforce","adobe","intel","qualcomm","databricks","huggingface","tensorflow",
    "pytorch","apache","kubernetes","anthropics","mistralai","chromedevtools","volcengine",
    "datawhalechina","bytedance","alibaba","tencent","baidu","aws","azure","github","a2aproject",
    "langchain-ai","coze-dev","agentscope-ai","sgl-project","hkuds","funaudiollm","modelscope",
    "chatchat-space","pdfmathtranslate","2noise","rsnext","rssnext","rssplusone",
    "karpathy","addyosmani","vercel-labs","mattpocock","thu-maic","ultraworkers","hesamsheikh",
    "tanweai","cft0808","saturndec","aiming-lab","snarktank","yeachan-heo","anthropic",
    # Amazon's Strands, personal accounts, academic
    "strands-agents","geeeekexplorer","ufomiao","wshobson","ruvnet","panniantong","jackwener","0x4m4",
    "santifer","zhulinsen","zoicware",
    "grab","conardli","78",
    "yamadashy","d4vinci",
    "kvcache-ai",
}
# Known Series-B+ orgs that our automated funding check misses (Series A orgs are now included)
KNOWN_SERIES_B_PLUS = {"onyx-dot-app","deepset-ai","rssplusone","rssnext","wandb"}
NON_STARTUP_DESC = [
    "curated list","awesome list","tutorial","learning resource","cheat sheet","collection of",
    "a list of","resources for","getting started","study guide","interview prep","course material",
    "library of","installable github","agentic skills for","skills for claude","skills for cursor",
    "extracted system prompts","leaked system","prompt leak","从零开始","教程","课程",
    "claude code skill","coding assistant skill","agent skill","single claude.md","from my .claude",
    "personal directory","my personal","my skills","a skill that","skill that ","clone any website",
    "cloner template","starter template","boilerplate","workflow skills","tips for getting","tips for claude",
    "45 tips","72 workflow","claude code plugin","local knowledge graph for claude","development loop for claude",
    "autonomous ai development loop","intelligent exit detection","running repeatedly until",
]
NON_STARTUP_NAME = [
    "awesome-","learn-","study-","tutorial","cheatsheet","roadmap","interview","awesome_",
    "skills-for-","prompts_leak","system_prompts","leaks","game-studios","karpathy-skills",
    "cloner-template","website-cloner","claude-code-tips","claude-hud","ralph-claude",
    "ppt-master","code-review-graph","oh-my-","waoowaoo",
]

def is_startup(repo):
    org = repo.get("org","").lower()
    name = repo.get("repo","").lower()
    desc = repo.get("description","").lower()
    if org in NON_STARTUP_ORGS: return False
    if any(name.startswith(p) for p in NON_STARTUP_NAME): return False
    if any(p in desc for p in NON_STARTUP_DESC): return False
    return True

def main():
    repos = json.load(open(sys.argv[1]) if len(sys.argv)>1 else sys.stdin)
    for r in repos: r["composite_score"] = composite(r)
    # Fix 2: Velocity floor — require ≥20 stars in best window (30/60/90d)
    before_vel = len(repos)
    def best_window_gained(r):
        v = r.get("velocity", {})
        return max(v.get("30d",{}).get("gained",0),
                   v.get("60d",{}).get("gained",0),
                   v.get("90d",{}).get("gained",0))
    repos = [r for r in repos if best_window_gained(r) >= 20]
    print(f"[info] Velocity floor: {before_vel} → {len(repos)} repos (≥20 stars in any window)", file=sys.stderr)
    # Inflation filter: very young repos with huge star counts but no community discussion
    # are almost always star-bombing artifacts (e.g. fake "open-source X alternative" repos).
    def is_inflated(r):
        stars = r.get("velocity", {}).get("total_stars", r.get("stars", 0))
        age = r.get("velocity", {}).get("age_days") or 9999
        red = r.get("reddit", {})
        weighted = red.get("reddit_count", 0) + 2 * red.get("hn_count", 0)
        return stars > 3000 and weighted < 5 and age < 60
    before_inf = len(repos)
    dropped_inf = [r["full_name"] for r in repos if is_inflated(r)]
    repos = [r for r in repos if not is_inflated(r)]
    print(f"[info] Inflation filter: {before_inf} → {len(repos)} repos · dropped: {dropped_inf}", file=sys.stderr)
    # Fix 3: Filter non-startups (awesome lists, big tech orgs, tutorial repos)
    before_ns = len(repos)
    repos = [r for r in repos if is_startup(r)]
    print(f"[info] Non-startup filter: {before_ns} → {len(repos)} repos", file=sys.stderr)
    # Override funding for known Series-B+ orgs
    for r in repos:
        if r.get("org","").lower() in KNOWN_SERIES_B_PLUS:
            r["is_post_series_a"] = True
            r["funding"] = {"stage":"series-b+","source":"known_override","note":"known Series B+ from training data"}
    included = [r for r in repos if not r.get("is_post_series_a",False)]
    excluded = [r for r in repos if r.get("is_post_series_a",False)]
    print(f"[info] Excluded {len(excluded)} Series B+: {[r['full_name'] for r in excluded[:8]]}", file=sys.stderr)
    included.sort(key=lambda r: r["composite_score"], reverse=True)
    top = included[:TOP_N]
    themes = classify_themes(top)
    # Write ranked JSON for downstream steps (e.g. linkedin_lookup.py)
    with open("/tmp/ranked.json", "w") as f:
        json.dump(top, f)
    print(build_report(top, themes, len(excluded)))

if __name__ == "__main__": main()
