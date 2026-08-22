# Desk Assistant

A permission-aware AI sidebar for **Frappe Desk**. Granted users ask questions about live ERP data using **their own** LLM key (OpenAI, Claude, Gemini, Groq, OpenRouter, Ollama, or any OpenAI-compatible API). The model only sees documents that user can already read in Desk.

This is a Frappe app, not an MCP server. Chat stays inside Desk. The assistant is **read-only**: it looks up data; it does not submit or cancel documents.

## What you get

- Right-hand Desk sidebar (resize, collapse, persist width)
- Site master switch plus role **AI Assistant User** (install does not enable it for everyone)
- Tools that run as `frappe.session.user`: `query`, `get_doc`, `get_meta`, `search`, `run_report`, `get_me`
- Chat sessions that survive refresh; **New** starts a fresh thread
- Audit log of tool calls for managers
- API keys stored server-side (never sent to the browser)

## Compatibility

This app is built and tested on **Frappe v16** only (Frappe 16.30, Python 3.14). It is **not** tested on Frappe 14 or 15. Desk icons, workspace sidebar, and boot hooks target v16.

Use the **`version-16`** branch on a Frappe v16 bench. Use **`develop`** for ongoing work (same code as `version-16` until a later Frappe version exists).

| Need | Detail |
|---|---|
| **Frappe** | v16 bench and site. Required. |
| **Python** | **3.14** (same as Frappe 16: `>=3.14,<3.15`) |
| **ERPNext** | **Optional.** Not in `required_apps`. Install ERPNext if you want Sales Invoice, stock, customers, and similar DocTypes. Without it, the sidebar still works on Frappe DocTypes the user can read (ToDo, etc.). |
| **Other apps** | Optional. The assistant can query any DocType the signed-in user can already read (HR, custom apps, …). |
| **Database / Redis** | Whatever that Frappe site already uses (MariaDB + Redis). No extra services. |
| **Node** | Needed for `bench build` / `bench get-app` asset build. |
| **Network** | Outbound HTTPS to the LLM provider (OpenAI, Anthropic, Google, Groq, OpenRouter). **Ollama** needs a reachable Ollama host. Keys stay on the server. |
| **Browser** | Current Desk (desktop). Mobile layout is not in this version. |

No extra Python pip packages. Provider SDKs are not bundled; the app calls the HTTP APIs.

## Requirements

- A Frappe **v16** site on a matching bench
- An API key for at least one supported provider (or a site-wide fallback key)

## Branches

Same layout as Frappe / ERPNext:

| Branch | Use |
|---|---|
| **`develop`** | Default. New work and PRs go here. |
| **`version-16`** | Stable line for **Frappe v16** sites. Install this on production v16. |

New features land on `develop`. Fixes that must ship on v16 are merged (or cherry-picked) to `version-16`. There is no `version-14` / `version-15` line.

## Install

Copy this app into your bench `apps` folder, or run `bench get-app` from your own git remote. Pin the branch to your Frappe version:

```bash
cd /path/to/frappe-bench

# Frappe v16 site
bench get-app <your-remote> --branch version-16
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
3. Answers include Desk links when the lookup succeeds
4. **New** starts a new chat session; refresh restores the open thread

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
