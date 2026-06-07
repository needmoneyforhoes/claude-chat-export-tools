# claude-chat-export-tools

Personal utilities to export Claude.ai conversations to Markdown and debug API access. Credentials are supplied via environment, never committed.

These are developer/research utilities split out of the Polymarket quant suite — used to archive the long strategy-research chat threads behind that work. They are unrelated to trading and handle no funds.

## Why it exists

Claude.ai has no bulk export. This pulls your conversations straight from the private `claude.ai/api`, rendering each thread to readable Markdown (or txt/json) so research history can be archived and grepped offline. Claude.ai sits behind Cloudflare, so requests use `curl_cffi` browser impersonation rather than plain `requests`.

## What's inside

| File | Purpose |
| --- | --- |
| `claude_exporter.py` | Main CLI. Auto-detects your org ID from the session, lists conversations, and exports one / all of them to Markdown, plain text, or JSON. Supports thinking-block inclusion, attachment handling, and splitting very long threads. |
| `debug_claude_api.py` | Connectivity probe. Hits `claude.ai/api/organizations` three ways (Chrome impersonation, Chrome + extra headers, Firefox) to diagnose 403s / Cloudflare blocks before running the exporter. |

## Requirements

- Python 3.10+ (uses `dict | list | None` union syntax)
- `pip install curl_cffi` (the only third-party dependency; everything else is stdlib)
- A valid **Claude.ai session key**, supplied via the `CLAUDE_SESSION_KEY` environment variable. Get it from claude.ai → DevTools (F12) → Application → Cookies → `sessionKey`. It is **never** committed; `.env`, `.env.*`, and `*.key` are gitignored.

This is a web-session token, not a wallet key — these tools touch no on-chain funds, ClobClient, or trading data.

## Usage

```bash
export CLAUDE_SESSION_KEY="sk-ant-sid01-..."   # from claude.ai cookies

# Sanity-check access first
python debug_claude_api.py

# List all conversations
python claude_exporter.py --list

# Export one conversation (by ID or URL)
python claude_exporter.py --id CONV_ID
python claude_exporter.py --url "https://claude.ai/chat/abc123"

# Export everything (Markdown by default) into ./claude_exports/
python claude_exporter.py --all

# Variations
python claude_exporter.py --all --limit 10 --format txt
python claude_exporter.py --id CONV_ID --format json --output my_exports --thinking
python claude_exporter.py --all --split 14000        # split long threads into chunks
```

The session key can also be passed inline with `--session-key`; `--org-id` overrides auto-detection. Exports are written to `./claude_exports/` by default (`--output` to change). Generated `*.json`/`*.md` artifacts are gitignored.

> Private research software. No warranty; use at your own risk.
