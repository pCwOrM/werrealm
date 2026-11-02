import os
import urllib.request
import json
import base64
import time
import sys

TOKEN = os.environ.get("GITHUB_TOKEN") or sys.argv[1] if len(sys.argv) > 1 else ""
if not TOKEN:
    print("[ERROR] Please provide GITHUB_TOKEN as environment variable or argument.")
    sys.exit(1)
UPSTREAM_OWNER = "ethereum-optimism"
UPSTREAM_REPO = "ethereum-optimism.github.io"
MY_USER = "pCwOrM"
BRANCH_NAME = "add-werr-token"

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Antigravity-Agent"
}

def api_request(url, method="GET", data=None):
    req_data = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=req_data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"[HTTP Error {e.code}] {url}: {err_msg}")
        raise

print("[1] Forking upstream repository...")
try:
    fork_res = api_request(f"https://api.github.com/repos/{UPSTREAM_OWNER}/{UPSTREAM_REPO}/forks", method="POST")
    print(f"    Fork initiated: {fork_res.get('html_url')}")
except urllib.error.HTTPError as e:
    if e.code == 202:
        print("    Fork request accepted (processing)...")
    else:
        raise

print("[2] Waiting for fork repository to become available...")
for attempt in range(1, 20):
    try:
        repo_info = api_request(f"https://api.github.com/repos/{MY_USER}/{UPSTREAM_REPO}")
        print(f"    Repository ready! (Default branch: {repo_info.get('default_branch')})")
        break
    except Exception:
        print(f"    Attempt {attempt}/20: waiting 3 seconds...")
        time.sleep(3)
else:
    print("[ERROR] Timed out waiting for fork repository.")
    sys.exit(1)

print("[3] Getting default branch commit SHA...")
default_branch = repo_info.get("default_branch", "master")
ref_res = api_request(f"https://api.github.com/repos/{MY_USER}/{UPSTREAM_REPO}/git/ref/heads/{default_branch}")
master_sha = ref_res["object"]["sha"]
print(f"    Base SHA ({default_branch}): {master_sha}")

print(f"[4] Creating working branch '{BRANCH_NAME}'...")
try:
    branch_res = api_request(
        f"https://api.github.com/repos/{MY_USER}/{UPSTREAM_REPO}/git/refs",
        method="POST",
        data={"ref": f"refs/heads/{BRANCH_NAME}", "sha": master_sha}
    )
    print(f"    Branch created: {branch_res['ref']}")
except urllib.error.HTTPError as e:
    if "Reference already exists" in str(e):
        print("    Branch already exists, continuing...")
    else:
        raise

print("[5] Preparing token data and logo...")
with open("werrealm/superchain_tokenlist/data/WERR/data.json", "rb") as f:
    data_json_bytes = f.read()
data_json_b64 = base64.b64encode(data_json_bytes).decode("ascii")

with open("werrealm/superchain_tokenlist/data/WERR/logo.svg", "rb") as f:
    logo_svg_bytes = f.read()
logo_svg_b64 = base64.b64encode(logo_svg_bytes).decode("ascii")

def put_file(path, content_b64, message):
    url = f"https://api.github.com/repos/{MY_USER}/{UPSTREAM_REPO}/contents/{path}"
    # check if file already exists to get its sha
    sha = None
    try:
        existing = api_request(f"{url}?ref={BRANCH_NAME}")
        sha = existing.get("sha")
    except Exception:
        pass
    
    payload = {
        "message": message,
        "content": content_b64,
        "branch": BRANCH_NAME
    }
    if sha:
        payload["sha"] = sha
        
    res = api_request(url, method="PUT", data=payload)
    print(f"    [OK] Committed {path} (Commit: {res['commit']['sha'][:8]})")

print("[6] Committing data.json and logo.svg to branch...")
put_file("data/WERR/data.json", data_json_b64, "feat: add Werrium (WERR) data.json on Base")
put_file("data/WERR/logo.svg", logo_svg_b64, "feat: add Werrium (WERR) logo.svg")

print("[7] Submitting Pull Request to upstream...")
pr_title = "Add Werrium (WERR) on Base"
pr_body = """### Token Addition Details

- **Token Name:** Werrium
- **Symbol:** WERR
- **Decimals:** 18
- **Chain:** Base Mainnet (Chain ID 8453)
- **Token Address:** `0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2`
- **Website:** https://werrealm.network
- **BaseScan Explorer:** https://basescan.org/token/0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2
- **Bridge Status:** Native Base deployment (`nobridge: true`)
- **Supply Cap:** 1,000,000,000 WERR (Fixed supply, no mint)
- **Treasury Multi-sig Vault:** `0x7CC5fd367e210F4678Bcfca054cbe0F87291E355` (Safe 2/2)

The metadata conforms strictly to the Superchain Token List schema (`data/WERR/data.json` & `data/WERR/logo.svg`).
"""

try:
    pr_res = api_request(
        f"https://api.github.com/repos/{UPSTREAM_OWNER}/{UPSTREAM_REPO}/pulls",
        method="POST",
        data={
            "title": pr_title,
            "head": f"{MY_USER}:{BRANCH_NAME}",
            "base": default_branch,
            "body": pr_body
        }
    )
    print("\n" + "="*60)
    print("SUCCESS! PULL REQUEST SUBMITTED:")
    print("PR URL   :", pr_res.get("html_url"))
    print("PR Number:", pr_res.get("number"))
    print("="*60)
except urllib.error.HTTPError as e:
    err_str = str(e)
    if "A pull request already exists" in err_str:
        print("[!] A pull request already exists from this branch.")
    else:
        raise
