"""
Werracle B2B Risk Radar — 24/7 Push Telemetry Background Worker
Polls active Pro/Institutional alert subscriptions in SQLite, evaluates live Morpho Blue
Health Factor breaches (GraphQL with RAMDisk fallback), applies per-subscription filters
and anti-spam escalation/cooldown rules, and dispatches HMAC-SHA256 webhooks & Telegram alerts.
"""

import os
import sys
import json
import time
import signal
import hashlib
import traceback
from typing import Any, Dict, List, Optional, Tuple

API_DIR = os.path.dirname(os.path.abspath(__file__))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

import radar_alerts

POLL_SEC = 20
DEFAULT_FETCH_TTL_SEC = 18.0
MORPHO_PAZARLAR = "/var/lib/werracle-health/morpho_pazarlar.json"
L1_PAZARLAR = "/var/lib/werracle-health/l1_morpho_pazarlar.json"
HEARTBEAT_PATH = "/var/lib/werracle-health/radar_alerts_worker.json"
STATE_PATH = "/var/lib/werracle-health/radar_alerts_worker_state.json"
COOLDOWN_SEC_BY_TIER = {
    "institutional": 600.0,
    "pro": 1800.0,
}

_STOP_REQUESTED = False


def _handle_signal(signum: int, _frame: Any) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def _write_json_atomic(path: str, data: Dict[str, Any], mode: int = 0o644) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(tmp_path, mode)
    os.replace(tmp_path, path)


def _read_json_safe(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {} if default is None else default


def _load_listed_markets() -> Dict[str, Tuple[int, List[str]]]:
    base_raw = _read_json_safe(MORPHO_PAZARLAR, {})
    eth_raw = _read_json_safe(L1_PAZARLAR, {})
    base_ids = [m.get("id") for m in (base_raw.get("pazarlar") or []) if m.get("listed", False) and m.get("id")]
    eth_ids = [m.get("id") for m in (eth_raw.get("pazarlar") or []) if m.get("listed", False) and m.get("id")]
    return {"base": (8453, base_ids), "ethereum_mainnet": (1, eth_ids)}


def _fingerprint_positions(positions: List[Dict[str, Any]]) -> str:
    keys = sorted(
        f"{p.get('chain','')}|{str(p.get('market_id') or '').lower()}|{str(p.get('borrower') or '').lower()}"
        for p in positions
    )
    if not keys:
        return ""
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()[:24]


def should_dispatch(
    prev: Optional[Dict[str, Any]],
    fingerprint: str,
    cur_min_hf: Optional[float],
    now: float,
    cooldown_sec: float,
) -> Tuple[bool, str]:
    """Determines whether a breaching alert should be pushed now vs suppressed by cooldown."""
    if not fingerprint:
        return False, "nominal"
    if not prev or not prev.get("last_sent_ts") or not prev.get("fingerprint"):
        return True, "initial_breach"
    if fingerprint != prev.get("fingerprint"):
        return True, "changed_positions"
    prev_min = prev.get("min_hf")
    if cur_min_hf is not None and prev_min is not None:
        if prev_min >= 1.0 and cur_min_hf < 1.0:
            return True, "crossed_below_1"
        if cur_min_hf <= float(prev_min) - 0.02:
            return True, "hf_deteriorated"
    if (now - float(prev.get("last_sent_ts") or 0.0)) >= cooldown_sec:
        return True, "cooldown_elapsed"
    return False, "cooldown_active"


def run_once(
    db_path: str = radar_alerts.DB_PATH,
    state: Optional[Dict[str, Any]] = None,
    heartbeat_path: Optional[str] = HEARTBEAT_PATH,
    state_path: Optional[str] = STATE_PATH,
    markets_by_chain: Optional[Dict[str, Tuple[int, List[str]]]] = None,
    breaches_override: Optional[Tuple[List[Dict[str, Any]], str]] = None,
    now_fn: Any = time.time,
) -> Dict[str, Any]:
    """Runs one surveillance and push cycle; returns the public-safe status heartbeat."""
    now = float(now_fn())
    if state is None:
        state = _read_json_safe(state_path, {}) if state_path else {}
    subs_state: Dict[str, Any] = state.setdefault("subscriptions", {})
    total_dispatched = int(state.get("dispatched_total") or 0)
    consecutive_errors = int(state.get("consecutive_errors") or 0)

    subs = radar_alerts.list_active_subscriptions(db_path=db_path)
    active_ids = {s["id"] for s in subs}
    for dead_id in [k for k in list(subs_state.keys()) if k not in active_ids]:
        del subs_state[dead_id]

    if not subs:
        hb = {
            "status": "IDLE_NO_SUBSCRIPTIONS",
            "poll_interval_sec": POLL_SEC,
            "active_subscriptions": 0,
            "last_cycle_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "last_cycle_ts": int(now),
            "last_fetch_source": "none_idle",
            "tracked_breaches_hf_1_05": 0,
            "dispatched_this_cycle": 0,
            "dispatched_total": total_dispatched,
            "consecutive_errors": 0,
            "pid": os.getpid(),
        }
        state["consecutive_errors"] = 0
        if heartbeat_path:
            _write_json_atomic(heartbeat_path, hb, mode=0o644)
        if state_path:
            _write_json_atomic(state_path, state, mode=0o600)
        return hb

    max_thr = max(float(s.get("hf_threshold") or 1.05) for s in subs)
    max_thr = max(1.05, min(max_thr, 1.50))

    if breaches_override is not None:
        breaches, fetch_source = breaches_override
    else:
        mkts = markets_by_chain if markets_by_chain is not None else _load_listed_markets()
        breaches, fetch_source = radar_alerts.fetch_hf_breaches_with_fallback(
            mkts,
            hf_threshold=max_thr,
            ttl=DEFAULT_FETCH_TTL_SEC,
        )

    dispatched_cycle = 0
    for sub in subs:
        sid = sub["id"]
        sub_thr = float(sub.get("hf_threshold") or 1.05)
        sub_vf = str(sub.get("vault_filter") or "all")
        sub_shock = int(sub.get("shock_threshold_pct") or 10)
        sub_tier = str(sub.get("effective_tier") or "pro").lower()
        cooldown = COOLDOWN_SEC_BY_TIER.get(sub_tier, 1800.0)

        payload = radar_alerts.build_alert_payload(
            hot_positions=breaches,
            hf_threshold=sub_thr,
            vault_filter=sub_vf,
            shock_threshold_pct=sub_shock,
        )
        summ = payload.get("summary") or {}
        positions = payload.get("critical_positions") or []
        fp = _fingerprint_positions(positions) if int(summ.get("breaching_positions_count") or 0) > 0 else ""
        cur_min_hf = summ.get("lowest_health_factor")

        if not fp:
            subs_state[sid] = {
                "last_sent_ts": (subs_state.get(sid) or {}).get("last_sent_ts", 0.0),
                "fingerprint": "",
                "min_hf": None,
                "critical_count": 0,
            }
            continue

        fire, _reason = should_dispatch(subs_state.get(sid), fp, cur_min_hf, now, cooldown)
        if not fire:
            continue

        res = radar_alerts.dispatch_push_alert(
            payload=payload,
            webhook_url=sub.get("webhook_url") or "",
            webhook_secret=sub.get("webhook_secret") or "",
            telegram_bot_token=sub.get("telegram_bot_token") or "",
            telegram_chat_id=sub.get("telegram_chat_id") or "",
            subscription_id=sid,
            db_path=db_path,
        )
        if any(d.get("ok") for d in (res.get("deliveries") or [])):
            dispatched_cycle += 1
            total_dispatched += 1
            subs_state[sid] = {
                "last_sent_ts": now,
                "fingerprint": fp,
                "min_hf": cur_min_hf,
                "critical_count": int(summ.get("breaching_positions_count") or 0),
            }

    breaches_105 = sum(1 for p in breaches if float(p.get("health_factor") or 99.0) <= 1.05)
    consecutive_errors = 0
    state["dispatched_total"] = total_dispatched
    state["consecutive_errors"] = consecutive_errors
    hb_status = "RAMDISK_FALLBACK" if fetch_source == "ramdisk_fallback" else "MONITORING"
    hb = {
        "status": hb_status,
        "poll_interval_sec": POLL_SEC,
        "active_subscriptions": len(subs),
        "last_cycle_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "last_cycle_ts": int(now),
        "last_fetch_source": fetch_source,
        "tracked_breaches_hf_1_05": breaches_105,
        "dispatched_this_cycle": dispatched_cycle,
        "dispatched_total": total_dispatched,
        "consecutive_errors": consecutive_errors,
        "pid": os.getpid(),
    }
    if heartbeat_path:
        _write_json_atomic(heartbeat_path, hb, mode=0o644)
    if state_path:
        _write_json_atomic(state_path, state, mode=0o600)
    return hb


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    radar_alerts.init_alerts_db(radar_alerts.DB_PATH)
    state = _read_json_safe(STATE_PATH, {})
    print(f"[radar-alerts-worker] started pid={os.getpid()} poll={POLL_SEC}s db={radar_alerts.DB_PATH}", flush=True)

    while not _STOP_REQUESTED:
        t0 = time.monotonic()
        try:
            hb = run_once(state=state)
            if hb.get("dispatched_this_cycle"):
                print(
                    f"[radar-alerts-worker] status={hb['status']} subs={hb['active_subscriptions']} "
                    f"dispatched={hb['dispatched_this_cycle']} src={hb['last_fetch_source']}",
                    flush=True,
                )
        except Exception as exc:
            err_n = int(state.get("consecutive_errors") or 0) + 1
            state["consecutive_errors"] = err_n
            now = time.time()
            hb_err = {
                "status": "DEGRADED_FETCH_ERROR",
                "poll_interval_sec": POLL_SEC,
                "active_subscriptions": int((_read_json_safe(HEARTBEAT_PATH, {}) or {}).get("active_subscriptions") or 0),
                "last_cycle_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                "last_cycle_ts": int(now),
                "last_fetch_source": "error",
                "last_error": str(exc)[:200],
                "consecutive_errors": err_n,
                "pid": os.getpid(),
            }
            try:
                _write_json_atomic(HEARTBEAT_PATH, hb_err, mode=0o644)
                _write_json_atomic(STATE_PATH, state, mode=0o600)
            except Exception:
                pass
            print(f"[radar-alerts-worker] cycle error #{err_n}: {exc}\n{traceback.format_exc(limit=3)}", flush=True)

        elapsed = time.monotonic() - t0
        sleep_rem = max(1.0, POLL_SEC - elapsed)
        deadline = time.monotonic() + sleep_rem
        while not _STOP_REQUESTED and time.monotonic() < deadline:
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))

    print("[radar-alerts-worker] stopped cleanly", flush=True)


if __name__ == "__main__":
    main()
