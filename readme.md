# Composio Toolkit Parity ( Research & Execution Agent )

1. It is a research pipeline that scores 100 apps in the list using AI-agent "buildability": auth method, self-serve vs gated, API surface, existing MCP, and a verdict.
2. Then verifies its own output against a risk-weighted sample. Includes a live LangGraph execution agent that calls Composio-powered tools for each app.

---

## What's in here

```
app.json               100 researched app records (the main dataset)
verification.json      20-app verification sample: first pass vs verified
execution_agent.py     LangGraph agent: loops all 100 apps via Composio SDK
research_agent.py      3-stage research agent (discover -> extract -> cross-check)
verify_agent.py        Independent fact-check pass
index.html             Single-page case study (the actual deliverable)
.env.example           Environment variable template (copy to .env)
.gitignore             Excludes .env and secrets from git
readme.md              This file
```

---

## Quick Start

### 1. View the Case Study UI (Recommended)
This launches the interactive frontend where you can view the 100 researched apps, the data patterns, and test the live agent.

```bash
# Start the backend server
python server.py
```
Then, open `http://localhost:8000` in your web browser.

### 2. Run the Headless Execution Agent
If you want to run the LangGraph agent across all apps in your terminal without the UI:
```bash
python execution_agent.py
```

### 3. Run the Research Data Pipeline
To regenerate the `app.json` data from scratch using the research agent:
```bash
python research_agent.py
```

---

## Environment Variables
Create a `.env` file in the root directory (you can copy `.env.example`).

| Variable | Description |
|---|---|
| `COMPOSIO_API_KEY` | Your Composio API key |
| `NVIDIA_API_KEY` | API key for `meta/llama-3.1-8b-instruct` |
