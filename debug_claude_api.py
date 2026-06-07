#!/usr/bin/env python3
"""Debug script — test claude.ai API access with curl_cffi (Cloudflare bypass)."""

import os
SESSION_KEY = os.environ.get("CLAUDE_SESSION_KEY", "")  # paste your session key here

try:
    from curl_cffi import requests
except ImportError:
    print("Missing curl_cffi. Install with: pip install curl_cffi")
    exit(1)

url = "https://claude.ai/api/organizations"

print("=== Test 1: curl_cffi impersonating Chrome ===")
try:
    r = requests.get(
        url,
        cookies={"sessionKey": SESSION_KEY},
        impersonate="chrome",
        timeout=15,
    )
    print(f"  Status: {r.status_code}")
    print(f"  Body: {r.text[:500]}")
except Exception as e:
    print(f"  Exception: {e}")

print("\n\n=== Test 2: curl_cffi with extra headers ===")
try:
    r = requests.get(
        url,
        cookies={"sessionKey": SESSION_KEY},
        headers={
            "Accept": "application/json",
            "Origin": "https://claude.ai",
            "Referer": "https://claude.ai/",
        },
        impersonate="chrome",
        timeout=15,
    )
    print(f"  Status: {r.status_code}")
    print(f"  Body: {r.text[:500]}")
except Exception as e:
    print(f"  Exception: {e}")

print("\n\n=== Test 3: curl_cffi impersonating Firefox ===")
try:
    r = requests.get(
        url,
        cookies={"sessionKey": SESSION_KEY},
        impersonate="firefox",
        timeout=15,
    )
    print(f"  Status: {r.status_code}")
    print(f"  Body: {r.text[:500]}")
except Exception as e:
    print(f"  Exception: {e}")
