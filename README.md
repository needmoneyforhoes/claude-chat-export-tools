# claude-chat-export-tools

CLI that exports Claude.ai conversations to Markdown, plain text, or JSON.

Split out of the Polymarket quant suite to archive strategy-research chat threads. Unrelated to trading; handles no funds. Claude.ai sits behind Cloudflare, so requests use `curl_cffi` browser impersonation instead of `requests`.

## Scripts

- `claude_exporter.py`: Main CLI. Auto-detects org ID from the session, lists conversations, exports one or all to Markdown/txt/JSON. Supports thinking-block inclusion, attachment extraction, and splitting long threads (default 14000 chars/chunk).
- `debug_claude_api.py`: Connectivity probe. Hits `claude.ai/api/organizations` three ways (Chrome impersonate, Chrome plus extra headers, Firefox impersonate) to diagnose 403s and Cloudflare blocks before running the exporter.

## Requirements

- Python 3.10+ (uses `dict | list | None` union syntax)
- `pip install curl_cffi` (only third-party dependency; rest is stdlib)
- A Claude.ai session key in `CLAUDE_SESSION_KEY`. Get it from claude.ai, DevTools (F12), Application, Cookies, `sessionKey`.

## Usage

```bash
export CLAUDE_SESSION_KEY="sk-ant-sid01-..."   # from claude.ai cookies

python debug_claude_api.py                      # check access first
python claude_exporter.py --list                # list conversations
python claude_exporter.py --id CONV_ID          # export one by ID
python claude_exporter.py --url "https://claude.ai/chat/abc123"
python claude_exporter.py --all                 # export all (Markdown)
python claude_exporter.py --all --limit 10 --format txt
python claude_exporter.py --id CONV_ID --format json --output my_exports --thinking
python claude_exporter.py --all --split 14000   # split long threads
```

`--session-key` passes the key inline; `--org-id` overrides auto-detection. Exports go to `./claude_exports/` by default (`--output` to change). Generated `*.json`/`*.md` artifacts are gitignored.

Session key is a web-session token, not a wallet key; never commit it. `.env`, `.env.*`, and `*.key` are gitignored.
