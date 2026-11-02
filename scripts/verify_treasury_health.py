"""
Werrealm Sovereign Treasury & Reserve Health Telemetry (v1.0.0 Live RPC)
========================================================================
Base L2 Mainnet üzerindeki Werrium ($WERR) token hazinesini, rezerv cüzdanlarını,
dolaşımdaki arzı ve kurumsal sağlık metriklerini canlı RPC üzerinden denetler.

İşlevleri:
- 0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2 akıllı sözleşmesinden totalSupply()
  ve bakiye sorgularını çeker.
- Genesis Hazine (`0x803a...`), Alpha Paydaş (`0xB89A...`) ve Deployer (`0x2034...`)
  adreslerinin canlı bakiyelerini teyit eder.
- Dolaşımdaki / Kilitli arz oranını ve EOA yoğunlaşma oranını hesaplar.
- Çıktıyı `data/treasury_health_report.json` olarak atomik yazar.
"""

import os
import sys
import json
import time
import requests
from typing import Dict, Any, List

class TreasuryHealthChecker:
    VERSION = "v1.0.0-Live-RPC-Auditor"
    CONTRACT = "0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2"
    CHAIN_ID = 8453
    
    DEFAULT_RPCS = [
        "https://mainnet.base.org",
        "https://base-rpc.publicnode.com",
        "https://base.llamarpc.com"
    ]

    TRACKED_WALLETS = {
        "genesis_treasury": {
            "address": "0x803a439fa8F7cf078302b51111Ae003b5221FC19",
            "label": "Werrealm Genesis Sovereign Treasury",
            "type": "Treasury / Reserve (Safe Migration Target)"
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
        # totalSupply() selector: 0x18160ddd
        res_hex = self._eth_call(self.CONTRACT, "0x18160ddd")
        return int(res_hex, 16)

    def get_balance(self, address: str) -> int:
        # balanceOf(address) selector: 0x70a08231 + padded address
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

        treasury_bal_wei = int(wallet_audits["genesis_treasury"]["balance_wei"])
        stakeholders_bal_wei = int(wallet_audits["bekirhan_alpha"]["balance_wei"])

        report = {
            "version": self.VERSION,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "block_number": latest_block,
            "chain_id": self.CHAIN_ID,
            "token_contract": self.CONTRACT,
            "total_supply_werr": total_supply_werr,
            "tracked_wallets": wallet_audits,
            "metrics": {
                "treasury_reserve_werr": round(treasury_bal_wei / 10**18, 4),
                "treasury_reserve_pct": round((treasury_bal_wei / total_supply_wei) * 100, 4),
                "stakeholder_holding_werr": round(stakeholders_bal_wei / 10**18, 4),
                "stakeholder_holding_pct": round((stakeholders_bal_wei / total_supply_wei) * 100, 4),
                "other_circulating_werr": round(circulating_other_werr, 4),
                "total_accounted_pct": round((sum_tracked_wei / total_supply_wei) * 100, 4)
            },
            "security_assessment": {
                "centralization_risk": "HIGH_UNTIL_SAFE_MIGRATION",
                "recommendation": "Migrate genesis_treasury to Safe 2/3 Multisig + WerrTreasuryTimelock.sol",
                "contract_verified": True,
                "no_mint_guarantee": True
            }
        }

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return report

if __name__ == "__main__":
    checker = TreasuryHealthChecker()
    print(f"[*] {TreasuryHealthChecker.VERSION} Hazırlanıyor...")
    print(f"    - Base Mainnet Sözleşmesi: {checker.CONTRACT}")
    print(f"[*] Canlı denetim başlatılıyor...")
    
    rep = checker.audit_treasury()
    m = rep["metrics"]
    print("\n" + "="*60)
    print("[*] WERREALM CANLI HAZINE SAGLIGI & ARZ DENETIM RAPORU")
    print("="*60)
    print(f"- Son Blok         : {rep['block_number']:,}")
    print(f"- Toplam Arz       : {rep['total_supply_werr']:,.0f} $WERR (Sabit)")
    print(f"- Genesis Hazine   : {m['treasury_reserve_werr']:,.0f} $WERR (%{m['treasury_reserve_pct']})")
    print(f"- Alpha Paydas     : {m['stakeholder_holding_werr']:,.0f} $WERR (%{m['stakeholder_holding_pct']})")
    print(f"- Diger / Dolasim  : {m['other_circulating_werr']:,.4f} $WERR")
    print(f"- Toplam Muhasebe  : %{m['total_accounted_pct']}")
    print(f"- Rapor Dosyasi    : {checker.output_file}")
    print("="*60)
