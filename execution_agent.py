"""
Execution Agent for Composio and LangGraph

Iterates through apps in app.json and checks Composio connectivity.
If an app requires authentication, it prompts the user to visit a URL.
Once connected, it fetches the appropriate tools and makes a safe read-only call.

Usage:
    python execution_agent.py
"""

import json
import os
import sys
from pathlib import Path

# Load .env variables
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:
    pass  # dotenv is optional; fall back to manually set env vars

from composio import Composio
from composio_langchain import LangchainProvider
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Configuration
COMPOSIO_API_KEY = os.environ.get("COMPOSIO_API_KEY", "ak_6w2V6MrVJv7q8CJgIlKP")
NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "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")
NVIDIA_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL    = os.environ.get("NVIDIA_MODEL",    "meta/llama-3.1-8b-instruct")
USER_ID = "composio_research_user"


def get_composio_client() -> Composio:
    """Returns an initialized Composio client."""
    return Composio(api_key=COMPOSIO_API_KEY, provider=LangchainProvider())


def check_or_authorize(client: Composio, slug: str, app_name: str) -> bool:
    """
    Checks if a toolkit exists and if the user is authenticated.
    If not authenticated, it creates a config and returns an authorization URL.
    """
    # Check if the app is in the catalog
    try:
        toolkit = client.toolkits.get(slug=slug)
        if not toolkit:
            print(f"       [CATALOG] '{slug}' not found in Composio catalog.")
            return False
    except Exception as e:
        print(f"       [CATALOG] '{slug}' not in Composio catalog: {type(e).__name__}")
        return False

    # Check if we already have an active connection
    try:
        accounts_resp = client.connected_accounts.list(
            toolkit_slugs=[slug],
            user_ids=[USER_ID],
            statuses=["ACTIVE"],
        )
        items = getattr(accounts_resp, "items", []) or []
        if items:
            print(f"       [AUTH] Already connected to {app_name}.")
            return True
    except Exception:
        pass

    print(f"       [AUTH] No active connection — initiating OAuth/API-key flow...")

    # Create a new connection configuration
    try:
        auth_configs_resp = client.auth_configs.list(toolkit_slug=slug)
        config_items = getattr(auth_configs_resp, "items", []) or []

        if not config_items:
            print(f"       [AUTH] No auth config — creating Composio-managed one...")
            try:
                new_config = client.auth_configs.create(
                    toolkit=slug,
                    options={"type": "use_composio_managed_auth"},
                )
                auth_config_id = new_config.id
                print(f"       [AUTH] Auth config created: {auth_config_id}")
            except Exception as create_err:
                err_str = str(create_err)
                if "DefaultAuthConfigNotFound" in err_str or "use_custom_auth" in err_str:
                    # Composio doesn't have managed creds for this app (e.g. Pipedrive)
                    # The user would need to supply their own OAuth app client_id/secret
                    print(f"       [AUTH] Composio has no managed credentials for '{slug}'.")
                    print(f"             To connect, supply your own OAuth app credentials in the Composio dashboard.")
                    return False
                raise
        else:
            auth_config_id = config_items[0].id
            print(f"       [AUTH] Using existing auth config: {auth_config_id}")

    except Exception as e:
        print(f"       [AUTH] Could not get/create auth config: {e}")
        return False

    # ── Step 4: Use connected_accounts.link() — the new v3 API ───────────────
    # NOTE: connected_accounts.initiate() is retired for Composio-managed OAuth.
    # connected_accounts.link() is the correct replacement.
    try:
        connection_request = client.connected_accounts.link(
            user_id=USER_ID,
            auth_config_id=auth_config_id,
        )
        redirect_url = getattr(connection_request, "redirect_url", None)

        if redirect_url:
            print(f"\n       >>> ACTION REQUIRED <<<")
            print(f"       Authorize '{app_name}' by visiting this URL in your browser:")
            print(f"\n       {redirect_url}\n")
            answer = input(f"       Press Enter after completing authorization, or 's' to skip: ").strip().lower()
            if answer == "s":
                print(f"       Skipped.")
                return False
            print(f"       [AUTH] Authorization confirmed for {app_name}.")
        else:
            print(f"       [AUTH] Connection created (no redirect — likely API key auth).")
            print(f"             Provide API key credentials via Composio dashboard if needed.")

        return True

    except Exception as e:
        print(f"       [AUTH] Failed to create connection link: {e}")
        return False


def main():
    # Using the NVIDIA API key provided for LLM authentication.

    # Load app list from json
    app_json_path = Path(__file__).parent / "app.json"
    try:
        with open(app_json_path, "r", encoding="utf-8") as f:
            apps = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] app.json not found at {app_json_path}")
        sys.exit(1)

    print(f"\nLoaded {len(apps)} apps from app.json")
    print(f"Composio API key: {COMPOSIO_API_KEY[:8]}...")
    print(f"LLM: NVIDIA {NVIDIA_MODEL}")
    print(f"NVIDIA base URL: {NVIDIA_BASE_URL}")
    print(f"Composio user/entity: {USER_ID}\n")

    # Initialize clients
    composio_client = get_composio_client()
    llm = ChatOpenAI(
        model=NVIDIA_MODEL,
        api_key=NVIDIA_API_KEY,
        base_url=NVIDIA_BASE_URL,
        temperature=0.2,
        top_p=0.7,
        max_tokens=1024,
    )

    # Verify the Composio API key is valid
    try:
        composio_client.toolkits.get(slug="github")  # quick sanity check
        print(f"Composio client ready. (API key valid)")
    except Exception as e:
        print(f"[WARN] Composio sanity check failed: {e}")

    # Start main execution loop
    print("\n" + "=" * 60)
    print("Starting execution loop over 100 apps...")
    print("Non-buildable apps are skipped automatically.")
    print("=" * 60)

    results = []

    for app_data in apps:
        raw_name = app_data["app"]
        slug = (raw_name.lower()
                .replace(" ", "").replace(".", "")
                .replace("-", "").replace("(", "").replace(")", ""))
        verdict = app_data.get("verdict", "")

        print(f"\n[{app_data['id']:>3}] {raw_name}  (slug: {slug})")
        print(f"       Verdict: {verdict}")

        # Skip apps that cannot be self-serve built
        if "Not buildable" in verdict:
            print(f"       >> Skipped (research verdict: not buildable self-serve)")
            results.append({"app": raw_name, "slug": slug, "status": "skipped"})
            continue

        try:
            # Ensure app is authorized
            authorized = check_or_authorize(composio_client, slug, raw_name)
            if not authorized:
                results.append({"app": raw_name, "slug": slug, "status": "no_catalog_or_skipped"})
                continue

            # Fetch available tools for this app
            try:
                app_session = composio_client.create(
                    user_id=USER_ID,
                    toolkits=[slug],
                    manage_connections={"enable": False},
                    workbench={"enable": False},
                )
                tools = list(app_session.tools())
            except Exception as e:
                print(f"       [TOOLS] Could not fetch tools: {e}")
                results.append({"app": raw_name, "slug": slug, "status": f"tool_error: {e}"})
                continue

            if not tools:
                print(f"       [TOOLS] No tools returned for '{slug}'.")
                results.append({"app": raw_name, "slug": slug, "status": "no_tools"})
                continue

            print(f"       [TOOLS] {len(tools)} tools available in Composio.")

            # Run the agent with tools
            agent = create_react_agent(llm, tools)
            prompt = (
                f"You are verifying the Composio integration for '{raw_name}'. "
                f"Call ONE safe, read-only tool (e.g. list channels, get current user). "
                f"If a tool requires a specific ID (like a profile_id, channel_id, etc.) that you do not have, DO NOT call it. "
                f"DO NOT create, update, or delete anything. "
                f"Briefly summarize what the tool returned."
            )

            print(f"       [AGENT] Invoking LangGraph agent...")
            response = agent.invoke({"messages": [("user", prompt)]})
            result_text = response["messages"][-1].content
            if len(result_text) > 300:
                result_text = result_text[:300] + "..."
            print(f"       [AGENT] Result: {result_text}")
            results.append({"app": raw_name, "slug": slug, "status": "success", "result": result_text})

        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Exiting.")
            break
        except Exception as e:
            print(f"       [ERROR] {e}")
            results.append({"app": raw_name, "slug": slug, "status": f"error: {e}"})

    # Print final summary
    print("\n" + "=" * 60)
    success = [r for r in results if r.get("status") == "success"]
    skipped = [r for r in results if "skip" in r.get("status", "")]
    no_catalog = [r for r in results if r.get("status") == "no_catalog_or_skipped"]
    errors = [r for r in results if "error" in r.get("status", "")]

    print(f"Execution complete.")
    print(f"  Successful tool calls : {len(success)}")
    print(f"  Skipped (not buildable): {len(skipped)}")
    print(f"  Not in catalog        : {len(no_catalog)}")
    print(f"  Errors                : {len(errors)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
