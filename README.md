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
- `speak in marathi` then any later question in that thread → replies in Marathi until you say `speak in english`

## Compatibility

This **`version-15`** branch targets **Frappe v15** only. Desk lives at `/app` (not `/desk`). Do not install this branch on a Frappe 16 bench — use **`version-16`** or **`develop`** there.

| Need | Detail |
|---|---|
| **Frappe** | **v15** bench and site. Required. |
| **Python** | **3.10–3.14** (same as Frappe 15: `>=3.10,<3.15`). No extra pip packages. |
| **ERPNext** | **Optional.** Not in `required_apps`. Install ERPNext if you want Sales Invoice, stock, customers, and similar DocTypes. Without it, the sidebar still works on Frappe DocTypes the user can read (ToDo, etc.). |
| **Other apps** | Optional. The assistant can query any DocType the signed-in user can already read (HR, custom apps, …). |
| **Database / Redis** | Whatever that Frappe site already uses (MariaDB + Redis). No extra services. |
| **Node** | Needed for `bench build` / `bench get-app` asset build (Frappe 15 uses Node 18/20). |
| **Network** | Outbound HTTPS to the LLM provider (OpenAI, Anthropic, Google, Groq, OpenRouter). **Ollama** needs a reachable Ollama host. Keys stay on the server. |
| **Browser** | Current Desk (desktop). Mobile layout is not in this version. |

No extra Python pip packages. Provider SDKs are not bundled; the app calls the HTTP APIs (`requests` already comes with Frappe).

## Requirements

- A Frappe **v15** site on a matching bench (Python 3.10+)
- An API key for at least one supported provider (or a site-wide fallback key)

## Branches

Same layout as Frappe / ERPNext:

| Branch | Use |
|---|---|
| **`version-15`** | This line. Install on **Frappe v15** sites. |
| **`develop`** | Frappe **v16** work. Do not mix with this branch on the same bench. |
| **`version-16`** | Stable line for **Frappe v16** sites. |

New v15-only fixes land here. Features first land on `develop` (v16) and are ported here when they should ship on v15.

## Install

Copy this app into your bench `apps` folder, or run `bench get-app` from your own git remote. Pin the branch to your Frappe version:

```bash
cd /path/to/frappe-bench

# Frappe v16 site
bench get-app <your-remote> --branch version-16
bench --site your.site install-app desk_assistant
```

```bash
# Frappe v15 site (this branch)
bench get-app <your-remote> --branch version-15
bench --site your.site install-app desk_assistant
```

```bash
# Ongoing development (Frappe v16)
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
3. Optional: set a **site default** provider, model, and API key (used only when the user has no key of their own)
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
| Model | e.g. `gpt-4o-mini`, `claude-sonnet-4-5`, `gemini-2.0-flash` |
| API key | Stored as a Password field on the server |
| Base URL | Required for Ollama / OpenAI-compatible; optional override for others |

Save, then **Test connection**. You can keep more than one provider as **User AI Model Profile** rows and switch the active one.

If the user has no key, the site default on **AI Assistant Settings** is used.

## Using the sidebar

1. Open any Desk page (Home is enough)
2. Type a question, for example: `top 5 sales invoices of year 2023`
3. Answers include Desk links when the lookup succeeds — click a link to open the form beside the sidebar
4. **New** starts a new chat session; refresh restores the open thread (scroll stays on the latest message)

The open document is optional context, not a limit. The assistant queries whatever that user is allowed to read.

The user still needs normal Frappe permissions for those DocTypes (for example **Accounts User** for Sales Invoice). The assistant does not bypass roles.

## Tests

```bash
bench --site your.site run-tests --app desk_assistant
```

## Security (short)

- Tools use `frappe.session.user`. No raw SQL, no `ignore_permissions`
- Hard blocklist includes User, passwords, OAuth, and this app’s own settings DocTypes
- Password fields are stripped from `get_doc`
- Report permission errors stay in the chat; they must not pop Desk modals
- Keys never appear in boot info or the browser

## License

MIT. See [LICENSE](LICENSE).
