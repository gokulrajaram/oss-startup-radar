#!/usr/bin/env python3
import argparse, json, os, sys, time, requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if GITHUB_TOKEN: GH["Authorization"] = f"Bearer {GITHUB_TOKEN}"

AI_TOPICS = {"ai","llm","agent","agents","ml","machine-learning","deep-learning","rag","embeddings","inference","fine-tuning","finetuning","nlp","generative-ai","diffusion","multimodal","computer-vision","transformer","gpt","llama","mistral","vector-database","vector-search","mlops","pytorch","tensorflow","jax","triton","cuda","openai","anthropic","huggingface","langchain","autonomous-agents","copilot","code-generation","text-to-image","speech-recognition","foundation-model","benchmark","synthetic-data","mcp","model-context-protocol","claude-code","codex","claude","gemini-api","ai-agent","ai-coding","agentic"}
AI_KW = ["ai","llm","model","neural","gpt","agent","inference","train","embed","vector","diffus","rag","retrieval","fine-tun","prompt","orchestrat","autonomous","copilot","coding agent","ai agent","zero-human"]

def gh_search(q, limit=25):
    results, page = [], 1
    while len(results) < limit:
        try:
            r = requests.get("https://api.github.com/search/repositories", headers=GH,
                params={"q":q,"sort":"stars","order":"desc","per_page":min(30,limit),"page":page}, timeout=15)
            if r.status_code == 403: print("[warn] GH rate limit", file=sys.stderr); break
            r.raise_for_status()
            items = r.json().get("items",[])
            if not items: break
            results.extend(items); page += 1; time.sleep(0.3)
        except Exception as e: print(f"[warn] GH search: {e}", file=sys.stderr); break
    return results[:limit]

def is_ai(raw):
    topics = set(raw.get("topics") or [])
    desc = (raw.get("description") or "").lower()
    return bool(AI_TOPICS & topics) or any(k in desc for k in AI_KW)

def norm(raw, src):
    fn = raw.get("full_name","")
    if not fn or "/" not in fn: return None
    stars = raw.get("stargazers_count",0) or 0
    if stars < 50 or stars > 300_000: return None
    if raw.get("fork") or raw.get("private"): return None
    if not is_ai(raw): return None
    return {"full_name":fn,"org":fn.split("/")[0],"repo":fn.split("/")[1],
            "description":(raw.get("description") or "").strip(),"stars":stars,
            "language":raw.get("language") or "","topics":raw.get("topics") or [],
            "homepage":raw.get("homepage") or "","created_at":raw.get("created_at") or "",
            "pushed_at":raw.get("pushed_at") or raw.get("updated_at") or "",
            "html_url":raw.get("html_url") or f"https://github.com/{fn}","source":src}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    if not GITHUB_TOKEN: print("[warn] GITHUB_TOKEN not set", file=sys.stderr)

    seen, candidates = set(), []
    # Recent repos (created < 15 months ago)
    recent_q = [
        "topic:llm stars:100..300000 created:>2024-01-01",
        "topic:ai-agent stars:100..300000 created:>2024-01-01",
        "topic:rag stars:100..300000 created:>2024-01-01",
        "topic:mcp stars:50..300000 created:>2024-01-01",
        "topic:generative-ai stars:100..300000 created:>2024-01-01",
        "topic:inference stars:100..300000 created:>2024-01-01",
        "topic:embeddings stars:50..300000 created:>2024-01-01",
        "topic:fine-tuning stars:50..300000 created:>2024-01-01",
        "topic:ai stars:200..100000 created:>2024-04-01",
        "topic:claude-code stars:500..300000",
        "topic:agentic stars:100..300000 created:>2024-01-01",
        # Catch-all: very high-momentum recent repos regardless of topic (is_ai filter still applies)
        "stars:2000..300000 created:>2025-09-01",
        "stars:3000..20000 created:>2026-01-01",   # lower range catches cmux-sized repos (≥3k to reduce personal project noise)
    ]
    # Older repos only if recently active (momentum proxy)
    momentum_q = [
        "topic:llm stars:500..100000 pushed:>2024-10-01 created:<2024-01-01",
        "topic:ai-agent stars:200..80000 pushed:>2024-10-01 created:<2024-01-01",
        "topic:rag stars:200..80000 pushed:>2024-10-01 created:<2024-01-01",
        "topic:machine-learning stars:500..80000 pushed:>2025-01-01 created:<2024-01-01",
    ]
    catchall = {"stars:2000..300000 created:>2025-09-01", "stars:500..20000 created:>2026-01-01"}
    for q in recent_q + momentum_q:
        limit = 40 if q in catchall else 20
        print(f"[info] Searching: {q[:60]}", file=sys.stderr)
        for raw in gh_search(q, limit=limit):
            r = norm(raw, "github_search")
            if r and r["full_name"] not in seen:
                seen.add(r["full_name"]); candidates.append(r)
        time.sleep(0.3)

    candidates.sort(key=lambda r: r["stars"], reverse=True)
    print(f"[info] Total candidates: {len(candidates)}", file=sys.stderr)
    print(json.dumps(candidates[:args.limit], indent=2))

if __name__ == "__main__": main()
