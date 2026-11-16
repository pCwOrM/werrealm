"""
Werracle B2B Risk Radar — Phase B Intelligence & Anti-Liquidation Shield Engine
Powers:
1. Pre-Flight Risk Shield & Position Rescue Engine (/v1/radar/shield/check, /shield/batch, /shield/position)
2. 12-Chain Live Open-Race & Solver Competition Analytics (/v1/radar/opportunities/open-race, /solvers/live)
3. Faz-2 Sub-Millisecond Oracle Shock Telemetry & SSE Leads (/v1/radar/telemetry/faz2-leads, /stream/oracle-shocks)
"""

import os
import re
import json
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = "/var/lib/werracle-health"
RAMDISK_DIR = "/dev/shm/werracle_ramdisk"

MORPHO_GQL = "https://blue-api.morpho.org/graphql"
MORPHO_PAZARLAR = os.path.join(BASE_DIR, "morpho_golge/pazarlar.json")
L1_HOT_FILE = os.path.join(RAMDISK_DIR, "l1_morpho_hot.json")
L1_HOT_FILE_DISK = os.path.join(BASE_DIR, "l1_morpho/hot_positions.json")
BASE_HOT_FILE = os.path.join(RAMDISK_DIR, "morpho_base_hot.json")
BASE_HOT_FILE_DISK = os.path.join(BASE_DIR, "morpho_golge/morpho_base_hot.json")
LIVE_STATE_RAM = os.path.join(RAMDISK_DIR, "live_state.json")
AAVE_ETH_STRIKE_RAM = os.path.join(RAMDISK_DIR, "aave_eth_strike.json")
AAVE_ETH_STRIKE_DISK = os.path.join(BASE_DIR, "aave_eth_strike.json")
WERRALIM_STREAM_FILE = os.path.join(BASE_DIR, "werralim_priority_stream.json")

COKLU_ZINCIR_OZET = os.path.join(BASE_DIR, "coklu_zincir/ozet.json")
COKLU_ZINCIR_OLAYLAR = os.path.join(BASE_DIR, "coklu_zincir/olaylar.jsonl")

ARB_FAZ2_DURUM = os.path.join(BASE_DIR, "arbitrum_faz2/durum.json")
ARB_FAZ2_FIRES = os.path.join(BASE_DIR, "arbitrum_faz2/ateslenirdi.jsonl")
BASE_FAZ2_DURUM = os.path.join(BASE_DIR, "base_faz2/durum.json")
BASE_FAZ2_FIRES = os.path.join(BASE_DIR, "base_faz2/ateslenirdi.jsonl")

EVM_ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_POS_CACHE: Dict[Tuple[int, str], Tuple[float, List[Dict[str, Any]]]] = {}
_CACHE_TTL_SEC = 15.0

CHAIN_ALIASES: Dict[str, List[str]] = {
    "base": ["base"],
    "8453": ["base"],
    "ethereum": ["ethereum"],
    "eth": ["ethereum"],
    "l1": ["ethereum"],
    "ethereum_mainnet": ["ethereum"],
    "1": ["ethereum"],
    "arbitrum": ["arbitrum"],
    "arb": ["arbitrum"],
    "42161": ["arbitrum"],
    "all": ["base", "ethereum", "arbitrum"],
}


def normalize_chains(chain: str) -> List[str]:
    key = (chain or "all").strip().lower()
    if key not in CHAIN_ALIASES:
        raise ValueError(f"Unsupported chain '{chain}'. Choose one of: base, ethereum, arbitrum, all.")
    return list(CHAIN_ALIASES[key])


def validate_evm_address(address: str) -> str:
    addr = (address or "").strip()
    if not EVM_ADDR_RE.match(addr):
        raise ValueError("Invalid EVM address format (expected 0x followed by 40 hex characters).")
    return addr.lower()


def _read_json_safe(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {} if default is None else default


def _tail_jsonl(path: str, max_lines: int = 500) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    dq: deque = deque(maxlen=max_lines)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if s:
                    dq.append(s)
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for s in dq:
        try:
            out.append(json.loads(s))
        except Exception:
            continue
    return out


def compute_rescue_metrics(
    hf: float,
    debt_usd: float,
    collateral_usd: float,
    lltv: float = 0.0,
    target_hf: float = 1.25,
    shock_pct: float = 10.0,
) -> Dict[str, Any]:
    """Computes exact Health Factor buffer, shock simulation, and repay/collateral rescue recipes."""
    hf_val = float(hf or 0.0)
    debt = max(0.0, float(debt_usd or 0.0))
    coll = max(0.0, float(collateral_usd or 0.0))
    lltv_val = float(lltv or 0.0)
    if lltv_val > 1.0:
        lltv_val = lltv_val / 1e18

    if coll > 0 and debt > 0 and hf_val > 0:
        lt_eff = min(0.99, max(0.10, (hf_val * debt) / coll))
    elif 0.0 < lltv_val <= 1.0:
        lt_eff = lltv_val
    else:
        lt_eff = 0.85

    drop_needed_pct = round(max(0.0, (1.0 - (1.0 / hf_val)) * 100.0), 2) if hf_val > 0 else 0.0
    shocked_hf = round(hf_val * max(0.0, 1.0 - (shock_pct / 100.0)), 4)

    def _recipe(t_hf: float) -> Dict[str, Any]:
        if debt <= 0 or hf_val >= t_hf:
            return {"target_hf": t_hf, "action_needed": False, "repay_debt_usd": 0.0, "add_collateral_usd": 0.0}
        repay = max(0.0, debt * (1.0 - (hf_val / t_hf))) if hf_val >= 0 else debt
        if coll > 0 and hf_val > 0:
            add_coll = max(0.0, coll * ((t_hf / hf_val) - 1.0))
        else:
            add_coll = max(0.0, ((t_hf - hf_val) * debt) / lt_eff)
        return {
            "target_hf": round(t_hf, 2),
            "action_needed": True,
            "repay_debt_usd": round(repay, 2),
            "add_collateral_usd": round(add_coll, 2),
        }

    if hf_val <= 1.0:
        risk_status = "LIQUIDATABLE_NOW"
    elif hf_val < 1.05:
        risk_status = "CRITICAL_DANGER"
    elif hf_val < target_hf:
        risk_status = "ELEVATED_REBALANCE_RECOMMENDED"
    else:
        risk_status = "PROTECTED"

    return {
        "effective_lt": round(lt_eff, 4),
        "drop_needed_pct": drop_needed_pct,
        "shock_scenario_pct": -abs(round(shock_pct, 2)),
        "shocked_hf": shocked_hf,
        "would_liquidate_on_shock": bool(debt > 0 and shocked_hf <= 1.0),
        "risk_status": risk_status,
        "rescue_target": _recipe(target_hf),
        "rescue_hf_1_15": _recipe(1.15),
        "rescue_hf_1_25": _recipe(1.25),
    }


def _query_morpho_user_chain(address: str, chain_id: int) -> List[Dict[str, Any]]:
    now = time.time()
    ck = (chain_id, address)
    cached = _POS_CACHE.get(ck)
    if cached and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    q = """
    query($u:[String!]!,$c:[Int!]!){
      marketPositions(first:50, where:{userAddress_in:$u, chainId_in:$c, borrowShares_gte:"1"}){
        items {
          healthFactor
          user { address }
          market { marketId lltv loanAsset { symbol } collateralAsset { symbol } }
          state { borrowAssetsUsd collateralUsd }
        }
      }
    }"""
    body = json.dumps({"query": q, "variables": {"u": [address], "c": [chain_id]}}).encode("utf-8")
    req = urllib.request.Request(
        MORPHO_GQL,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Werracle-Radar-Shield/2.3"},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    if res.get("errors"):
        raise RuntimeError(str(res["errors"])[:250])

    chain_name = "base" if chain_id == 8453 else "ethereum"
    items = ((res.get("data") or {}).get("marketPositions") or {}).get("items") or []
    parsed: List[Dict[str, Any]] = []
    for it in items:
        hf = it.get("healthFactor")
        if hf is None:
            continue
        m = it.get("market") or {}
        st = it.get("state") or {}
        lltv = int(m.get("lltv") or 0) / 1e18 if m.get("lltv") else 0.0
        coll_sym = (m.get("collateralAsset") or {}).get("symbol") or "?"
        loan_sym = (m.get("loanAsset") or {}).get("symbol") or "?"
        parsed.append({
            "chain": chain_name,
            "chain_id": chain_id,
            "protocol": "morpho_blue",
            "market_id": (m.get("marketId") or "").lower(),
            "market_pair": f"{coll_sym}/{loan_sym}",
            "borrower": ((it.get("user") or {}).get("address") or address).lower(),
            "health_factor": round(float(hf), 6),
            "debt_usd": round(float(st.get("borrowAssetsUsd") or 0.0), 2),
            "collateral_usd": round(float(st.get("collateralUsd") or 0.0), 2),
            "lltv": round(lltv, 4),
            "source": "morpho_graphql_live",
        })
    if len(_POS_CACHE) > 2048:
        _POS_CACHE.clear()
    _POS_CACHE[ck] = (now, parsed)
    return parsed


def lookup_address_positions(
    address: str,
    chain: str = "all",
    use_graphql: bool = True,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Finds active Morpho Blue and Aave v3 positions for an address across live RAMDisk/GraphQL caches."""
    addr_l = validate_evm_address(address)
    chains = normalize_chains(chain)
    merged: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    sources_checked: List[str] = []

    def _put(pos: Dict[str, Any], prefer: bool = False) -> None:
        key = (pos["chain"], pos["protocol"], pos.get("market_id") or pos["protocol"])
        if prefer or key not in merged:
            merged[key] = pos

    if "base" in chains:
        sources_checked.append("base_morpho_ramdisk")
        bhot = _read_json_safe(BASE_HOT_FILE) or _read_json_safe(BASE_HOT_FILE_DISK)
        for p in bhot.get("positions") or []:
            if str(p.get("borrower") or "").lower() == addr_l:
                _put({
                    "chain": "base",
                    "chain_id": 8453,
                    "protocol": "morpho_blue",
                    "market_id": str(p.get("market_id") or "").lower(),
                    "market_pair": p.get("market_pair") or f"{p.get('collateral_symbol','?')}/{p.get('loan_symbol','?')}",
                    "borrower": addr_l,
                    "health_factor": round(float(p.get("health_factor") or 0.0), 6),
                    "debt_usd": round(float(p.get("debt_usd") or 0.0), 2),
                    "collateral_usd": round(float(p.get("collateral_usd") or 0.0), 2),
                    "lltv": float(p.get("lltv") or 0.0),
                    "source": "morpho_base_ramdisk",
                })

    if "ethereum" in chains:
        sources_checked.append("ethereum_morpho_ramdisk")
        l1hot = _read_json_safe(L1_HOT_FILE) or _read_json_safe(L1_HOT_FILE_DISK)
        for p in l1hot.get("positions") or []:
            if str(p.get("borrower") or "").lower() == addr_l:
                _put({
                    "chain": "ethereum",
                    "chain_id": 1,
                    "protocol": "morpho_blue",
                    "market_id": str(p.get("market_id") or "").lower(),
                    "market_pair": p.get("market_pair") or f"{p.get('collateral_symbol','?')}/{p.get('loan_symbol','?')}",
                    "borrower": addr_l,
                    "health_factor": round(float(p.get("health_factor") or 0.0), 6),
                    "debt_usd": round(float(p.get("debt_usd") or 0.0), 2),
                    "collateral_usd": round(float(p.get("collateral_usd") or 0.0), 2),
                    "lltv": float(p.get("lltv") or 0.0),
                    "source": "morpho_l1_ramdisk",
                })

    if use_graphql:
        for ch_name, cid in (("base", 8453), ("ethereum", 1)):
            if ch_name in chains:
                try:
                    gql_rows = _query_morpho_user_chain(addr_l, cid)
                    sources_checked.append(f"{ch_name}_morpho_graphql")
                    for gp in gql_rows:
                        _put(gp, prefer=True)
                except Exception:
                    sources_checked.append(f"{ch_name}_morpho_graphql_unavailable")

    live_st = _read_json_safe(LIVE_STATE_RAM)
    if "ethereum" in chains:
        sources_checked.append("ethereum_aave_v3_ramdisk")
        aeth = _read_json_safe(AAVE_ETH_STRIKE_RAM) or _read_json_safe(AAVE_ETH_STRIKE_DISK)
        q_eth = aeth.get("queue") or live_st.get("gamma_strike_queue_eth") or []
        for x in q_eth:
            u = str(x.get("borrower") or x.get("address") or "").lower()
            if u == addr_l:
                _put({
                    "chain": "ethereum",
                    "chain_id": 1,
                    "protocol": "aave_v3",
                    "market_id": "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",
                    "market_pair": "Aave v3 Cross-Collateral Portfolio",
                    "borrower": addr_l,
                    "health_factor": round(float(x.get("hf") or x.get("health_factor") or 0.0), 6),
                    "debt_usd": round(float(x.get("debt_usd") or 0.0), 2),
                    "collateral_usd": round(float(x.get("collateral_usd") or 0.0), 2),
                    "lltv": 0.825,
                    "source": "aave_eth_ramdisk",
                })

    for ch_name, cid, qkey in (
        ("base", 8453, "gamma_strike_queue_base"),
        ("arbitrum", 42161, "gamma_strike_queue_arb"),
    ):
        if ch_name in chains:
            sources_checked.append(f"{ch_name}_aave_v3_ramdisk")
            for x in live_st.get(qkey) or []:
                u = str(x.get("address") or x.get("borrower") or "").lower()
                if u == addr_l:
                    _put({
                        "chain": ch_name,
                        "chain_id": cid,
                        "protocol": "aave_v3",
                        "market_id": f"aave_v3_{ch_name}",
                        "market_pair": f"Aave v3 ({ch_name.title()})",
                        "borrower": addr_l,
                        "health_factor": round(float(x.get("hf") or 0.0), 6),
                        "debt_usd": round(float(x.get("debt_usd") or 0.0), 2),
                        "collateral_usd": round(float(x.get("collateral_usd") or 0.0), 2),
                        "lltv": 0.825,
                        "source": f"aave_{ch_name}_ramdisk",
                    })

    rows = sorted(merged.values(), key=lambda r: (float(r.get("health_factor") or 999.0), -float(r.get("debt_usd") or 0.0)))
    return rows, sources_checked


def _get_werralim_regime() -> Dict[str, Any]:
    st = _read_json_safe(WERRALIM_STREAM_FILE, {})
    w = st.get("werralim") or {}
    ts = float(st.get("timestamp") or 0.0)
    age = round(time.time() - ts, 1) if ts else None
    vol_z = float((w.get("volatility_model") or {}).get("statistical_z_score") or 0.0)
    dir_z = float((w.get("directional_model") or {}).get("statistical_z_score") or 0.0)
    return {
        "stream_active": bool(w.get("stream_valid") and age is not None and age < 120.0),
        "age_sec": age,
        "direction_label": w.get("direction_label"),
        "predicted_direction": w.get("predicted_direction"),
        "directional_z_score": round(dir_z, 3),
        "volatility_z_score": round(vol_z, 3),
        "high_volatility_regime": abs(vol_z) >= 5.0,
    }


def get_position_shield(
    address: str,
    chain: str = "all",
    target_hf: float = 1.25,
    shock_pct: float = 10.0,
    include_rescue_recipe: bool = True,
    use_graphql: bool = True,
) -> Dict[str, Any]:
    addr_l = validate_evm_address(address)
    positions, sources = lookup_address_positions(addr_l, chain=chain, use_graphql=use_graphql)
    regime = _get_werralim_regime()

    enriched: List[Dict[str, Any]] = []
    total_debt = 0.0
    total_coll = 0.0
    worst_hf: Optional[float] = None

    for p in positions:
        hf = float(p.get("health_factor") or 0.0)
        debt = float(p.get("debt_usd") or 0.0)
        coll = float(p.get("collateral_usd") or 0.0)
        lltv = float(p.get("lltv") or 0.0)
        total_debt += debt
        total_coll += coll
        if worst_hf is None or hf < worst_hf:
            worst_hf = hf

        calc = compute_rescue_metrics(
            hf=hf,
            debt_usd=debt,
            collateral_usd=coll,
            lltv=lltv,
            target_hf=target_hf,
            shock_pct=shock_pct,
        )
        entry = dict(p)
        entry["effective_lt"] = calc["effective_lt"]
        entry["drop_needed_pct"] = calc["drop_needed_pct"]
        entry["shock_simulation"] = {
            "shock_pct": calc["shock_scenario_pct"],
            "projected_hf": calc["shocked_hf"],
            "would_liquidate": calc["would_liquidate_on_shock"],
        }
        entry["risk_status"] = calc["risk_status"]
        if include_rescue_recipe:
            entry["rescue_recipe"] = {
                "requested_target": calc["rescue_target"],
                "benchmark_1_15": calc["rescue_hf_1_15"],
                "benchmark_1_25": calc["rescue_hf_1_25"],
            }
        enriched.append(entry)

    if not enriched:
        overall = "CLEAR_NO_ACTIVE_DEBT"
    elif worst_hf is not None and worst_hf <= 1.0:
        overall = "BLOCK_LIQUIDATABLE_NOW"
    elif worst_hf is not None and worst_hf < 1.05:
        overall = "CRITICAL_SHIELD_INTERVENTION_NEEDED"
    elif worst_hf is not None and worst_hf < target_hf:
        overall = "WARN_BELOW_TARGET_BUFFER"
    else:
        overall = "PASS_PROTECTED"

    return {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "address": addr_l,
        "chain_filter": (chain or "all").lower(),
        "target_hf": target_hf,
        "shock_pct": -abs(shock_pct),
        "overall_verdict": overall,
        "active_positions_count": len(enriched),
        "lowest_health_factor": worst_hf,
        "total_debt_usd": round(total_debt, 2),
        "total_collateral_usd": round(total_coll, 2),
        "positions": enriched,
        "werralim_regime_context": regime,
        "sources_checked": sources,
    }


def evaluate_preflight_check(
    address: str,
    chain: str = "base",
    action: str = "preflight",
    delta_debt_usd: float = 0.0,
    delta_collateral_usd: float = 0.0,
    min_safe_hf: float = 1.15,
    shock_pct: float = 10.0,
    market_id: Optional[str] = None,
    tier: str = "developer",
    use_graphql: bool = True,
    positions_override: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Deterministic pre-signing transaction risk shield for wallets, AI agents, and multisigs."""
    addr_l = validate_evm_address(address)
    if positions_override is not None:
        positions = list(positions_override)
        sources = ["test_override"]
    else:
        positions, sources = lookup_address_positions(addr_l, chain=chain, use_graphql=use_graphql)
    regime = _get_werralim_regime()

    target_pos: Optional[Dict[str, Any]] = None
    if market_id:
        mid_l = market_id.strip().lower()
        for p in positions:
            if (p.get("market_id") or "").lower() == mid_l:
                target_pos = p
                break
    elif positions:
        target_pos = positions[0]

    reason_codes: List[str] = []
    if target_pos is None:
        if delta_debt_usd > 0 and delta_collateral_usd <= 0:
            return {
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "address": addr_l,
                "chain": (chain or "base").lower(),
                "action": action,
                "verdict": "WARN",
                "reason_codes": ["NO_TRACKED_EXISTING_POSITION_FOR_DEBT_INCREASE"],
                "message": "No tracked Morpho/Aave debt position found; verify collateral balance on-chain before increasing debt.",
                "werralim_regime_context": regime,
                "sources_checked": sources,
            }
        return {
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "address": addr_l,
            "chain": (chain or "base").lower(),
            "action": action,
            "verdict": "PASS",
            "reason_codes": ["NO_ACTIVE_AT_RISK_DEBT_DETECTED"],
            "active_positions_count": 0,
            "werralim_regime_context": regime,
            "sources_checked": sources,
        }

    cur_hf = float(target_pos.get("health_factor") or 0.0)
    cur_debt = float(target_pos.get("debt_usd") or 0.0)
    cur_coll = float(target_pos.get("collateral_usd") or 0.0)
    cur_calc = compute_rescue_metrics(
        hf=cur_hf,
        debt_usd=cur_debt,
        collateral_usd=cur_coll,
        lltv=float(target_pos.get("lltv") or 0.0),
        target_hf=min_safe_hf,
        shock_pct=shock_pct,
    )
    lt_eff = cur_calc["effective_lt"]

    new_debt = max(0.0, cur_debt + float(delta_debt_usd or 0.0))
    new_coll = max(0.0, cur_coll + float(delta_collateral_usd or 0.0)) if (cur_coll > 0 or delta_collateral_usd > 0) else 0.0
    cur_adj_coll = cur_debt * cur_hf if cur_debt > 0 else cur_coll * lt_eff
    proj_adj_coll = max(0.0, cur_adj_coll + float(delta_collateral_usd or 0.0) * lt_eff)
    proj_hf = round(proj_adj_coll / new_debt, 4) if new_debt > 0 else 999.0

    proj_calc = compute_rescue_metrics(
        hf=proj_hf,
        debt_usd=new_debt,
        collateral_usd=new_coll,
        lltv=float(target_pos.get("lltv") or 0.0),
        target_hf=min_safe_hf,
        shock_pct=shock_pct,
    )

    if new_debt <= 0:
        verdict = "PASS"
        reason_codes.append("DEBT_FULLY_CLEARED")
    elif proj_hf <= 1.03:
        verdict = "BLOCK"
        reason_codes.append("PROJECTED_HF_CRITICAL_BELOW_1_03")
    elif proj_hf < min_safe_hf:
        verdict = "BLOCK"
        reason_codes.append(f"PROJECTED_HF_BELOW_MIN_SAFE_{min_safe_hf:.2f}")
    elif proj_calc["shocked_hf"] < 1.05:
        verdict = "WARN"
        reason_codes.append(f"VULNERABLE_TO_{-abs(shock_pct):.0f}PCT_COLLATERAL_SHOCK")
    else:
        verdict = "PASS"
        reason_codes.append("SAFE_BUFFER_VERIFIED")

    if regime.get("high_volatility_regime") and new_debt > 0:
        reason_codes.append("HIGH_VOLATILITY_REGIME_ACTIVE")
        if verdict == "PASS" and proj_hf < (min_safe_hf + 0.08):
            verdict = "WARN"

    out: Dict[str, Any] = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "address": addr_l,
        "chain": target_pos["chain"],
        "protocol": target_pos["protocol"],
        "market_id": target_pos.get("market_id"),
        "market_pair": target_pos.get("market_pair"),
        "action": action,
        "verdict": verdict,
        "reason_codes": reason_codes,
        "current_metrics": {
            "health_factor": cur_hf,
            "debt_usd": round(cur_debt, 2),
            "collateral_usd": round(cur_coll, 2),
            "drop_needed_pct": cur_calc["drop_needed_pct"],
            "effective_lt": lt_eff,
        },
        "projected_metrics": {
            "delta_debt_usd": round(float(delta_debt_usd or 0.0), 2),
            "delta_collateral_usd": round(float(delta_collateral_usd or 0.0), 2),
            "health_factor": proj_hf,
            "debt_usd": round(new_debt, 2),
            "drop_needed_pct": proj_calc["drop_needed_pct"],
            "shocked_hf": proj_calc["shocked_hf"],
            "shock_pct": -abs(round(shock_pct, 2)),
        },
        "werralim_regime_context": regime,
        "sources_checked": sources,
    }
    if tier in ("pro", "institutional"):
        out["rescue_targets"] = {
            "to_requested_min_safe_hf": proj_calc["rescue_target"],
            "to_hf_1_15": proj_calc["rescue_hf_1_15"],
            "to_hf_1_25": proj_calc["rescue_hf_1_25"],
        }
    return out


def build_open_race_payload(
    window: str = "7d",
    chain: str = "all",
    min_open_usd: float = 0.0,
    ozet_path: str = COKLU_ZINCIR_OZET,
    olaylar_path: str = COKLU_ZINCIR_OLAYLAR,
) -> Dict[str, Any]:
    """Builds 12-chain non-SVR open-race liquidation opportunities ranking & recent examples."""
    win_norm = "24h" if (window or "7d").lower() in ("24h", "24sa") else "7d"
    ozet_key = "24sa" if win_norm == "24h" else "7g"
    ch_filter = (chain or "all").strip().lower()

    oz = _read_json_safe(ozet_path, {})
    chains_raw = oz.get("zincirler") or {}
    rows: List[Dict[str, Any]] = []
    total_open_usd = 0.0
    total_liqs = 0

    for cname, cdata in chains_raw.items():
        if ch_filter not in ("all", "") and ch_filter != cname.lower():
            continue
        wstats = (cdata or {}).get(ozet_key) or {}
        liqs = int(wstats.get("likidasyon") or 0)
        meaningful = int(wstats.get("anlamli_ge5") or 0)
        gross_usd = float(wstats.get("brut_toplam_usd") or 0.0)
        debt_usd = float(wstats.get("borc_tum_usd") or 0.0)
        svr_share = wstats.get("svr_payi")
        open_usd = float(wstats.get("acik_yaris_brut_usd") or 0.0)
        if open_usd < float(min_open_usd or 0.0):
            continue

        total_open_usd += open_usd
        total_liqs += liqs
        top_execs = [
            {"address_prefix": item[0], "wins": int(item[1])}
            for item in (wstats.get("en_cok_kazanan") or [])
            if isinstance(item, (list, tuple)) and len(item) >= 2
        ]

        if svr_share is not None and float(svr_share) >= 0.5:
            classification = "SVR_DOMINATED_AUCTION"
        elif (svr_share is None or float(svr_share) == 0.0) and open_usd >= 10000.0:
            classification = "HIGH_OPEN_RACE_ZERO_SVR"
        elif open_usd >= 500.0:
            classification = "ACTIVE_OPEN_COMPETITION"
        else:
            classification = "LOW_VOLUME"

        rows.append({
            "chain": cname,
            "window": win_norm,
            "liquidations_total": liqs,
            "meaningful_events_ge5_usd": meaningful,
            "meaningful_gross_bonus_usd": round(gross_usd, 2),
            "total_liquidated_debt_usd": round(debt_usd, 2),
            "svr_adoption_share": svr_share,
            "svr_locked_pct": round(float(svr_share) * 100.0, 1) if svr_share is not None else None,
            "open_competition_bonus_usd": round(open_usd, 2),
            "opportunity_classification": classification,
            "top_executors": top_execs,
        })

    rows.sort(key=lambda r: (-r["open_competition_bonus_usd"], -r["liquidations_total"]))

    recent_open: List[Dict[str, Any]] = []
    for ev in reversed(_tail_jsonl(olaylar_path, max_lines=600)):
        ag = str(ev.get("ag") or "").lower()
        if ch_filter not in ("all", "") and ag != ch_filter:
            continue
        if ev.get("svr") is True:
            continue
        brut = float(ev.get("brut_usd") or 0.0)
        if brut < 5.0 or brut > 2_000_000.0:
            continue
        recent_open.append({
            "chain": ag,
            "timestamp_utc": ev.get("zaman_utc"),
            "block": ev.get("blok"),
            "pair": f"{ev.get('teminat','?')}/{ev.get('borc','?')}",
            "debt_usd": round(float(ev.get("borc_usd") or 0.0), 2),
            "gross_bonus_usd": round(brut, 2),
            "executor": ev.get("islem_to") or ev.get("likidator"),
            "tx_hash": ev.get("tx"),
        })
        if len(recent_open) >= 20:
            break

    return {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_updated_utc": oz.get("guncellendi"),
        "window": win_norm,
        "chain_filter": ch_filter,
        "chains_evaluated": len(rows),
        "total_open_competition_bonus_usd": round(total_open_usd, 2),
        "total_liquidations_window": total_liqs,
        "chains_ranked": rows,
        "recent_open_race_events": recent_open,
    }


def _parse_utc_epoch(ts_str: str) -> Optional[float]:
    if not ts_str:
        return None
    s = str(ts_str).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def build_live_solvers_payload(
    window: str = "7d",
    chain: str = "all",
    svr_only: bool = False,
    limit: int = 50,
    olaylar_path: str = COKLU_ZINCIR_OLAYLAR,
) -> Dict[str, Any]:
    """Aggregates live liquidation solver & executor competition directly from 12-chain events."""
    win_norm = "24h" if (window or "7d").lower() in ("24h", "24sa") else "7d"
    cutoff = time.time() - (86400.0 if win_norm == "24h" else 7.0 * 86400.0)
    ch_filter = (chain or "all").strip().lower()

    stats: Dict[str, Dict[str, Any]] = {}
    total_events = 0
    total_svr = 0

    for ev in _tail_jsonl(olaylar_path, max_lines=5000):
        ep = _parse_utc_epoch(ev.get("zaman_utc") or "")
        if ep is not None and ep < cutoff:
            continue
        ag = str(ev.get("ag") or "").lower()
        if ch_filter not in ("all", "") and ag != ch_filter:
            continue
        is_svr = bool(ev.get("svr"))
        if svr_only and not is_svr:
            continue

        total_events += 1
        if is_svr:
            total_svr += 1

        exec_addr = str(ev.get("islem_to") or ev.get("likidator") or "unknown").lower()
        st = stats.get(exec_addr)
        if st is None:
            st = {
                "executor_contract": exec_addr,
                "wins_count": 0,
                "meaningful_wins_ge5": 0,
                "svr_wins_count": 0,
                "open_race_wins_count": 0,
                "total_debt_liquidated_usd": 0.0,
                "total_gross_bonus_usd": 0.0,
                "chains_active": set(),
                "pairs_sample": set(),
                "last_seen_utc": "",
            }
            stats[exec_addr] = st

        brut = float(ev.get("brut_usd") or 0.0)
        debt = float(ev.get("borc_usd") or 0.0)
        st["wins_count"] += 1
        if is_svr:
            st["svr_wins_count"] += 1
        else:
            st["open_race_wins_count"] += 1
        if 5.0 <= brut <= 2_000_000.0:
            st["meaningful_wins_ge5"] += 1
            st["total_gross_bonus_usd"] += brut
        if debt <= 50_000_000.0:
            st["total_debt_liquidated_usd"] += debt
        if ag:
            st["chains_active"].add(ag)
        pair = f"{ev.get('teminat','?')}/{ev.get('borc','?')}"
        if len(st["pairs_sample"]) < 8:
            st["pairs_sample"].add(pair)
        z = str(ev.get("zaman_utc") or "")
        if z > st["last_seen_utc"]:
            st["last_seen_utc"] = z

    ranked = sorted(
        stats.values(),
        key=lambda x: (-x["total_gross_bonus_usd"], -x["wins_count"]),
    )
    hhi = 0.0
    if total_events > 0:
        for r in ranked:
            share_pct = (r["wins_count"] / total_events) * 100.0
            hhi += share_pct * share_pct

    formatted: List[Dict[str, Any]] = []
    for r in ranked[:limit]:
        w_cnt = r["wins_count"]
        formatted.append({
            "executor_contract": r["executor_contract"],
            "wins_count": w_cnt,
            "meaningful_wins_ge5": r["meaningful_wins_ge5"],
            "svr_wins_count": r["svr_wins_count"],
            "open_race_wins_count": r["open_race_wins_count"],
            "svr_ratio": round(r["svr_wins_count"] / w_cnt, 3) if w_cnt else 0.0,
            "total_debt_liquidated_usd": round(r["total_debt_liquidated_usd"], 2),
            "total_gross_bonus_usd": round(r["total_gross_bonus_usd"], 2),
            "chains_active": sorted(r["chains_active"]),
            "pairs_sample": sorted(r["pairs_sample"]),
            "last_seen_utc": r["last_seen_utc"],
        })

    return {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window": win_norm,
        "chain_filter": ch_filter,
        "svr_only": bool(svr_only),
        "total_events_analyzed": total_events,
        "svr_events_count": total_svr,
        "svr_share_pct": round((total_svr / total_events) * 100.0, 2) if total_events else 0.0,
        "total_active_solvers": len(ranked),
        "live_hhi_concentration": round(hhi, 1),
        "solvers_ranked": formatted,
    }


def _normalize_faz2_fire(chain_name: str, ev: Dict[str, Any]) -> Dict[str, Any]:
    t_feed = float(ev.get("t_feed") or 0.0)
    t_karar = float(ev.get("t_karar") or 0.0)
    dec_ms = round(max(0.0, (t_karar - t_feed) * 1000.0), 3) if (t_feed and t_karar) else None
    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_feed)) if t_feed > 0 else None
    return {
        "chain": chain_name,
        "timestamp_utc": ts_iso,
        "t_feed_unix": round(t_feed, 6),
        "sequencer_id": str(ev.get("seq") or ""),
        "oracle_tx": ev.get("oracle_tx"),
        "affected_assets": ev.get("varlik"),
        "price_ratio": ev.get("oran"),
        "borrower": ev.get("kullanici"),
        "hf_before": ev.get("hf_once"),
        "hf_projected": ev.get("hf_tahmin"),
        "debt_usd": round(float(ev.get("borc_usd") or 0.0), 2),
        "decision_latency_ms": dec_ms,
        "snapshot_age_sec": ev.get("foto_yasi_sn"),
    }


def _summarize_faz2_engine(durum: Dict[str, Any]) -> Dict[str, Any]:
    verif = durum.get("ozdogrulama") or {}
    avans = durum.get("avans_ms") or {}
    return {
        "connected": bool(durum.get("baglanti", False)),
        "feed_messages": durum.get("feed_mesaj"),
        "decoded_transactions": durum.get("cozulen_islem"),
        "oracle_price_updates": durum.get("fiyat_guncelleme"),
        "hot_targets_aave_v3": durum.get("sicak_hedef"),
        "snapshot_age_sec": durum.get("snapshot_yasi_sn"),
        "decision_compute_ms": durum.get("karar_hesap_ms"),
        "total_threshold_triggers": durum.get("ateslenirdi"),
        "state_verification": {
            "checked": verif.get("n"),
            "exact_match": verif.get("esit"),
            "mismatch": verif.get("fark"),
        },
        "lead_time_ms": {
            "samples": avans.get("n"),
            "median_ms": avans.get("medyan"),
            "p10_ms": avans.get("p10"),
            "p90_ms": avans.get("p90"),
        } if avans else None,
    }


def load_faz2_leads(
    chain: str = "all",
    limit: int = 50,
    arb_durum_path: str = ARB_FAZ2_DURUM,
    base_durum_path: str = BASE_FAZ2_DURUM,
    arb_fires_path: str = ARB_FAZ2_FIRES,
    base_fires_path: str = BASE_FAZ2_FIRES,
) -> Dict[str, Any]:
    """Returns sub-second oracle price shock telemetry and engine diagnostics across Arbitrum & Base Faz-2."""
    ch = (chain or "all").strip().lower()
    engines: Dict[str, Any] = {}
    events: List[Dict[str, Any]] = []

    if ch in ("all", "arbitrum", "arb"):
        engines["arbitrum"] = _summarize_faz2_engine(_read_json_safe(arb_durum_path, {}))
        for raw in _tail_jsonl(arb_fires_path, max_lines=max(limit, 50)):
            events.append(_normalize_faz2_fire("arbitrum", raw))

    if ch in ("all", "base"):
        engines["base"] = _summarize_faz2_engine(_read_json_safe(base_durum_path, {}))
        for raw in _tail_jsonl(base_fires_path, max_lines=max(limit, 50)):
            events.append(_normalize_faz2_fire("base", raw))

    events.sort(key=lambda e: -float(e.get("t_feed_unix") or 0.0))
    return {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chain_filter": ch,
        "engines": engines,
        "shocks_count": len(events[:limit]),
        "recent_oracle_shocks": events[:limit],
        "stream_endpoint": "GET /v1/radar/stream/oracle-shocks",
    }
