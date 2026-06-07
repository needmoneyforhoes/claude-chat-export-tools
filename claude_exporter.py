#!/usr/bin/env python3
"""
Claude.ai Chat Exporter
========================
Export your Claude conversations to readable Markdown files.

Setup:
  1. Go to claude.ai in Chrome
  2. Open DevTools (F12) → Application tab → Cookies → claude.ai
  3. Copy the 'sessionKey' cookie value
  4. That's it — org ID is auto-detected

Usage:
  python claude_exporter.py --list                     # List all conversations
  python claude_exporter.py --id CONV_ID               # Export one conversation
  python claude_exporter.py --url "https://claude.ai/chat/abc123"  # Export from URL
  python claude_exporter.py --all                      # Export all conversations
  python claude_exporter.py --all --limit 10           # Export last 10 conversations
  python claude_exporter.py --id CONV_ID --format txt  # Export as plain text
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    print("Missing curl_cffi. Install with: pip install curl_cffi")
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────────
SESSION_KEY = os.getenv("CLAUDE_SESSION_KEY", "")

BASE_URL = "https://claude.ai/api"
OUTPUT_DIR = "claude_exports"

# ── API Client (curl_cffi to bypass Cloudflare) ──────────────────────────────

class ClaudeExporter:
    def __init__(self, session_key: str):
        self.session_key = session_key
        self.org_id = None
        self._cookies = {"sessionKey": session_key}
        self._detect_org_id()

    def _get(self, path: str, params: dict = None) -> dict | list | None:
        url = f"{BASE_URL}/organizations/{self.org_id}/{path}"
        try:
            r = cffi_requests.get(
                url, params=params,
                cookies=self._cookies,
                impersonate="chrome",
                timeout=30,
            )
            if r.status_code == 403:
                print(f"ERROR: 403 Forbidden for {path}")
                return None
            if r.status_code == 404:
                print(f"ERROR: 404 Not Found for {path}")
                return None
            if r.status_code != 200:
                print(f"ERROR: HTTP {r.status_code} for {path}")
                return None
            return r.json()
        except Exception as e:
            print(f"ERROR: Request failed for {path}: {e}")
            return None

    def _detect_org_id(self):
        """Auto-detect org ID from session."""
        try:
            r = cffi_requests.get(
                f"{BASE_URL}/organizations",
                cookies=self._cookies,
                impersonate="chrome",
                timeout=15,
            )
        except Exception as e:
            print(f"ERROR: Could not connect to Claude.ai: {e}")
            sys.exit(1)

        if r.status_code == 403:
            print("ERROR: 403 Forbidden — your session key is invalid or expired.")
            print("       Go to claude.ai → DevTools → Application → Cookies → copy sessionKey")
            sys.exit(1)

        if r.status_code != 200:
            print(f"ERROR: HTTP {r.status_code} from Claude.ai")
            print(f"       Response: {r.text[:300]}")
            sys.exit(1)

        try:
            orgs = r.json()
        except Exception:
            print(f"ERROR: Invalid JSON from Claude.ai")
            print(f"       Response: {r.text[:300]}")
            sys.exit(1)

        if isinstance(orgs, list) and orgs:
            self.org_id = orgs[0].get("uuid", orgs[0].get("id"))
            print(f"  Org: {orgs[0].get('name', self.org_id)}")
        elif isinstance(orgs, dict):
            org_list = orgs.get("data", orgs.get("organizations", []))
            if org_list:
                self.org_id = org_list[0].get("uuid", org_list[0].get("id"))
                print(f"  Org: {org_list[0].get('name', self.org_id)}")

        if not self.org_id:
            print("ERROR: Could not detect organization ID.")
            print(f"       Response: {str(orgs)[:300]}")
            sys.exit(1)

    def list_conversations(self, limit: int = 50) -> list:
        """Fetch list of recent conversations."""
        result = self._get("chat_conversations", params={"limit": limit})
        if not result:
            return []
        return result if isinstance(result, list) else result.get("data", result.get("conversations", []))

    def get_conversation(self, conv_id: str) -> dict | None:
        """Fetch a single conversation with all messages."""
        return self._get(f"chat_conversations/{conv_id}")

    def get_full_conversation(self, conv_id: str) -> dict | None:
        """Fetch conversation with full message content."""
        # Try the detailed endpoint first
        result = self._get(f"chat_conversations/{conv_id}?tree=True&rendering_mode=messages")
        if result:
            return result
        # Fallback to basic endpoint
        return self.get_conversation(conv_id)


# ── Formatters ─────────────────────────────────────────────────────────────────

def _extract_text(content, include_thinking: bool = False) -> str:
    """Extract readable text from message content (handles various formats)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                btype = block.get("type", "")
                if btype == "text":
                    txt = block.get("text", "")
                    # Detect artifact placeholder
                    if "This block is not supported on your current device yet" in txt:
                        parts.append("\n🎨 *[Artifact/Widget — content not available via API]*\n")
                    elif txt.strip():
                        parts.append(txt)
                elif btype == "thinking" and include_thinking:
                    thinking = block.get("thinking", "")
                    if thinking.strip():
                        parts.append(f"\n**💭 Thinking:**\n> {thinking.strip()}\n")
                elif btype == "tool_use":
                    name = block.get("name", "tool")
                    inp = block.get("input", {})
                    parts.append(f"\n**Tool Use: {name}**\n```json\n{json.dumps(inp, indent=2)}\n```\n")
                elif btype == "tool_result":
                    content_inner = block.get("content", "")
                    parts.append(f"\n**Tool Result:**\n{_extract_text(content_inner)}\n")
                elif btype == "image":
                    parts.append("[Image]")
                elif btype == "document":
                    parts.append("[Document]")
                elif btype != "thinking":  # skip thinking when not included
                    text = block.get("text", block.get("content", ""))
                    if text:
                        parts.append(_extract_text(text))
        return "\n".join(parts)
    if isinstance(content, dict):
        return content.get("text", content.get("content", str(content)))
    return str(content)


def _format_timestamp(ts) -> str:
    """Format a timestamp string or unix timestamp."""
    if not ts:
        return ""
    try:
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts)
        else:
            # Try ISO format
            ts_clean = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_clean)
        return dt.strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return str(ts)


def _safe_filename(name: str, max_len: int = 80) -> str:
    """Create a filesystem-safe filename from a conversation title."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    safe = safe.strip('. ')
    if len(safe) > max_len:
        safe = safe[:max_len].rstrip('. ')
    return safe or "untitled"


def format_markdown(conversation: dict, no_attachments: bool = False,
                    include_thinking: bool = False) -> str:
    """Format a conversation as readable Markdown."""
    lines = []
    title = conversation.get("name", conversation.get("title", "Untitled"))
    created = _format_timestamp(conversation.get("created_at"))
    updated = _format_timestamp(conversation.get("updated_at"))
    model = conversation.get("model", conversation.get("settings", {}).get("model", ""))

    lines.append(f"# {title}")
    lines.append("")
    if created:
        lines.append(f"**Created:** {created}")
    if updated:
        lines.append(f"**Updated:** {updated}")
    if model:
        lines.append(f"**Model:** {model}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Extract messages
    messages = conversation.get("chat_messages", [])
    if not messages:
        messages = conversation.get("messages", [])

    for msg in messages:
        sender = msg.get("sender", msg.get("role", "unknown"))
        ts = _format_timestamp(msg.get("created_at", msg.get("timestamp", "")))

        if sender in ("human", "user"):
            header = f"## Human"
            if ts:
                header += f" ({ts})"
        elif sender in ("assistant", "claude"):
            header = f"## Claude"
            if ts:
                header += f" ({ts})"
        else:
            header = f"## {sender.title()}"
            if ts:
                header += f" ({ts})"

        lines.append(header)
        lines.append("")

        # Handle content and attachments
        content = msg.get("content", msg.get("text", ""))
        text = _extract_text(content, include_thinking=include_thinking)

        # Check for attachments/files
        attachments = msg.get("attachments", msg.get("files", []))
        has_attachments = False
        if attachments:
            for att_idx, att in enumerate(attachments):
                if isinstance(att, dict):
                    has_attachments = True
                    fname = (att.get("file_name") or att.get("name")
                             or f"attachment_{att_idx + 1}.{att.get('file_type', 'txt')}")
                    ftype = att.get("file_type", att.get("type", ""))
                    lines.append(f"📎 **Attachment:** {fname}" +
                                 (f" ({ftype})" if ftype else ""))
                    # Include extracted content if available
                    if not no_attachments:
                        att_content = (att.get("extracted_content")
                                       or att.get("content")
                                       or att.get("text")
                                       or "")
                        if att_content:
                            lines.append("")
                            lines.append(f"**{fname} content:**")
                            lines.append("```")
                            lines.append(att_content.strip())
                            lines.append("```")
                    lines.append("")

        if text.strip():
            lines.append(text.strip())
        elif not has_attachments:
            lines.append("*(empty message)*")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def format_text(conversation: dict, no_attachments: bool = False,
                include_thinking: bool = False) -> str:
    """Format a conversation as plain text."""
    lines = []
    title = conversation.get("name", conversation.get("title", "Untitled"))
    created = _format_timestamp(conversation.get("created_at"))

    lines.append(f"{'='*80}")
    lines.append(f"  {title}")
    if created:
        lines.append(f"  {created}")
    lines.append(f"{'='*80}")
    lines.append("")

    messages = conversation.get("chat_messages", [])
    if not messages:
        messages = conversation.get("messages", [])

    for msg in messages:
        sender = msg.get("sender", msg.get("role", "unknown"))
        ts = _format_timestamp(msg.get("created_at", msg.get("timestamp", "")))

        if sender in ("human", "user"):
            label = "HUMAN"
        elif sender in ("assistant", "claude"):
            label = "CLAUDE"
        else:
            label = sender.upper()

        header = f"[{label}]"
        if ts:
            header += f"  {ts}"

        lines.append(header)
        lines.append("-" * 40)

        content = msg.get("content", msg.get("text", ""))
        text = _extract_text(content, include_thinking=include_thinking)

        # Attachments
        attachments = msg.get("attachments", msg.get("files", []))
        has_attachments = False
        if attachments:
            for att_idx, att in enumerate(attachments):
                if isinstance(att, dict):
                    has_attachments = True
                    fname = (att.get("file_name") or att.get("name")
                             or f"attachment_{att_idx + 1}.{att.get('file_type', 'txt')}")
                    lines.append(f"[Attachment: {fname}]")

        if text.strip():
            lines.append(text.strip())
        elif not has_attachments:
            lines.append("(empty message)")
        lines.append("")

    return "\n".join(lines)


def format_json(conversation: dict, no_attachments: bool = False,
                include_thinking: bool = False) -> str:
    """Format as pretty-printed JSON."""
    return json.dumps(conversation, indent=2, ensure_ascii=False, default=str)


# ── Export Logic ───────────────────────────────────────────────────────────────

FORMATTERS = {
    "md": (format_markdown, ".md"),
    "txt": (format_text, ".txt"),
    "json": (format_json, ".json"),
}


def _split_content(content: str, max_chars: int, fmt: str) -> list[str]:
    """Split content into chunks at message boundaries, each under max_chars."""
    if len(content) <= max_chars:
        return [content]

    # Split at message boundaries
    if fmt == "md":
        separator = "\n---\n"
    else:
        separator = "\n[HUMAN]"  # txt format

    # For markdown, split on --- dividers
    if fmt == "md":
        sections = content.split(separator)
    else:
        # For txt, split on message headers but keep the header with its content
        parts = content.split(separator)
        sections = [parts[0]]
        for p in parts[1:]:
            sections.append("[HUMAN]" + p)

    chunks = []
    current = ""

    for section in sections:
        piece = section + (separator if fmt == "md" else "")
        # If adding this section would exceed limit, start new chunk
        if current and len(current) + len(piece) > max_chars:
            chunks.append(current.rstrip())
            current = piece
        else:
            current += piece

    if current.strip():
        chunks.append(current.rstrip())

    return chunks if chunks else [content]


def export_conversation(exporter: ClaudeExporter, conv_id: str,
                        fmt: str = "md", output_dir: str = OUTPUT_DIR,
                        no_attachments: bool = False,
                        include_thinking: bool = False,
                        split_chars: int = 0) -> str | None:
    """Export a single conversation to file. Returns the output filepath."""
    print(f"  Fetching conversation {conv_id}...")
    conv = exporter.get_full_conversation(conv_id)
    if not conv:
        print(f"  ERROR: Could not fetch conversation {conv_id}")
        return None

    title = conv.get("name", conv.get("title", "untitled"))
    formatter, ext = FORMATTERS.get(fmt, FORMATTERS["md"])
    content = formatter(conv, no_attachments=no_attachments,
                        include_thinking=include_thinking)

    os.makedirs(output_dir, exist_ok=True)
    safe_name = _safe_filename(title)
    short_id = conv_id[:8] if len(conv_id) > 8 else conv_id

    # Split if requested and content exceeds limit
    if split_chars > 0 and len(content) > split_chars:
        chunks = _split_content(content, split_chars, fmt)
        filepaths = []
        for i, chunk in enumerate(chunks, 1):
            filename = f"{safe_name}_{short_id}_part{i}{ext}"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(chunk)
            filepaths.append(filepath)
        msg_count = len(conv.get("chat_messages", conv.get("messages", [])))
        print(f"  ✅ Split into {len(chunks)} files ({msg_count} messages, {len(content)} chars)")
        for fp in filepaths:
            print(f"     → {fp}")
        return filepaths[0]
    else:
        filename = f"{safe_name}_{short_id}{ext}"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        msg_count = len(conv.get("chat_messages", conv.get("messages", [])))
        print(f"  ✅ Saved: {filepath} ({msg_count} messages, {len(content)} chars)")
        return filepath


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Export Claude.ai conversations to Markdown, Text, or JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python claude_exporter.py --list
  python claude_exporter.py --id abc123-def456
  python claude_exporter.py --all --limit 5
  python claude_exporter.py --all --format txt
  python claude_exporter.py --id abc123 --format json --output my_exports

Environment variables:
  CLAUDE_SESSION_KEY   Your sessionKey cookie value
        """
    )
    parser.add_argument("--session-key", default=SESSION_KEY,
                        help="Session key (or set CLAUDE_SESSION_KEY env var)")
    parser.add_argument("--org-id", default=None,
                        help="Organization ID (auto-detected, only needed as override)")
    parser.add_argument("--list", action="store_true",
                        help="List recent conversations")
    parser.add_argument("--id", type=str, default=None,
                        help="Export a specific conversation by ID")
    parser.add_argument("--url", type=str, default=None,
                        help="Export from a claude.ai chat URL")
    parser.add_argument("--all", action="store_true",
                        help="Export all conversations")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max conversations to list/export (default: 50)")
    parser.add_argument("--format", choices=["md", "txt", "json"], default="md",
                        help="Output format (default: md)")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR,
                        help=f"Output directory (default: {OUTPUT_DIR})")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay between API calls in seconds (default: 1.0)")
    parser.add_argument("--no-attachments", action="store_true",
                        help="Skip attachment content (just show filenames)")
    parser.add_argument("--thinking", action="store_true",
                        help="Include Claude's thinking blocks in export")
    parser.add_argument("--split", type=int, nargs="?", const=14000, default=0,
                        help="Split into multiple files (default: 14000 chars per file, safe for Claude reading)")

    args = parser.parse_args()

    # Validate credentials
    session_key = args.session_key

    if not session_key:
        print("ERROR: No session key provided.")
        print("  Set CLAUDE_SESSION_KEY env var or use --session-key")
        print("  Find it in Chrome DevTools → Application → Cookies → claude.ai → sessionKey")
        sys.exit(1)

    # Extract conv ID from URL if provided
    conv_id = args.id
    if args.url:
        # https://claude.ai/chat/abc123-def456
        match = re.search(r'/chat/([a-f0-9-]+)', args.url)
        if match:
            conv_id = match.group(1)
        else:
            print(f"ERROR: Could not extract conversation ID from URL: {args.url}")
            sys.exit(1)

    print("\nConnecting to claude.ai...")
    exporter = ClaudeExporter(session_key)

    # Override org ID if provided manually
    if args.org_id:
        exporter.org_id = args.org_id
        print(f"  Using manual org ID: {args.org_id}")

    # ── List mode ──────────────────────────────────────────────────────────
    if args.list:
        print(f"\nFetching conversations (limit={args.limit})...\n")
        convos = exporter.list_conversations(limit=args.limit)
        if not convos:
            print("No conversations found (check credentials).")
            return

        print(f"{'#':<4} {'Title':<55} {'Created':<20} {'ID'}")
        print(f"{'─'*4} {'─'*55} {'─'*20} {'─'*36}")
        for i, c in enumerate(convos, 1):
            title = c.get("name", c.get("title", "Untitled"))
            if len(title) > 52:
                title = title[:52] + "..."
            created = _format_timestamp(c.get("created_at", ""))
            cid = c.get("uuid", c.get("id", "?"))
            print(f"{i:<4} {title:<55} {created:<20} {cid}")

        print(f"\n  Total: {len(convos)} conversations")
        print(f"  Export one:  python claude_exporter.py --id <ID>")
        print(f"  Export all:  python claude_exporter.py --all")
        return

    # ── Single export ──────────────────────────────────────────────────────
    if conv_id:
        print(f"\nExporting conversation: {conv_id}")
        print(f"  Format: {args.format} | Output: {args.output}\n")
        result = export_conversation(exporter, conv_id, args.format, args.output,
                                     no_attachments=args.no_attachments,
                                     include_thinking=args.thinking,
                                     split_chars=args.split)
        if result:
            print(f"\nDone!")
        return

    # ── Export all ─────────────────────────────────────────────────────────
    if args.all:
        print(f"\nFetching conversation list (limit={args.limit})...")
        convos = exporter.list_conversations(limit=args.limit)
        if not convos:
            print("No conversations found.")
            return

        print(f"  Found {len(convos)} conversations")
        print(f"  Format: {args.format} | Output: {args.output}")
        print(f"  Delay: {args.delay}s between requests\n")

        exported = 0
        failed = 0
        for i, c in enumerate(convos, 1):
            cid = c.get("uuid", c.get("id"))
            title = c.get("name", c.get("title", "Untitled"))
            if len(title) > 50:
                title = title[:50] + "..."
            print(f"[{i}/{len(convos)}] {title}")

            if not cid:
                print("  SKIP: no conversation ID")
                failed += 1
                continue

            result = export_conversation(exporter, cid, args.format, args.output,
                                         no_attachments=args.no_attachments,
                                         include_thinking=args.thinking,
                                         split_chars=args.split)
            if result:
                exported += 1
            else:
                failed += 1

            if i < len(convos):
                time.sleep(args.delay)

        print(f"\nDone! Exported: {exported} | Failed: {failed}")
        print(f"Files saved to: {args.output}/")
        return

    # No action specified
    parser.print_help()


if __name__ == "__main__":
    main()
