"""
Werracle B2B Risk Radar — Real-Time Push Telemetry (Webhook & Telegram Alert Engine)
Monitors Morpho Blue positions (HF < 1.05) and MetaMorpho Curator Vault shock thresholds
(Steakhouse, Gauntlet, Moonwell) across Base, Ethereum, and Arbitrum.
Delivers HMAC-SHA256 signed JSON webhooks and instant Telegram Bot alerts.
"""

import os
import time
import json
import hmac
import secrets
import hashlib
import sqlite3
import urllib.parse
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Set, Tuple

DB_PATH = "/var/lib/werracle-health/werracle_api_keys.db"
HOT_POS_CACHE_PATH = "/var/lib/werracle-health/morpho_hot_positions.json"


def _conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    c = sqlite3.connect(db_path, timeout=10.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    return c


def init_alerts_db(db_path: str = DB_PATH) -> None:
    conn = _conn(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_subscriptions (
                id TEXT PRIMARY KEY,
                key_hash TEXT,
                tier TEXT NOT NULL DEFAULT 'pro',
                email TEXT,
                webhook_url TEXT,
                webhook_secret TEXT NOT NULL,
                telegram_bot_token TEXT,
                telegram_chat_id TEXT,
                hf_threshold REAL NOT NULL DEFAULT 1.05,
                shock_threshold_pct INTEGER NOT NULL DEFAULT 10,
                vault_filter TEXT NOT NULL DEFAULT 'all',
                active INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL,
                last_triggered_at REAL,
                trigger_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                target TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status_code INTEGER,
                latency_ms REAL,
                ok INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at REAL NOT NULL
            )
        """)
    conn.close()


def _is_safe_webhook_url(url: str) -> bool:
    """Public http(s) endpoints only. 28 Oct 2026: resolves DNS and rejects every non-global address
    (loopback, RFC1918 incl. 172.16/12, CGNAT, link-local, IPv4-mapped IPv6, decimal-encoded IPs)."""
    if not url:
        return False
    try:
        import ipaddress, socket
        p = urllib.parse.urlparse(url.strip())
        if p.scheme not in ("https", "http") or p.username or p.password:
            return False
        host = (p.hostname or "").strip().lower()
        if not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return False
        port = p.port or (443 if p.scheme == "https" else 80)
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        if not infos:
            return False
        for info in infos:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if not ip.is_global or ip.is_multicast:
                return False
        return True
    except Exception:
        return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None  # a redirect could point the request at an internal address


_WEBHOOK_OPENER = urllib.request.build_opener(_NoRedirect)
_GQL = "https://blue-api.morpho.org/graphql"
_VAULT_ALLOC_CACHE: Dict[str, Any] = {"ts": 0.0, "vaults": [], "alias_mids": {}}
_RAMDISK_MORPHO_HOT = (
    ("base", "/dev/shm/werracle_ramdisk/morpho_base_hot.json"),
    ("ethereum_mainnet", "/dev/shm/werracle_ramdisk/l1_morpho_hot.json"),
)


def _norm_id_lower(mid: str) -> str:
    m = (mid or "").strip().lower()
    if not m:
        return ""
    return m if m.startswith("0x") else "0x" + m


def _fetch_vault_alloc_index(ttl: float = 300.0) -> List[Dict[str, Any]]:
    now = time.time()
    cached = _VAULT_ALLOC_CACHE.get("vaults") or []
    if cached and (now - float(_VAULT_ALLOC_CACHE.get("ts") or 0.0)) < ttl:
        return cached
    q = """
    query($c:[Int!]!,$n:Int!){
      vaults(first:$n, orderBy:TotalAssetsUsd, orderDirection:Desc, where:{chainId_in:$c, listed:true}){
        items {
          address name symbol
          chain { id }
          state {
            allocation {
              supplyAssetsUsd
              market { marketId }
            }
          }
        }
      }
    }"""
    try:
        body = json.dumps({"query": q, "variables": {"c": [8453, 1], "n": 80}}).encode()
        req = urllib.request.Request(
            _GQL,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "Werracle-Radar/2.2"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode("utf-8"))
        if res.get("errors"):
            return cached
        items = ((res.get("data") or {}).get("vaults") or {}).get("items") or []
        parsed: List[Dict[str, Any]] = []
        for v in items:
            allocs = (v.get("state") or {}).get("allocation") or []
            active_mids: Set[str] = set()
            all_mids: Set[str] = set()
            for a in allocs:
                mid = _norm_id_lower(((a.get("market") or {}).get("marketId")) or "")
                if not mid:
                    continue
                all_mids.add(mid)
                if float(a.get("supplyAssetsUsd") or 0.0) > 0:
                    active_mids.add(mid)
            parsed.append({
                "address": str(v.get("address") or "").lower(),
                "name": str(v.get("name") or "").lower(),
                "symbol": str(v.get("symbol") or "").lower(),
                "chain_id": (v.get("chain") or {}).get("id"),
                "market_ids": active_mids or all_mids,
            })
        if parsed:
            _VAULT_ALLOC_CACHE["ts"] = now
            _VAULT_ALLOC_CACHE["vaults"] = parsed
        return parsed or cached
    except Exception:
        return cached


def resolve_vault_market_ids(vault_filter: str) -> Set[str]:
    """Resolves a curator/vault filter (e.g. 'steakhouse', 'gauntlet', 'moonwell', '0x...') to allocated Morpho market IDs."""
    vf = (vault_filter or "").strip().lower()
    if not vf or vf == "all":
        return set()

    mids: Set[str] = set()
    target_addrs: Set[str] = set()
    alias_chains: Dict[str, int] = {}
    if vf.startswith("0x") and len(vf) == 42:
        target_addrs.add(vf)
    try:
        import curator_stress  # type: ignore
        for ak, aaddr in (getattr(curator_stress, "ALIASES", {}) or {}).items():
            if vf == ak.lower() or vf in ak.lower():
                target_addrs.add(str(aaddr).lower())
                cid = (getattr(curator_stress, "ALIAS_CHAINS", {}) or {}).get(ak)
                if cid:
                    alias_chains[str(aaddr).lower()] = int(cid)
    except Exception:
        curator_stress = None  # type: ignore

    for v in _fetch_vault_alloc_index():
        hay = f"{v['name']} {v['symbol']} {v['address']}"
        if vf in hay or v["address"] in target_addrs:
            mids.update(v.get("market_ids") or ())
            target_addrs.discard(v["address"])

    # Fetch any explicitly aliased/address vault not covered by the top-80 vault list
    now = time.time()
    alias_cache = _VAULT_ALLOC_CACHE.setdefault("alias_mids", {})
    for addr in sorted(target_addrs):
        hit = alias_cache.get(addr)
        if hit and (now - float(hit[0])) < 300.0:
            mids.update(hit[1])
            continue
        if curator_stress is not None:
            try:
                vobj, _ = curator_stress._vault(addr, alias_chains.get(addr))
                amids: Set[str] = set()
                for a in (vobj.get("state") or {}).get("allocation") or []:
                    mid = _norm_id_lower(((a.get("market") or {}).get("marketId")) or "")
                    if mid:
                        amids.add(mid)
                alias_cache[addr] = (now, amids)
                mids.update(amids)
            except Exception:
                pass
    return mids


def build_alert_payload(
    hot_positions: Optional[List[Dict[str, Any]]] = None,
    pazarlar: Optional[List[Dict[str, Any]]] = None,
    morpho_status: Optional[Dict[str, Any]] = None,
    hf_threshold: float = 1.05,
    vault_filter: str = "all",
    shock_threshold_pct: int = 10
) -> Dict[str, Any]:
    """Builds a canonical real-time Werracle Push Telemetry alert payload from live positions or markets."""
    now = time.time()
    vf = (vault_filter or "all").strip().lower()
    critical_list = []
    total_debt_at_risk = 0.0

    # Only real per-position data is used. No values are synthesised from market totals.
    items = list(hot_positions or [])
    resolved_vault_mids = resolve_vault_market_ids(vf) if vf not in ("all", "") else set()

    for pos in items:
        hf = float(pos.get("health_factor") or pos.get("hf") or 999.0)
        if hf <= hf_threshold:
            mkt = str(pos.get("market") or pos.get("pair") or "WETH/USDC")
            chain = str(pos.get("chain") or "base")
            mid_norm = _norm_id_lower(str(pos.get("market_id") or ""))
            if vf not in ("all", ""):
                text_match = (vf in mkt.lower()) or (vf in chain.lower())
                vault_match = bool(resolved_vault_mids and mid_norm in resolved_vault_mids)
                if not (text_match or vault_match):
                    continue
            debt_usd = float(pos.get("debt_usd") or pos.get("borrow_usd") or 0.0)
            total_debt_at_risk += debt_usd
            severity = "CRITICAL_IMMINENT_LIQUIDATION" if hf < 1.01 else ("HIGH_AT_RISK" if hf < 1.05 else "ELEVATED_WATCH")
            entry = {
                "chain": chain,
                "market": mkt,
                "market_id": pos.get("market_id") or "",
                "borrower": pos.get("borrower") or pos.get("user") or "0x...",
                "sample_borrower": pos.get("borrower") or pos.get("user") or "0x...",
                "health_factor": round(hf, 4),
                "debt_usd": round(debt_usd, 2),
                "collateral_usd": round(float(pos.get("collateral_usd") or 0.0), 2),
                "liquidation_incentive_bps": int(pos.get("lif_bps") or 400),
                "severity": severity
            }
            critical_list.append(entry)

    critical_list.sort(key=lambda x: -x["debt_usd"])   # largest exposures first
    top_alerts = critical_list[:15]
    below_one = [x for x in critical_list if x["health_factor"] < 1.0]
    top_sev = "CRITICAL" if any(x["health_factor"] < 1.01 for x in top_alerts) else ("ELEVATED" if top_alerts else "NOMINAL")

    return {
        "event_id": f"evt_wrk_{int(now)}_{secrets.token_hex(4)}",
        "event_type": "werracle.radar.hf_threshold_breach",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "unix_ts": int(now),
        "service": "Werracle B2B Risk Radar & OEV DaaS Push Telemetry",
        "criteria": {
            "hf_threshold": hf_threshold,
            "shock_threshold_pct": f"-{shock_threshold_pct}%",
            "vault_filter": vf
        },
        "summary": {
            "severity": top_sev,
            "critical_count": len(critical_list),
            "breaching_positions_count": len(critical_list),
            "total_liquidatable_or_at_risk_debt_usd": round(total_debt_at_risk, 2),
            "lowest_health_factor": min((x["health_factor"] for x in critical_list), default=None),
            "liquidatable_now_count": len(below_one),
            "liquidatable_now_debt_usd": round(sum(x["debt_usd"] for x in below_one), 2),
            "recommended_curator_action": (
                "IMMEDIATE_BUFFER_REBALANCE_OR_SOLVER_BID"
                if any(x["health_factor"] < 1.01 for x in top_alerts)
                else ("ACTIVE_HF_SURVEILLANCE" if top_alerts else "NOMINAL")
            )
        },
        "critical_positions": top_alerts,
        "critical_markets": top_alerts,
        "links": {
            "dashboard": "https://radar.werracle.com/v1/radar/dashboard",
            "hot_positions_api": "https://radar.werracle.com/v1/radar/hot-positions",
            "curator_stress_api": "https://api.werracle.com/v1/radar/curator/steakhouse"
        }
    }


def subscribe_alerts(
    key_hash: Optional[str] = "public_preview",
    tier: str = "pro",
    email: str = "",
    webhook_url: str = "",
    telegram_bot_token: str = "",
    telegram_chat_id: str = "",
    hf_threshold: float = 1.05,
    shock_threshold_pct: int = 10,
    vault_filter: str = "all",
    api_key_hash: Optional[str] = None,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    init_alerts_db(db_path)
    if api_key_hash and (not key_hash or key_hash == "public_preview"):
        key_hash = api_key_hash
    webhook_url = (webhook_url or "").strip()
    telegram_bot_token = (telegram_bot_token or "").strip()
    telegram_chat_id = (telegram_chat_id or "").strip()

    if not webhook_url and not telegram_chat_id:
        return {"success": False, "error": "Please provide either a Webhook URL (https://...) or a Telegram Chat ID."}
    if webhook_url and not _is_safe_webhook_url(webhook_url):
        return {"success": False, "error": "Invalid Webhook URL. Must be a public http:// or https:// endpoint."}

    hf_threshold = max(1.001, min(float(hf_threshold or 1.05), 1.50))
    shock_threshold_pct = max(5, min(int(shock_threshold_pct or 10), 30))
    sub_id = f"sub_{int(time.time())}_{secrets.token_hex(4)}"
    wh_secret = f"whsec_wrk_{secrets.token_hex(20)}"

    conn = _conn(db_path)
    with conn:
        conn.execute("""
            INSERT INTO alert_subscriptions (
                id, key_hash, tier, email, webhook_url, webhook_secret,
                telegram_bot_token, telegram_chat_id, hf_threshold, shock_threshold_pct,
                vault_filter, active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            sub_id, key_hash or "public_preview", tier or "pro", email or "",
            webhook_url, wh_secret, telegram_bot_token, telegram_chat_id,
            hf_threshold, shock_threshold_pct, (vault_filter or "all").strip(), time.time()
        ))
    conn.close()

    return {
        "success": True,
        "subscription_id": sub_id,
        "tier": tier,
        "webhook_url": webhook_url or None,
        "webhook_signing_secret": wh_secret,
        "webhook_hmac_secret": wh_secret,
        "signature_header": "X-Werracle-Signature-256",
        "telegram_chat_id": telegram_chat_id or None,
        "hf_threshold": hf_threshold,
        "shock_threshold_pct": shock_threshold_pct,
        "vault_filter": vault_filter or "all",
        "status": "active",
        "message": "Real-time Push Telemetry alert subscription registered. Store your webhook_signing_secret to verify HMAC-SHA256 signatures."
    }


def dispatch_push_alert(
    payload: Optional[Dict[str, Any]] = None,
    alert_payload: Optional[Dict[str, Any]] = None,
    webhook_url: str = "",
    webhook_secret: str = "",
    telegram_bot_token: str = "",
    telegram_chat_id: str = "",
    subscription_id: str = "adhoc_test",
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """Dispatches the alert payload to the specified Webhook URL and/or Telegram Chat ID and logs delivery."""
    init_alerts_db(db_path)
    if alert_payload and not payload:
        payload = alert_payload
    payload = payload or {}
    secret = webhook_secret or f"whsec_wrk_{secrets.token_hex(16)}"
    body_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sig_hex = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    deliveries = []
    conn = _conn(db_path)

    # 1. Webhook Delivery
    if webhook_url:
        if not _is_safe_webhook_url(webhook_url):
            deliveries.append({"channel": "webhook", "target": webhook_url, "ok": False, "error": "Invalid or internal URL blocked."})
        else:
            t0 = time.perf_counter()
            status_code = 0
            err_str = None
            ok = False
            try:
                req = urllib.request.Request(
                    webhook_url,
                    data=body_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "Werracle-Radar-PushTelemetry/2.2",
                        "X-Werracle-Event": payload.get("event_type", "werracle.radar.hf_threshold_breach"),
                        "X-Werracle-Delivery": payload.get("event_id", ""),
                        "X-Werracle-Signature-256": f"sha256={sig_hex}"
                    },
                    method="POST"
                )
                with _WEBHOOK_OPENER.open(req, timeout=8) as resp:
                    status_code = resp.getcode()
                    ok = 200 <= status_code < 300
            except urllib.error.HTTPError as he:
                status_code = he.code
                err_str = f"HTTP {he.code}"
            except Exception as ex:
                err_str = str(ex)[:200]
            ms = round((time.perf_counter() - t0) * 1000, 2)
            deliveries.append({
                "channel": "webhook",
                "target": webhook_url,
                "ok": ok,
                "status_code": status_code,
                "latency_ms": ms,
                "signature_sent": f"sha256={sig_hex}",
                "error": err_str
            })
            with conn:
                conn.execute("""
                    INSERT INTO alert_deliveries (subscription_id, channel, target, event_type, status_code, latency_ms, ok, error, created_at)
                    VALUES (?, 'webhook', ?, ?, ?, ?, ?, ?, ?)
                """, (subscription_id, webhook_url, payload.get("event_type", ""), status_code, ms, 1 if ok else 0, err_str, time.time()))

    # 2. Telegram Bot API Delivery
    if telegram_chat_id:
        bot_tok = (telegram_bot_token or os.environ.get("WERRACLE_TELEGRAM_BOT_TOKEN") or "").strip()
        if not bot_tok:
            deliveries.append({
                "channel": "telegram",
                "target": telegram_chat_id,
                "ok": False,
                "error": "Provide your Telegram Bot Token (from @BotFather) in telegram_bot_token to push directly to your chat/channel."
            })
        else:
            t0 = time.perf_counter()
            status_code = 0
            err_str = None
            ok = False
            summ = payload.get("summary") or {}
            top_pos = (payload.get("critical_positions") or [{}])[0]
            tg_text = (
                f"🚨 *Werracle Risk Radar — HF Alert*\n"
                f"• *Threshold:* `HF <= {payload['criteria']['hf_threshold']}`\n"
                f"• *Breaching Positions:* `{summ.get('breaching_positions_count', 0)}`\n"
                f"• *At-Risk Debt:* `${summ.get('total_liquidatable_or_at_risk_debt_usd', 0):,.2f}`\n"
                f"• *Lowest HF:* `{summ.get('lowest_health_factor') or 'N/A'}` ({top_pos.get('chain', 'base').upper()} — {top_pos.get('market', 'N/A')})\n"
                f"• *Action:* `{summ.get('recommended_curator_action', 'MONITOR')}`\n"
                f"🔗 [Open Werracle Radar Dashboard](https://radar.werracle.com/v1/radar/dashboard)"
            )
            tg_body = json.dumps({
                "chat_id": telegram_chat_id,
                "text": tg_text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }).encode("utf-8")
            try:
                tg_req = urllib.request.Request(
                    f"https://api.telegram.org/bot{bot_tok}/sendMessage",
                    data=tg_body,
                    headers={"Content-Type": "application/json", "User-Agent": "Werracle-Radar-PushTelemetry/2.2"},
                    method="POST"
                )
                with urllib.request.urlopen(tg_req, timeout=8) as resp:
                    status_code = resp.getcode()
                    ok = 200 <= status_code < 300
            except urllib.error.HTTPError as he:
                status_code = he.code
                err_str = f"Telegram HTTP {he.code}"
            except Exception as ex:
                err_str = str(ex)[:200]
            ms = round((time.perf_counter() - t0) * 1000, 2)
            deliveries.append({
                "channel": "telegram",
                "target": telegram_chat_id,
                "ok": ok,
                "status_code": status_code,
                "latency_ms": ms,
                "error": err_str
            })
            with conn:
                conn.execute("""
                    INSERT INTO alert_deliveries (subscription_id, channel, target, event_type, status_code, latency_ms, ok, error, created_at)
                    VALUES (?, 'telegram', ?, ?, ?, ?, ?, ?, ?)
                """, (subscription_id, telegram_chat_id, payload.get("event_type", ""), status_code, ms, 1 if ok else 0, err_str, time.time()))

    if subscription_id and subscription_id != "adhoc_test" and any(d.get("ok") for d in deliveries):
        with conn:
            conn.execute("""
                UPDATE alert_subscriptions
                SET last_triggered_at = ?,
                    trigger_count = COALESCE(trigger_count, 0) + 1
                WHERE id = ?
            """, (time.time(), subscription_id))

    conn.close()
    return {
        "success": True,
        "deliveries": deliveries,
        "alert_summary": payload.get("summary") or {"severity": "NOMINAL", "critical_count": 0},
        "signature_header": f"sha256={sig_hex}",
        "payload_dispatched": payload
    }


def list_active_subscriptions(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Returns active webhook/Telegram alert subscriptions backed by non-expired Pro/Institutional keys."""
    init_alerts_db(db_path)
    now = time.time()
    conn = _conn(db_path)
    try:
        has_keys = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='api_keys'"
        ).fetchone()
        if not has_keys:
            return []
        rows = conn.execute("""
            SELECT s.id, s.key_hash, lower(k.tier) AS effective_tier, s.email, s.webhook_url,
                   s.webhook_secret, s.telegram_bot_token, s.telegram_chat_id,
                   s.hf_threshold, s.shock_threshold_pct, s.vault_filter,
                   s.last_triggered_at, s.trigger_count
            FROM alert_subscriptions s
            JOIN api_keys k ON s.key_hash = k.key_hash
            WHERE s.active = 1
              AND lower(k.status) = 'active'
              AND k.expires_at > ?
              AND lower(k.tier) IN ('pro', 'institutional')
        """, (now,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Real health-factor breaches from the Morpho public API (listed markets only)
# ---------------------------------------------------------------------------
_HF_CACHE: Dict[Any, Any] = {}


def _norm_id(mid: str) -> str:
    mid = (mid or "").strip()
    return mid if mid.startswith("0x") else "0x" + mid


def fetch_hf_breaches(markets_by_chain: Dict[str, Any], hf_threshold: float = 1.05,
                      min_debt_usd: float = 100.0, ttl: float = 60.0,
                      max_rows_per_chain: int = 5000) -> List[Dict[str, Any]]:
    """markets_by_chain: {"base": (8453, [market ids]), "ethereum_mainnet": (1, [...])}.
    Returns borrow positions with Morpho healthFactor <= threshold and debt >= min_debt_usd."""
    thr = round(float(hf_threshold), 4)
    key = (thr, tuple(sorted((c, len(v[1])) for c, v in markets_by_chain.items())))
    hit = _HF_CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    q = ('query($m:[String!]!,$c:[Int!]!,$s:Int!){ marketPositions(first:1000, skip:$s, '
         'orderBy:BorrowShares, orderDirection:Desc, where:{marketUniqueKey_in:$m, chainId_in:$c, '
         'healthFactor_lte:%s, borrowShares_gte:"1"}){ items{ healthFactor user{address} '
         'market{ marketId lltv collateralAsset{symbol} loanAsset{symbol} } '
         'state{ borrowAssetsUsd collateralUsd } } pageInfo{countTotal} } }' % thr)
    out: List[Dict[str, Any]] = []
    for chain_name, (cid, ids) in markets_by_chain.items():
        ids_all = [_norm_id(i) for i in ids if i]
        for ci in range(0, len(ids_all), 100):
          ids = ids_all[ci:ci + 100]
          skip = 0
          while skip < max_rows_per_chain:
              body = json.dumps({"query": q, "variables": {"m": ids, "c": [cid], "s": skip}}).encode()
              req = urllib.request.Request(_GQL, data=body, headers={
                  "content-type": "application/json", "user-agent": "werracle-radar/2.2"})
              with urllib.request.urlopen(req, timeout=20) as r:
                  d = json.loads(r.read())
              if d.get("errors"):
                  raise RuntimeError(str(d["errors"])[:300])
              items = ((d.get("data") or {}).get("marketPositions") or {}).get("items") or []
              for it in items:
                  st = it.get("state") or {}
                  debt = float(st.get("borrowAssetsUsd") or 0.0)
                  hf = it.get("healthFactor")
                  if hf is None or debt < min_debt_usd:
                      continue
                  m = it.get("market") or {}
                  lltv = int(m.get("lltv") or 0) / 1e18
                  lif = min(1.15, 1.0 / (0.3 * lltv + 0.7)) if lltv else 1.0
                  out.append({
                      "chain": chain_name,
                      "market": "%s/%s" % ((m.get("collateralAsset") or {}).get("symbol", "?"),
                                           (m.get("loanAsset") or {}).get("symbol", "?")),
                      "market_id": m.get("marketId"),
                      "borrower": (it.get("user") or {}).get("address"),
                      "health_factor": float(hf),
                      "debt_usd": debt,
                      "collateral_usd": float(st.get("collateralUsd") or 0.0),
                      "lif_bps": int(round((lif - 1.0) * 10000)),
                  })
              if len(items) < 1000:
                  break
              skip += 1000
    out.sort(key=lambda x: (x["health_factor"], -x["debt_usd"]))
    _HF_CACHE[key] = (time.time(), out)
    return out
def _load_ramdisk_hf_breaches(
    markets_by_chain: Dict[str, Any],
    hf_threshold: float = 1.05,
    min_debt_usd: float = 100.0,
    max_age_sec: float = 900.0,
) -> List[Dict[str, Any]]:
    now = time.time()
    allowed_ids_by_chain: Dict[str, Set[str]] = {}
    for cname, (_cid, ids) in (markets_by_chain or {}).items():
        allowed_ids_by_chain[cname] = {_norm_id_lower(str(i)) for i in (ids or []) if i}

    out: List[Dict[str, Any]] = []
    fresh_sources = 0
    for cname, fpath in _RAMDISK_MORPHO_HOT:
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        upd = float(data.get("updated_at") or os.path.getmtime(fpath) or 0.0)
        if upd <= 0 or (now - upd) > max_age_sec:
            continue
        fresh_sources += 1
        allowed_mids = allowed_ids_by_chain.get(cname) or set()
        for it in data.get("positions") or []:
            hf = it.get("health_factor")
            debt = float(it.get("debt_usd") or 0.0)
            if hf is None or debt < min_debt_usd:
                continue
            hf_val = float(hf)
            if hf_val > hf_threshold:
                continue
            mid_norm = _norm_id_lower(str(it.get("market_id") or ""))
            if allowed_mids and mid_norm and mid_norm not in allowed_mids:
                continue
            lltv = float(it.get("lltv") or 0.0)
            lif = min(1.15, 1.0 / (0.3 * lltv + 0.7)) if 0 < lltv <= 1.0 else 1.0
            pair = str(it.get("market_pair") or "").strip() or (
                f"{it.get('collateral_symbol') or '?'}/{it.get('loan_symbol') or '?'}"
            )
            out.append({
                "chain": cname,
                "market": pair,
                "market_id": it.get("market_id") or mid_norm,
                "borrower": it.get("borrower") or it.get("user"),
                "health_factor": hf_val,
                "debt_usd": debt,
                "collateral_usd": float(it.get("collateral_usd") or 0.0),
                "lif_bps": int(round((lif - 1.0) * 10000)),
            })
    if fresh_sources == 0:
        raise RuntimeError("No fresh RAMDisk Morpho position cache available")
    out.sort(key=lambda x: (x["health_factor"], -x["debt_usd"]))
    return out


def fetch_hf_breaches_with_fallback(
    markets_by_chain: Dict[str, Any],
    hf_threshold: float = 1.05,
    min_debt_usd: float = 100.0,
    ttl: float = 60.0,
    max_rows_per_chain: int = 5000,
) -> Tuple[List[Dict[str, Any]], str]:
    """Queries live Morpho GraphQL positions and falls back to live RAMDisk snapshots on transient GraphQL errors."""
    try:
        return fetch_hf_breaches(
            markets_by_chain,
            hf_threshold=hf_threshold,
            min_debt_usd=min_debt_usd,
            ttl=ttl,
            max_rows_per_chain=max_rows_per_chain,
        ), "morpho_graphql"
    except Exception as gql_err:
        try:
            breaches = _load_ramdisk_hf_breaches(
                markets_by_chain,
                hf_threshold=hf_threshold,
                min_debt_usd=min_debt_usd,
            )
            return breaches, "ramdisk_fallback"
        except Exception:
            raise gql_err
