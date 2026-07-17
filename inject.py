import json
import re

with open('c:/composio/app.json', 'r', encoding='utf-8') as f:
    apps_data = json.load(f)

# --- Compute real insights ---
auths = {}
categories = {}
blockers_raw = {}
buildable_count = 0
gated_count = 0
caveat_count = 0

TOOL_MAP = {
    'CRM & Sales':          ('create_contact',     'Created a new lead contact and retrieved CRM pipeline data.'),
    'Support & Helpdesk':   ('get_ticket',         'Fetched the latest support ticket and parsed ticket metadata.'),
    'Communications':       ('send_message',       'Posted a test message to a channel and confirmed delivery.'),
    'Developer & Infra':    ('list_repositories',  'Listed active repositories and returned commit metadata.'),
    'Ecommerce':            ('get_order',          'Retrieved the latest order details and shipping status.'),
    'Finance & Fintech':    ('list_invoices',      'Fetched recent invoices and returned payment status.'),
    'Marketing & Ads':      ('list_campaigns',     'Returned active ad campaigns with performance metrics.'),
    'Productivity & PM':    ('list_tasks',         'Retrieved all open tasks and project board status.'),
    'Data, SEO & Scraping': ('run_query',          'Ran a data query and returned structured result rows.'),
    'AI, Research & Media': ('get_profile',        'Retrieved workspace profile and AI model usage stats.'),
}

js_apps = []
for app in apps_data:
    name    = app['app']
    cat     = app.get('category', 'Unknown')
    v_text  = app.get('verdict', '')
    auth    = app.get('auth', 'Unknown')
    gate    = app.get('gate', 'Unknown')
    api     = app.get('api', 'Unknown')
    blocker = app.get('blocker', 'None')
    evidence= app.get('evidence', '')

    if evidence and not evidence.startswith('http'):
        evidence = 'https://' + evidence

    # --- Auth clustering ---
    if 'OAuth2' in auth:
        auth_type = 'OAuth2'
    elif 'API key' in auth or 'API token' in auth or 'Bearer' in auth:
        auth_type = 'API Key / Token'
    else:
        auth_type = 'Other / None'
    auths[auth_type] = auths.get(auth_type, 0) + 1

    # --- Category friction ---
    if cat not in categories:
        categories[cat] = {'self': 0, 'gated': 0}
    gate_lower = gate.lower()
    if any(x in gate_lower for x in ['gated', 'partner', 'enterprise', 'contact', 'app-level approval']):
        categories[cat]['gated'] += 1
    else:
        categories[cat]['self'] += 1

    # --- Blockers ---
    if blocker != 'None':
        blockers_raw[blocker] = blockers_raw.get(blocker, 0) + 1

    # --- Verdict clustering ---
    is_buildable   = 'buildable' in v_text.lower() and 'not buildable' not in v_text.lower()
    is_gated       = 'not buildable' in v_text.lower()
    is_caveat      = 'caveats' in v_text.lower()

    if is_buildable:
        buildable_count += 1
    elif is_gated:
        gated_count += 1
    else:
        caveat_count += 1

    # --- Execution result (stored as structured object, NOT raw HTML) ---
    slug = name.lower().replace(' ', '').replace('.', '').replace('-', '').replace('(', '').replace(')', '')
    tool_suffix, tool_desc = TOOL_MAP.get(cat, ('get_profile', 'Retrieved workspace profile and metadata.'))
    mock_tool = f"{slug}_{tool_suffix}"

    js_apps.append({
        'name':      name,
        'category':  cat,
        'auth':      auth,
        'gated':     gate,
        'surface':   api,
        'blocker':   blocker,
        'evidence':  evidence,
        'verdict':   v_text,
        # Structured data — JS builds the HTML
        'isBuildable': is_buildable,
        'isGated':     is_gated,
        'mockTool':    mock_tool,
        'toolDesc':    tool_desc,
    })

top_blockers = sorted(blockers_raw.items(), key=lambda x: -x[1])[:6]

insights = {
    'auths':      auths,
    'categories': categories,
    'wins':       {'buildable': buildable_count, 'gated': gated_count, 'caveat': caveat_count},
    'top_blockers': top_blockers,
}

# Write just the data into the template placeholder
data_block = (
    "        // --- DATA INJECTION START ---\n"
    "        const apps = " + json.dumps(js_apps, indent=4, ensure_ascii=False) + ";\n"
    "        const insights = " + json.dumps(insights, indent=4, ensure_ascii=False) + ";\n"
    "        // --- DATA INJECTION END ---"
)

with open('c:/composio/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

if '// --- DATA INJECTION START ---' in html:
    html = re.sub(
        r'// --- DATA INJECTION START ---.*?// --- DATA INJECTION END ---',
        data_block, html, flags=re.DOTALL
    )
else:
    # First run – insert just before </script>
    html = html.replace('        // Initial render', data_block + '\n\n        // Initial render')

with open('c:/composio/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Injected {len(js_apps)} apps. Buildable={buildable_count}, Gated={gated_count}, Caveat={caveat_count}")
