"""
Werrealm Phase 3 — Autonomous Buyback & On-Chain Reflex Burn Engine (v1.0)
==========================================================================
İşlevi:
1. B2B satış faturaları (Radar DaaS & Answerr API) için deterministik
   `queryHash = keccak256(invoice_id)` üretir ve `WerriumToken.burnForReflex(value, queryHash)`
   zincir üstü yakım çağrısını (`calldata`) hazırlar.
   Not: `burnForReflex()` OpenZeppelin `_burn()` fonksiyonunu çağırarak zincirdeki
   `totalSupply()` değerini doğrudan azaltır ve `AnswerrReflexBurned` event'i yayınlar.
2. Ay sonu net kasa fazlası (`treasury_ledger.json` -> `allocated_burn_reserve_usd`) ile
   Aerodrome Finance (`vAMM-WERR/USDC`) havuzundan otomatik `$WERR` geri alımı (Buyback)
   ve anında yakımı (Burn) döngüsünü hesaplar.
"""

import os
import sys
import json
import time
import requests
from decimal import Decimal
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from services.werr_burn_watcher import keccak_256


class WerrBuybackBurnEngine:
    VERSION = "v1.0.0-Reflex-Buyback-Engine"
    CHAIN_ID = 8453

    WERR_TOKEN = "0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2"
    USDC_TOKEN = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    AERO_ROUTER = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"
    AERO_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"

    # Function Selectors on WerriumToken.sol
    # burnForReflex(uint256 value, bytes32 queryHash)
    SEL_BURN_FOR_REFLEX = "0x" + keccak_256(b"burnForReflex(uint256,bytes32)").hex()[:8]
    # burnForATP(uint256 value)
    SEL_BURN_FOR_ATP = "0x" + keccak_256(b"burnForATP(uint256)").hex()[:8]
    # burn(uint256 value)
    SEL_BURN = "0x42966c68"

    DEFAULT_RPCS = [
        "https://mainnet.base.org",
        "https://base-rpc.publicnode.com",
        "https://base.llamarpc.com"
    ]

    def __init__(self, ledger_path: Optional[str] = None):
        self.ledger_path = ledger_path or os.path.join(
            os.path.dirname(__file__), "..", "data", "treasury_ledger.json"
        )

    @staticmethod
    def compute_invoice_query_hash(invoice_id: str) -> str:
        """Fatura veya referans kimliginden EVM uyumlu 32-byte keccak256 queryHash uretir."""
        clean = str(invoice_id).strip()
        if not clean:
            raise ValueError("Fatura kimligi (invoice_id) bos olamaz.")
        return "0x" + keccak_256(clean.encode("utf-8")).hex()

    def build_reflex_burn_tx(self, werr_amount: float, invoice_id: str) -> Dict[str, Any]:
        """
        WerriumToken.burnForReflex(uint256 value, bytes32 queryHash) islemi icin
        cuzdan/Safe veya otomasyon tarafindan imzalanmaya hazir islem paketi uretir.
        """
        if werr_amount <= 0:
            raise ValueError("Yakilacak WERR miktari sifirdan buyuk olmalidir.")

        werr_wei = int(Decimal(str(werr_amount)) * (10 ** 18))
        query_hash = self.compute_invoice_query_hash(invoice_id)

        calldata = (
            self.SEL_BURN_FOR_REFLEX
            + hex(werr_wei)[2:].zfill(64)
            + query_hash[2:].zfill(64)
        )

        return {
            "contract": self.WERR_TOKEN,
            "chain_id": self.CHAIN_ID,
            "method": "burnForReflex(uint256,bytes32)",
            "selector": self.SEL_BURN_FOR_REFLEX,
            "invoice_id": invoice_id,
            "query_hash_bytes32": query_hash,
            "werr_amount": werr_amount,
            "werr_amount_wei": str(werr_wei),
            "atp_equivalent": werr_wei // (10 ** 9),
            "reduces_onchain_total_supply": True,
            "emits_event": "AnswerrReflexBurned(address,uint256,bytes32)",
            "tx_payload": {
                "to": self.WERR_TOKEN,
                "value": "0x0",
                "data": calldata
            }
        }

    def get_dex_buyback_quote(self, usdc_amount: float) -> Dict[str, Any]:
        """
        Aerodrome Finance uzerinden verilen USDC tutari karsiliginda alinabilecek
        WERR miktarini sorgular (havuz henuz acik degilse Genesis $0.001 referans kurunu kullanir).
        """
        usdc_units = int(round(usdc_amount * 1e6))
        # Router.getAmountsOut(uint256 amountIn, Route[] routes)
        # Route: (address from, address to, bool stable, address factory)
        sel = "0x" + keccak_256(b"getAmountsOut(uint256,(address,address,bool,address)[])").hex()[:8]
        calldata = (
            sel
            + hex(usdc_units)[2:].zfill(64)
            + hex(64)[2:].zfill(64)  # offset to array
            + hex(1)[2:].zfill(64)   # array length = 1
            + self.USDC_TOKEN[2:].lower().zfill(64)
            + self.WERR_TOKEN[2:].lower().zfill(64)
            + ("0" * 64)            # stable = false
            + self.AERO_FACTORY[2:].lower().zfill(64)
        )

        for rpc in self.DEFAULT_RPCS:
            try:
                res = requests.post(rpc, json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_call",
                    "params": [{"to": self.AERO_ROUTER, "data": calldata}, "latest"]
                }, timeout=6).json()
                raw = res.get("result", "0x")
                if raw and raw != "0x" and len(raw) >= 2 + 64 * 4:
                    werr_out_wei = int(raw[-64:], 16)
                    if werr_out_wei > 0:
                        return {
                            "quote_source": "LIVE_AERODROME_ROUTER",
                            "usdc_in": usdc_amount,
                            "expected_werr_out": round(werr_out_wei / 1e18, 4),
                            "expected_werr_out_wei": str(werr_out_wei)
                        }
            except Exception:
                continue

        # Fallback: Genesis Baseline ($1 = 1,000 WERR)
        fallback_werr = round(usdc_amount * 1000.0, 4)
        fallback_wei = int(Decimal(str(fallback_werr)) * (10 ** 18))
        return {
            "quote_source": "GENESIS_BASELINE_1000_WERR_PER_USD",
            "usdc_in": usdc_amount,
            "expected_werr_out": fallback_werr,
            "expected_werr_out_wei": str(fallback_wei)
        }

    def generate_surplus_buyback_report(self) -> Dict[str, Any]:
        """
        treasury_ledger.json dosyasindaki net kasa fazlasini ve gerceklesen yakimlari okuyarak
        kalan yakim kotasini ve `burnForReflex` / DEX Buyback-Burn emrini uretir.
        """
        ledger = {}
        if os.path.exists(self.ledger_path):
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                ledger = json.load(f)

        summary = ledger.get("summary", {})
        flywheel = ledger.get("token_burn_strategy") or ledger.get("token_burn_flywheel", {})
        surplus_usd = float(summary.get("allocated_burn_reserve_usd", flywheel.get("current_surplus_usd", 130.0)))
        target_quota_werr = float(flywheel.get("target_burn_werr_nominal", flywheel.get("estimated_werr_burn_quota", 130000.0)))

        burned_events = flywheel.get("burn_events") or flywheel.get("verified_burn_events", [])
        already_burned_werr = sum(float(e.get("werr_burned", 0.0)) for e in burned_events)
        remaining_quota_werr = max(0.0, target_quota_werr - already_burned_werr)
        remaining_surplus_usd = round(remaining_quota_werr / 1000.0, 2)

        period = ledger.get("fiscal_period", "2026-11")
        ref_invoice = f"SURPLUS-BUYBACK-{period}"
        quote = self.get_dex_buyback_quote(remaining_surplus_usd if remaining_surplus_usd > 0 else surplus_usd)
        burn_tx = self.build_reflex_burn_tx(
            remaining_quota_werr if remaining_quota_werr > 0 else target_quota_werr,
            ref_invoice
        )

        return {
            "version": self.VERSION,
            "fiscal_period": period,
            "allocated_burn_reserve_usd": surplus_usd,
            "target_period_burn_werr": target_quota_werr,
            "already_burned_werr": already_burned_werr,
            "remaining_period_burn_werr": remaining_quota_werr,
            "remaining_surplus_usd": remaining_surplus_usd,
            "dex_buyback_quote": quote,
            "next_reflex_burn_instruction": burn_tx
        }


if __name__ == "__main__":
    engine = WerrBuybackBurnEngine()
    rep = engine.generate_surplus_buyback_report()
    print(json.dumps(rep, indent=2))
