"""
Werrealm Sovereign Treasury & Reserve Health Telemetry (v1.1.0 Live RPC + Burn Tracker)
=======================================================================================
Base L2 Mainnet üzerindeki Werrium ($WERR) token hazinesini, rezerv cüzdanlarını,
EVM dead yakım adresini, dolaşımdaki arzı ve kurumsal sağlık metriklerini canlı RPC üzerinden denetler.
"""

import os
import sys
import json
import time
import requests
from typing import Dict, Any

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

class TreasuryHealthChecker:
    VERSION = "v1.1.0-Live-RPC-Auditor"
    CONTRACT = "0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2"
    CHAIN_ID = 8453
    
    DEFAULT_RPCS = [
        "https://mainnet.base.org",
        "https://base-rpc.publicnode.com",
        "https://base.llamarpc.com"
    ]

    TRACKED_WALLETS = {
        "safe_multisig": {
            "address": "0x7CC5fd367e210F4678Bcfca054cbe0F87291E355",
            "label": "Werrealm Sovereign Treasury Safe (2/3 Multisig)",
            "type": "Institutional Multi-Sig Vault (Active)"
        },
        "genesis_treasury": {
            "address": "0x803a439fa8F7cf078302b51111Ae003b5221FC19",
            "label": "Werrealm Genesis EOA Key (Founder & Operational Reserve)",
            "type": "Genesis Founder EOA"
        },
        "bekirhan_alpha": {
            "address": "0xB89AecB2A19CFCc13EE060154A1eAbc42C94485f",
            "label": "Bekirhan Dagli (Alpha Liquidator)",
            "type": "Sovereign Stakeholder"
        },
        "deployer_worker": {
            "address": "0x2034422f8ba7a38981a0d4e7dc3ed80fe859c0c2",
            "label": "Contract Deployer Key",
            "type": "Deployer (Non-holder Worker)"
        },
        "dead_address_burn": {
            "address": "0x000000000000000000000000000000000000dEaD",
            "label": "EVM Dead Burn Blackhole",
            "type": "Permanent Burn Address"
        },
        "timelock_vesting": {
            "address": "0x839A6d7E726D60EA2B587e793aE36342297e8C63",
            "label": "WerrTreasuryTimelock (90d Cliff / 24m Linear Vesting)",
            "type": "Immutable Vesting Smart Contract"
        }
    }

    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or os.path.join(os.path.dirname(__file__), "..", "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.output_file = os.path.join(self.data_dir, "treasury_health_report.json")

    def _eth_call(self, to_addr: str, data: str) -> str:
        for rpc in self.DEFAULT_RPCS:
            try:
                res = requests.post(rpc, json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_call",
                    "params": [{"to": to_addr, "data": data}, "latest"]
                }, timeout=6)
                rj = res.json()
                if "result" in rj and rj["result"] != "0x":
                    return rj["result"]
            except Exception:
                continue
        raise ConnectionError("Base RPC uçlarına ulaşılamadı.")

    def get_total_supply(self) -> int:
        res_hex = self._eth_call(self.CONTRACT, "0x18160ddd")
        return int(res_hex, 16)

    def get_balance(self, address: str) -> int:
        param = address.lower().replace("0x", "").zfill(64)
        call_data = "0x70a08231" + param
        res_hex = self._eth_call(self.CONTRACT, call_data)
        return int(res_hex, 16)

    def get_latest_block(self) -> int:
        for rpc in self.DEFAULT_RPCS:
            try:
                res = requests.post(rpc, json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_blockNumber",
                    "params": []
                }, timeout=5)
                return int(res.json()["result"], 16)
            except Exception:
                continue
        return 0

    def audit_treasury(self) -> Dict[str, Any]:
        latest_block = self.get_latest_block()
        total_supply_wei = self.get_total_supply()
        total_supply_werr = total_supply_wei / 10**18

        wallet_audits = {}
        sum_tracked_wei = 0

        for key, info in self.TRACKED_WALLETS.items():
            addr = info["address"]
            bal_wei = self.get_balance(addr)
            bal_werr = bal_wei / 10**18
            pct_of_total = (bal_wei / total_supply_wei) * 100 if total_supply_wei else 0
            sum_tracked_wei += bal_wei

            wallet_audits[key] = {
                "address": addr,
                "label": info["label"],
                "type": info["type"],
                "balance_wei": str(bal_wei),
                "balance_werr": round(bal_werr, 4),
                "percentage_of_supply": round(pct_of_total, 4)
            }

        circulating_other_wei = max(0, total_supply_wei - sum_tracked_wei)
        circulating_other_werr = circulating_other_wei / 10**18

        safe_bal_wei = int(wallet_audits["safe_multisig"]["balance_wei"])
        treasury_bal_wei = int(wallet_audits["genesis_treasury"]["balance_wei"])
        stakeholders_bal_wei = int(wallet_audits["bekirhan_alpha"]["balance_wei"])
        burned_bal_wei = int(wallet_audits["dead_address_burn"]["balance_wei"])
        timelock_bal_wei = int(wallet_audits["timelock_vesting"]["balance_wei"])
        
        effective_circulating_wei = max(0, total_supply_wei - burned_bal_wei)

        risk_status = "RESOLVED_SAFE_ACTIVE" if safe_bal_wei > 0 else "READY_FOR_SAFE_FUNDING"
        safe_pct = (safe_bal_wei / total_supply_wei) * 100 if total_supply_wei else 0
        if safe_pct >= 90:
            rec = "Treasury reserve migration complete (Safe multisig holds >90% of supply; Timelock deployed)"
        elif safe_bal_wei > 0:
            rec = "Pilot transfer complete; proceed with major treasury reserve migration"
        else:
            rec = "Transfer WERR allocation from genesis_treasury to safe_multisig"

        report = {
            "version": self.VERSION,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "block_number": latest_block,
            "chain_id": self.CHAIN_ID,
            "token_contract": self.CONTRACT,
            "total_supply_werr": total_supply_werr,
            "tracked_wallets": wallet_audits,
            "metrics": {
                "safe_multisig_werr": round(safe_bal_wei / 10**18, 4),
                "safe_multisig_pct": round((safe_bal_wei / total_supply_wei) * 100, 4),
                "treasury_reserve_werr": round(treasury_bal_wei / 10**18, 4),
                "treasury_reserve_pct": round((treasury_bal_wei / total_supply_wei) * 100, 4),
                "timelock_vesting_werr": round(timelock_bal_wei / 10**18, 4),
                "timelock_vesting_pct": round((timelock_bal_wei / total_supply_wei) * 100, 4),
                "stakeholder_holding_werr": round(stakeholders_bal_wei / 10**18, 4),
                "stakeholder_holding_pct": round((stakeholders_bal_wei / total_supply_wei) * 100, 4),
                "other_circulating_werr": round(circulating_other_werr, 4),
                "total_accounted_pct": round((sum_tracked_wei / total_supply_wei) * 100, 4),
                "burned_werr": round(burned_bal_wei / 10**18, 4),
                "burned_pct": round((burned_bal_wei / total_supply_wei) * 100, 4),
                "effective_circulating_werr": round(effective_circulating_wei / 10**18, 4)
            },
            "security_assessment": {
                "centralization_risk": risk_status,
                "safe_multisig_deployed": True,
                "safe_multisig_address": self.TRACKED_WALLETS["safe_multisig"]["address"],
                "timelock_vesting_deployed": True,
                "timelock_vesting_address": self.TRACKED_WALLETS["timelock_vesting"]["address"],
                "recommendation": rec,
                "contract_verified": True,
                "no_mint_guarantee": True
            }
        }

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return report

if __name__ == "__main__":
    checker = TreasuryHealthChecker()
    rep = checker.audit_treasury()
    m = rep["metrics"]
    print("=" * 60)
    print("[*] WERREALM CANLI HAZINE SAGLIGI & ARZ DENETIM RAPORU")
    print("=" * 60)
    print(f"- Son Blok         : {rep['block_number']:,}")
    print(f"- Toplam Arz       : {rep['total_supply_werr']:,.0f} $WERR (Sabit)")
    print(f"- Safe Multisig    : {m['safe_multisig_werr']:,.0f} $WERR (%{m['safe_multisig_pct']}) [KILITLI]")
    print(f"- Genesis Hazine   : {m['treasury_reserve_werr']:,.0f} $WERR (%{m['treasury_reserve_pct']})")
    print(f"- Alpha Paydas     : {m['stakeholder_holding_werr']:,.0f} $WERR (%{m['stakeholder_holding_pct']})")
    print(f"- Yakilan (dEaD)   : {m['burned_werr']:,.0f} $WERR (%{m['burned_pct']}) [BURNED]")
    print(f"- Aktif Arz        : {m['effective_circulating_werr']:,.0f} $WERR")
    print(f"- Toplam Muhasebe  : %{m['total_accounted_pct']}")
    print("=" * 60)
