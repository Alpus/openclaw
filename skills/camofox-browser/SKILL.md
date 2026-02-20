---
name: camofox-browser
description: Anti-detection headless browser for visiting sites that block automation (Ocado, Amazon, Cloudflare-protected). Use when the built-in browser tool gets blocked or when you need stealth browsing.
---

# Camofox Browser

Anti-detection browser server powered by [Camoufox](https://camoufox.com) — a Firefox fork with fingerprint spoofing at the C++ level. Bypasses Cloudflare, Google, Amazon, and most bot detection systems.

## When to Use

- Site blocks Playwright/Puppeteer/headless Chrome
- Need to bypass Cloudflare challenge pages
- Need session isolation (separate cookies per task)
- Built-in `browser` tool gets detected

## When NOT to Use

- **Just reading an article/page** → use `web_fetch` instead (faster, no browser overhead)
- Only use browser when you need to click, login, or interact with the page

## Prerequisites

- **Plugin**: `camofox-browser` must be enabled in OpenClaw config (plugins.entries)
- **Server**: Runs on localhost (default port 9377), auto-starts with gateway if `autoStart: true`
- **Install**: `git clone https://github.com/jo-inc/camofox-browser && cd camofox-browser && npm install`
- First run downloads Camoufox engine (~300MB)

## Plugin Tools

When the plugin is active, these tools are available:

| Tool                 | Description                                              |
| -------------------- | -------------------------------------------------------- |
| `camofox_create_tab` | Open URL in anti-detection browser                       |
| `camofox_snapshot`   | Get accessibility tree (compact, ~5-30KB vs ~500KB HTML) |
| `camofox_click`      | Click element by ref (e1, e2...)                         |
| `camofox_type`       | Type text into element                                   |
| `camofox_navigate`   | Navigate to URL or use search macro                      |
| `camofox_scroll`     | Scroll page                                              |
| `camofox_screenshot` | Take screenshot                                          |
| `camofox_close_tab`  | Close tab                                                |
| `camofox_list_tabs`  | List open tabs                                           |

## Without Plugin (curl fallback)

If plugin tools aren't available, use REST API directly:

```bash
# Create tab
curl -s -X POST http://localhost:9377/tabs \
  -H 'Content-Type: application/json' \
  -d '{"userId": "<agent-id>", "sessionKey": "<task>", "url": "https://example.com"}'

# Snapshot (accessibility tree with element refs)
curl -s --max-time 30 "http://localhost:9377/tabs/<TAB_ID>/snapshot?userId=<agent-id>"

# Click by ref
curl -s -X POST http://localhost:9377/tabs/<TAB_ID>/click \
  -H 'Content-Type: application/json' \
  -d '{"userId": "<agent-id>", "ref": "e1"}'

# Type
curl -s -X POST http://localhost:9377/tabs/<TAB_ID>/type \
  -H 'Content-Type: application/json' \
  -d '{"userId": "<agent-id>", "ref": "e2", "text": "search query", "pressEnter": true}'

# Screenshot
curl -s --max-time 30 "http://localhost:9377/tabs/<TAB_ID>/screenshot?userId=<agent-id>" -o /tmp/screenshot.png

# Navigate with search macro
curl -s -X POST http://localhost:9377/tabs/<TAB_ID>/navigate \
  -H 'Content-Type: application/json' \
  -d '{"userId": "<agent-id>", "macro": "@google_search", "query": "best coffee"}'
```

## Search Macros

`@google_search`, `@youtube_search`, `@amazon_search`, and 10+ more built-in.

## Key Behaviors

- **Cookie consent**: Auto-dismissed (🍪 in server logs)
- **Session isolation**: Each userId+sessionKey gets separate cookies/storage
- **Element refs**: Stable identifiers (e1, e2, e3...) for reliable interaction across snapshots

## ⚠️ Important: Timeouts & Navigation

### Snapshot timeouts

Heavy SPAs (Ocado, Amazon) take 3-5 seconds for snapshot. **Always use `--max-time 30`** (or equivalent timeout). Without it, curl exits before the response arrives — this looks like a server crash but isn't.

| Page type                       | Snapshot time | Snapshot size   |
| ------------------------------- | ------------- | --------------- |
| Simple (example.com)            | <1s           | ~200 bytes      |
| Medium (Google)                 | ~1s           | ~2KB            |
| Heavy SPA (Ocado homepage)      | 3-5s          | ~31KB, 150 refs |
| Specific pages (Ocado delivery) | 2-3s          | ~10KB, 73 refs  |

### Click timeouts on SPAs — NORMAL

When `camofox_click` triggers a page navigation (login submit, link click), Playwright's default 5s timeout often expires because the SPA takes longer to settle. **The click succeeded** — the page navigated. Just proceed with `camofox_snapshot` to see the new page.

Error looks like: `"locator.click: Timeout 5000ms exceeded"` followed by `"navigated to ..."` in the call log — that `"navigated to"` confirms success.

### Prefer `camofox_navigate` over click for links

When a snapshot shows a link with an `href`, use `camofox_navigate` with the URL directly instead of clicking the element. This is faster, more reliable, and avoids click timeout issues.

**Use `camofox_click`** for: buttons, form submits, dropdowns, interactive elements without URLs.
**Use `camofox_navigate`** for: links with visible `/url:` in snapshot, known page URLs.

### Modal dialogs blocking the page

If a modal appears (e.g., post-login popups), navigate directly to the target URL with `camofox_navigate` instead of trying to close the modal. The navigate will dismiss it.

### Invisible reCAPTCHA (v3)

Many sites use invisible reCAPTCHA that runs in the background (no checkbox, no image challenge). Camoufox's C++ fingerprint spoofing makes the browser look legitimate, so reCAPTCHA v3 gives a high trust score and passes silently. No special action needed — just submit the form normally.

**Warning**: reCAPTCHA may escalate to a **visible challenge** (image grid) on repeated logins or if the score drops. This is not consistent — the same site may pass silently once and show a challenge the next time.

To solve visual reCAPTCHA challenges, see the **reCAPTCHA Solving** section below.

### Coordinate click

The `/click` endpoint supports `x, y` coordinates in addition to `ref` and `selector`:

```bash
curl -X POST http://localhost:9377/tabs/TAB_ID/click \
  -H 'Content-Type: application/json' \
  -d '{"userId": "main", "x": 640, "y": 360}'
```

Coordinates match the screenshot pixel coordinates exactly (viewport = screenshot = 1280×720).

### Aim — visual coordinate verification

Before clicking, verify your target coordinates by rendering crosshairs on the screenshot:

```bash
# Single point
curl "http://localhost:9377/tabs/TAB_ID/aim?userId=main&x=640&y=360" -o aim.png

# Multiple points (comma-separated)
curl "http://localhost:9377/tabs/TAB_ID/aim?userId=main&x=640,200,800&y=360,100,500" -o aim.png
```

Returns a PNG with red crosshair markers, numbered labels, and coordinate text at each point. Use this to confirm your coordinates hit the right targets before sending actual clicks.

**When to use aim**: reCAPTCHA grids, small buttons, crowded UIs, or any time you're not 100% sure where the click will land.

## Workflow: Login + Navigate

1. Create tab → navigate to login page
2. Snapshot → find email/password fields (refs)
3. Type credentials → click submit (**expect timeout on navigation — this is OK**)
4. Snapshot to verify logged in (look for account indicators)
5. Navigate to target page via URL → snapshot/interact

**Credentials**: Always retrieve from 1Password at runtime. Never hardcode.

## Default Browser

**Use camofox as the default browser for ALL web automation.** Log in to sites directly in camofox — don't rely on Chrome cookies.

Use built-in `browser` (Chrome Relay) only as **fallback** if camofox is broken/unavailable.

Use `web_fetch` when:

- Simple static content or APIs (no JS rendering needed)

## reCAPTCHA Solving

For detailed reCAPTCHA solving guide (grid layout, recognition rules, crop workflow, tips), see `references/recaptcha.md`. Load it when a visual reCAPTCHA challenge appears.

**Quick summary**: Screenshot → crop grid → identify matching cells → aim to verify coordinates → click cells → check for replacements → click VERIFY → repeat if needed.

## Known Limitations

- **Session persistence**: Cookies persist within a camofox server session but are lost on server restart. For sites requiring login, re-authenticate after restart.
- **userId for curl fallback**: Plugin uses `userId=main` (from `ctx.agentId`). Use this in manual curl calls.
