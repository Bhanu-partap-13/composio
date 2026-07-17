import json
import os
import sys
import time
from dataclasses import dataclass, asdict

import anthropic
from composio import Composio

EXTRACTION_SCHEMA = {
    "app": "string",
    "category": "string",
    "desc": "one-line description of what the app does",
    "auth": "OAuth2 | API key | Basic | Token | Other (say which)",
    "gate": "Self-serve (how) OR Gated (why - admin approval / paid plan / partner program / contact sales)",
    "api": "REST/GraphQL/gRPC, and roughly how broad the surface is",
    "mcp": "does an official or community MCP server already exist? name it or say None",
    "verdict": "Buildable today | Buildable with caveats | Not buildable self-serve",
    "blocker": "the single biggest blocker, or None",
    "evidence": "the doc URL(s) actually used",
    "conf": "high | medium | low  (low = could not find authoritative public docs)"
}

SYSTEM_PROMPT = f"""You are a toolkit-research analyst. You will be given raw
scraped text from an app's developer documentation (and/or search results
about it). Extract ONLY what is verifiable from the provided text into this
exact JSON schema:

{json.dumps(EXTRACTION_SCHEMA, indent=2)}

Rules:
- Never invent a URL, auth method, or plan name that isn't in the source text.
- If the source text does not clearly answer a field, set conf to "low" and
  say so plainly in that field rather than guessing.
- "Gated" means a normal developer cannot get a working credential today
  without an approval step, existing paid account, or a sales conversation.
- Output ONLY the JSON object, nothing else.
"""


@dataclass
class AppRecord:
    app: str
    category: str
    desc: str
    auth: str
    gate: str
    api: str
    mcp: str
    verdict: str
    blocker: str
    evidence: str
    conf: str


def discover(app_name: str, hint_url: str, web_search_fn) -> str:
    """Stage 1: gather raw text about the app's auth/API/gating.
    web_search_fn is an injectable search+fetch function so this can run
    against any search backend (Brave/Serper/Bing/etc in production)."""
    queries = [
        f"{app_name} API documentation authentication",
        f"{app_name} API self-serve OR free developer account OR sandbox",
        f"{app_name} MCP server",
    ]
    corpus = []
    for q in queries:
        corpus.append(web_search_fn(q))
        time.sleep(0.2)  # be polite to the search backend
    return "\n\n---\n\n".join(corpus)


def extract(app_name: str, raw_text: str, client: anthropic.Anthropic) -> dict:
    """Stage 2: LLM turns raw docs into the structured record."""
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"App: {app_name}\n\nRaw source material:\n{raw_text[:12000]}"
        }]
    )
    text = resp.content[0].text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(text)


def cross_check_composio(app_name: str, composio: Composio) -> str:
    """Stage 3: ask Composio directly whether a toolkit already exists.
    This is the one part of the record we don't have to infer - Composio's
    own catalog is ground truth for 'does a toolkit already exist'."""
    try:
        toolkits = composio.toolkits.get(search=app_name)
        if toolkits:
            return f"Existing Composio toolkit found: {toolkits[0].slug}"
        return "No existing Composio toolkit"
    except Exception as e:
        return f"Composio lookup failed: {e}"


def research_one(app_name: str, hint_url: str, web_search_fn,
                  client: anthropic.Anthropic, composio: Composio) -> dict:
    raw = discover(app_name, hint_url, web_search_fn)
    record = extract(app_name, raw, client)
    record["composio_status"] = cross_check_composio(app_name, composio)
    return record


def main(input_path: str):
    apps = json.load(open(input_path))
    client = anthropic.Anthropic()
    composio = Composio()

    def web_search_fn(query: str) -> str:
        # Placeholder - wire this to your search provider of choice.
        # In this deliverable, the equivalent searches were run through
        # Claude's native web_search tool; see README "How this was actually run".
        raise NotImplementedError("Wire up a search backend here")

    results = []
    for a in apps:
        print(f"Researching {a['app']}...", file=sys.stderr)
        try:
            results.append(research_one(a["app"], a.get("hint_url", ""),
                                         web_search_fn, client, composio))
        except Exception as e:
            results.append({"app": a["app"], "error": str(e), "conf": "low"})

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "apps_input.json")