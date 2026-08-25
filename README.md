# Desk Assistant

A permission-aware AI sidebar for **Frappe Desk**. Granted users ask questions about live ERP data using **their own** LLM key (OpenAI, Claude, Gemini, Groq, OpenRouter, Ollama, or any OpenAI-compatible API). The model only sees documents that user can already read in Desk.

This is a Frappe app, not an MCP server. Chat stays inside Desk. The assistant is **read-only**: it looks up data; it does not submit or cancel documents.

## What you get

- Right-hand Desk sidebar (resize, collapse, persist width)
- Site master switch plus role **AI Assistant User** (install does not enable it for everyone)
- Tools that run as `frappe.session.user`: `query`, `get_doc`, `get_meta`, `search`, `run_report`, `get_me`
- Streaming replies with **Stop**; **Copy** on finished assistant messages
- Chat sessions that survive refresh; **New** starts a fresh thread
- Audit log of tool calls for managers
- API keys stored server-side (never sent to the browser)

## Features (MVP)

Replies stay **short prose** unless you ask for more. The assistant does not invent totals; charts and tables use numbers from tools.

| Feature | What it does |
|---|---|
| **Streaming** | Tokens appear as they arrive. **Stop** cancels the in-flight request. |
| **Tables (opt-in)** | A markdown table only if you ask for a table, list, ranking, or breakdown — or several rows must be compared. “Which customer has the largest overdue?” is a sentence plus a document link, not a ranking table. |
| **Charts (opt-in)** | Bar, line, pie, or donut when you ask for a chart (or a short comparison needs one). Drawn with Desk `frappe.Chart`. A ranking without the word “chart” stays a table. |
| **Desk links** | Invoice and other document IDs are clickable. A click opens the form in the **main pane**; the sidebar stays. Ctrl/Cmd-click opens a new tab. |
| **Copy** | Finished assistant replies have **Copy** (raw markdown, including any chart fence). |
| **Language** | The model matches the language you type. Say **speak in Marathi** (or Hindi, Tamil, Japanese, …) to lock that language for the rest of the chat; **speak in English** to switch back. Document names, Desk URLs, field names, numbers, and chart JSON stay untranslated. |
| **Context chip** | On a form, the open document is optional context. You can still ask about other records you can read. |

### Example asks

- `top 5 sales invoices of year 2023` → ranking table + Desk links
- `top 6 sales invoices bar chart` → bar chart, no table unless you also asked for one
- `which customer has the largest overdue receivable?` → one sentence + invoice link
- `who is Accounts Manager` → User / Has Role lookup if this session can read those DocTypes
- `P&L for fiscal year 2023-2024` → Profit and Loss report (dates/FY mapped for the model)
- `speak in marathi` then any later question in that thread → replies in Marathi until you say `speak in english`

## Compatibility

Pick the branch that matches the Frappe version on the site. Do not install `develop` / `version-16` on a Frappe 15 bench, or `version-15` on a Frappe 16 bench.

| Need | `develop` / `version-16` | `version-15` |
|---|---|---|
| **Frappe** | v16 (tested on 16.30) | v15 |
| **Desk URLs** | `/desk/...` | `/app/...` |
| **Python** | `>=3.14,<3.15` | `>=3.10,<3.15` |

**ERPNext** is optional (not in `required_apps`) on every branch. Install it for Sales Invoice, stock, customers, and reports such as Profit and Loss. Without it, the sidebar still works on Frappe DocTypes the user can read (ToDo, User, …). Other apps are the same: the assistant can query any DocType the signed-in user can already read.

**Database / Redis:** whatever that Frappe site already uses. No extra pip packages; provider SDKs are not bundled. **Node** is needed for `bench build` / `bench get-app`. **Network:** outbound HTTPS to the LLM provider (Ollama needs a reachable host). Keys stay on the server. **Browser:** current Desk (desktop). Mobile layout is not in this version.

## Requirements

- A Frappe site on a matching bench (v16 → `develop` / `version-16`; v15 → `version-15`)
- An API key for at least one supported provider (or a site-wide fallback key)

## Branches

Same layout as Frappe / ERPNext:

| Branch | Use |
|---|---|
| **`develop`** | Default. New work and PRs go here. Frappe **v16**. |
| **`version-16`** | Stable line for **Frappe v16** sites. Same product as `develop` until a later Frappe line exists. |
| **`version-15`** | Same product for **Frappe v15** sites (`/app` Desk routes, Python 3.10+). No v16 Workspace Sidebar / Desktop Icon JSON. |

New features land on `develop`, then merge or cherry-pick to `version-16` and `version-15` without overwriting that branch’s Desk path or Python range. There is no `version-14` line.

## Install

Copy this app into your bench `apps` folder, or run `bench get-app` from your own git remote. Pin the branch to your Frappe version:

```bash
cd /path/to/frappe-bench

# Frappe v16 site
bench get-app <your-remote> --branch version-16
bench --site your.site install-app desk_assistant
```

```bash
# Frappe v15 site
bench get-app <your-remote> --branch version-15
bench --site your.site install-app desk_assistant
```

```bash
# Ongoing development (Frappe v16 today)
bench get-app <your-remote> --branch develop
bench --site your.site install-app desk_assistant
```

If the app is already on disk as `apps/desk_assistant`:

```bash
bench --site your.site install-app desk_assistant
```

If you fetched it with `bench get-app <your-remote>`, that command also **builds assets**. `install-app` only attaches the app to the site (DocTypes, roles). It does not build again.

If you copied the folder in by hand (no `get-app`):

```bash
bench --site your.site install-app desk_assistant
bench build --app desk_assistant
```

After a later `git pull` that changes JS or CSS, run `bench build --app desk_assistant` again.

Restart processes if the sidebar does not load (`bench restart`, or reload `bench start`). Then hard-refresh Desk.

## Enable and grant access

Installing the app does **not** show the sidebar. A System Manager or **AI Assistant Manager** must turn it on.

1. Desk → **AI Assistant Settings**
2. Check **Enabled**
3. Optional: set a **site default** provider, API key, **Fetch Models**, then model (used only when the user has no key of their own)
4. Optional: leave **Allowed DocTypes** empty (recommended) so any readable DocType works, minus a hard blocklist. Fill it only if you want a sandbox.
5. Open the **User** form for each person who should chat → add role **AI Assistant User**
6. That user logs out and back in, or hard-refreshes Desk

| Role | Purpose |
|---|---|
| **AI Assistant User** | Sees the sidebar and can chat |
| **AI Assistant Manager** | Settings, workspace, audit log |
| **System Manager** | Same as Manager for Settings |

Do not assign **AI Assistant User** to everyone by default.

## User configuration (BYOK)

Each granted user opens the gear in the sidebar (or **User AI Settings**) and sets:

| Field | Notes |
|---|---|
| Provider | `openai`, `anthropic`, `google`, `groq`, `openrouter`, `ollama`, `openai_compatible` |
| API key | Stored as a Password field on the server |
| **Fetch Models** | After the API key, before Model. Sidebar button and form Button field (not a header action). Uses the key on this screen, then fills the Model list. |
| Model | Pick from the fetched list, or type e.g. `gpt-4o-mini`, `claude-sonnet-4-5`, `gemini-2.0-flash` |
| Base URL | After Model. Required for Ollama / OpenAI-compatible; optional override for others |

**Test** and **Save** stay at the bottom of the sidebar (on the form, Test is a header button). You can keep more than one provider as **User AI Model Profile** rows and switch the active one. Site defaults on **AI Assistant Settings** use the same field order.

If the user has no key, the site default on **AI Assistant Settings** is used.

## Using the sidebar

1. Open any Desk page (Home is enough)
2. Type a question, for example: `top 5 sales invoices of year 2023`
3. Answers include Desk links when the lookup succeeds — click a link to open the form beside the sidebar
4. **New** starts a new chat session; refresh restores the open thread (scroll stays on the latest message)

The open document is optional context, not a limit. The assistant queries whatever that user is allowed to read.

The user still needs normal Frappe permissions for those DocTypes (for example **Accounts User** for Sales Invoice, or **System Manager** to list users). The assistant does not bypass roles.

Financial questions (P&L, Trial Balance, General Ledger) go through `run_report`. The server maps common aliases (`from_date` / `to_date`, a fiscal year name such as `2023-2024`) onto the report’s real filters so the model does not have to guess Frappe field names.

## Tests

```bash
bench --site your.site run-tests --app desk_assistant
```

## Security (short)

- Tools use `frappe.session.user`. No raw SQL, no `ignore_permissions`
- **User** and **Has Role** follow Desk permissions (a manager can list who holds a role; a user without User read cannot). Passwords and API keys are always stripped from tool output
- Still blocked: DocPerm, User Permission, Password*, System Settings, Error Log, Email Account, OAuth, this app’s own settings DocTypes
- Password / `api_key` / `api_secret` fields are stripped from `get_doc` and rejected on `query`
- Report permission errors stay in the chat; they must not pop Desk modals
- Keys never appear in boot info or the browser

## License

MIT. See [LICENSE](LICENSE).
