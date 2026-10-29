#!/usr/bin/env python3
import os

SERVER_PATH = "/opt/apps/answerr/api/server.py"

def patch():
    if not os.path.exists(SERVER_PATH):
        print(f"File not found: {SERVER_PATH}")
        return

    with open(SERVER_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    target = 'response.headers["X-RateLimit-Limit"] = str(_a["rate_limit_per_min"])'
    replacement = 'response.headers["X-Werrealm-Network"] = "werrealm.network"\n                response.headers["X-Werrealm-Engine"] = "Werrite-Q16.16"\n                response.headers["X-Werrealm-Token"] = "WERR"\n                response.headers["X-RateLimit-Limit"] = str(_a["rate_limit_per_min"])'

    target2 = 'response.headers["X-RateLimit-Limit"] = str(RATE_LIMITER.requests_per_window)'
    replacement2 = 'response.headers["X-Werrealm-Network"] = "werrealm.network"\n    response.headers["X-Werrealm-Engine"] = "Werrite-Q16.16"\n    response.headers["X-Werrealm-Token"] = "WERR"\n    response.headers["X-RateLimit-Limit"] = str(RATE_LIMITER.requests_per_window)'

    if "X-Werrealm-Network" in content:
        print("[*] Headers already present in server.py")
        return

    if target in content and target2 in content:
        content = content.replace(target, replacement, 1)
        content = content.replace(target2, replacement2, 1)
        with open(SERVER_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        print("[+] SUCCESS: Werrealm network headers successfully injected into server.py")
    else:
        print("[!] Target strings not found in server.py")

if __name__ == "__main__":
    patch()
