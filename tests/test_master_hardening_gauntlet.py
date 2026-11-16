"""
WERREALM & WERRIUM ($WERR) MASTER HARDENING GAUNTLET TEST SUITE
==============================================================
Tüm denetim düzeltmelerini, canlı RPC köprülerini, SSOT konfigürasyonunu
ve akıllı sözleşme bütünlüğünü uçtan uca doğrulayan resmi test bataryası.
"""

import os
import sys
import json
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from gateway.werr_stake_gate import WerrStakeGate
from services.werr_burn_watcher import WerrBurnWatcher, keccak_256
from scripts.verify_treasury_health import TreasuryHealthChecker

class TestWerrealmHardeningGauntlet(unittest.TestCase):

    def test_01_zero_sepolia_leakage(self):
        """Web portalında ve tokenomik sayfalarında eski testnet (Sepolia) kalıntısı olmadığını doğrular."""
        index_html = os.path.join(ROOT_DIR, "docs", "index.html")
        tokenomics_html = os.path.join(ROOT_DIR, "docs", "tokenomics.html")
        
        self.assertTrue(os.path.exists(index_html), "docs/index.html bulunamadi")
        self.assertTrue(os.path.exists(tokenomics_html), "docs/tokenomics.html bulunamadi")

        with open(index_html, "r", encoding="utf-8") as f:
            c1 = f.read()
        with open(tokenomics_html, "r", encoding="utf-8") as f:
            c2 = f.read()

        sepolia_addr = "0xe6ecc9575B4D52642c55FCf64E8E2d3baa6e6EF7"
        self.assertNotIn(sepolia_addr, c1, "index.html icinde Sepolia adresi kalmis!")
        self.assertNotIn(sepolia_addr, c2, "tokenomics.html icinde Sepolia adresi kalmis!")
        self.assertIn("0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2", c1, "index.html ana sozlesme adresini icermiyor!")

    def test_02_ssot_config_consistency(self):
        """radar_b2b_config.json dosyasının tek hakikat kaynağı olduğunu ve oranların doğruluğunu test eder."""
        cfg_path = os.path.join(ROOT_DIR, "staging_answerr", "radar_b2b_config.json")
        self.assertTrue(os.path.exists(cfg_path), "radar_b2b_config.json bulunamadi")

        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        matrix = cfg["werr_stakeholder_matrix"]
        self.assertEqual(matrix["tier_1_sentinel"]["renewal_discount_pct"], 15)
        self.assertEqual(matrix["tier_2_alpha"]["renewal_discount_pct"], 35)
        self.assertEqual(matrix["tier_3_consortium"]["api_fee"], "100% Lifetime Free (While Staked)")
        
        # Institutional rate limit
        self.assertEqual(cfg["pricing"]["institutional"]["rate_limit_per_min"], 3000)

    def test_03_live_onchain_stake_gate(self):
        """Base Mainnet RPC'si üzerinden Bekirhan'ın cüzdanının canlı bakiye ve Alpha tier doğrulamasını test eder."""
        gate = WerrStakeGate()
        bekirhan = "0xB89AecB2A19CFCc13EE060154A1eAbc42C94485f"
        
        res = gate.verify_request(bekirhan, "RADAR_DaaS", "/v1/radar/neural-alpha")
        self.assertTrue(res["allowed"])
        self.assertEqual(res["tier"], "alpha")
        self.assertEqual(res["rate_limit_per_min"], 3000)
        self.assertEqual(res["discount_pct"], 35)
        self.assertGreaterEqual(res["onchain_balance_werr"], 500000.0)
        
        proof = res["werrealm_proof"]
        self.assertTrue(proof["attestation_hash"].startswith("0x"))
        self.assertEqual(len(proof["attestation_hash"]), 66) # 0x + 64 hex

    def test_04_burn_watcher_and_keccak(self):
        """EVM Keccak-256 topic hesaplamasını ve event dinleyicisinin Base RPC taramasını test eder."""
        expected_atp = "0x756c55b8c8e6fb05966eb4510d9f9f7498babd3c45e3fe3c6163f504ca12e47c"
        actual_atp = "0x" + keccak_256(b"ATPBurnInitiated(address,uint256,uint256)").hex()
        self.assertEqual(actual_atp, expected_atp)

        watcher = WerrBurnWatcher()
        latest = watcher.get_latest_block()
        self.assertGreater(latest, 50000000, "Base RPC blok numarasi beklenenden kucuk")

        # Son 20 blok taraması hatasız tamamlanmalı
        events = watcher.scan_burn_events(from_block=latest - 20, to_block=latest)
        self.assertIsInstance(events, list)

    def test_05_live_treasury_health_audit(self):
        """Toplam 1 Milyar arzın Base L2 üzerindeki matematiksel denkliğini teyit eder."""
        checker = TreasuryHealthChecker()
        rep = checker.audit_treasury()

        self.assertEqual(rep["total_supply_werr"], 1000000000.0)
        self.assertEqual(rep["chain_id"], 8453)
        
        m = rep["metrics"]
        # Genesis EOA + Safe Multisig + Dead Burn toplam rezerv denkliği
        total_reserve_and_burned = m["treasury_reserve_werr"] + m.get("timelock_vesting_werr", 0.0) + m["safe_multisig_werr"] + m["burned_werr"]
        self.assertEqual(total_reserve_and_burned, 999500000.0)
        self.assertGreaterEqual(m["safe_multisig_werr"], 900000000.0, "Safe Multisig ana hazine rezervi teyit edilemedi!")
        self.assertGreaterEqual(m["burned_werr"], 99000.0, "Genesis Burn #1 (99,000 WERR) teyit edilemedi!")
        self.assertEqual(m["stakeholder_holding_werr"], 500000.0)
        self.assertEqual(m["total_accounted_pct"], 100.0)

    def test_06_timelock_contract_integrity(self):
        """WerrTreasuryTimelock.sol sözleşmesinin varlığını ve temel vesting fonksiyonlarını doğrular."""
        sol_path = os.path.join(ROOT_DIR, "contracts", "WerrTreasuryTimelock.sol")
        self.assertTrue(os.path.exists(sol_path), "WerrTreasuryTimelock.sol bulunamadi")

        with open(sol_path, "r", encoding="utf-8") as f:
            code = f.read()

        self.assertIn("function vestedAmount()", code)
        self.assertIn("function releasableAmount()", code)
        self.assertIn("function release()", code)
        self.assertIn("cliffDuration", code)
        self.assertIn("vestingDuration", code)

    def test_07_radar_router_endpoints_registered(self):
        """staging_answerr/radar_router.py içinde yeni eklenen denetim uçlarının varlığını teyit eder."""
        router_path = os.path.join(ROOT_DIR, "staging_answerr", "radar_router.py")
        self.assertTrue(os.path.exists(router_path), "radar_router.py bulunamadi")

        with open(router_path, "r", encoding="utf-8") as f:
            code = f.read()

        self.assertIn('@radar_router.get("/stake/status"', code)
        self.assertIn('@radar_router.get("/stake/credits"', code)
        self.assertIn('@radar_router.get("/treasury/health"', code)
        self.assertIn('@radar_router.get("/supply/total"', code)
        self.assertIn('@radar_router.get("/supply/circulating"', code)
        self.assertIn('@radar_router.post("/shield/check"', code)
        self.assertIn('@radar_router.post("/shield/batch"', code)
        self.assertIn('@radar_router.get("/shield/position/{chain}/{address}"', code)
        self.assertIn('@radar_router.get("/opportunities/open-race"', code)
        self.assertIn('@radar_router.get("/solvers/live"', code)
        self.assertIn('@radar_router.get("/telemetry/faz2-leads"', code)
        self.assertIn('@radar_router.get("/stream/oracle-shocks"', code)
        self.assertTrue(os.path.exists(os.path.join(ROOT_DIR, "staging_answerr", "radar_shield.py")))


    def test_08_security_invariants_and_input_sanitization(self):
        """Hex injection, gecersiz EVM adresi reddi, Safe 2/3 esigi ve Permit nonce temizligini dogrular."""
        gate = WerrStakeGate()
        watcher = WerrBurnWatcher()
        for bad_addr in ["0xZZZZ", "0x1234", "'; DROP TABLE werr_burn_events; --", "0x" + "g"*40]:
            with self.assertRaises(ValueError):
                gate.fetch_onchain_balance(bad_addr)
            with self.assertRaises(ValueError):
                watcher.get_user_atp_balance(bad_addr)

        checker = TreasuryHealthChecker()
        rep = checker.audit_treasury()
        sec = rep["security_assessment"]
        self.assertEqual(sec["safe_threshold_verified"], 2)
        self.assertEqual(sec["safe_owners_count"], 3)
        self.assertTrue(sec["permit_nonces_clean"], "Kritik cuzdanlarda beklenmeyen EIP-2612 permit nonce artisi!")
        self.assertGreaterEqual(sec["total_smart_contract_locked_pct"], 98.9)

    def test_09_phase3_dex_and_buyback_burn_engine(self):
        """Phase 3 Aerodrome CREATE2 havuz adreslerini, atomik LP calldata ve burnForReflex motorunu dogrular."""
        from scripts.dex_liquidity_launcher import WerrDexLiquidityLauncher
        from services.werr_buyback_burn_engine import WerrBuybackBurnEngine

        launcher = WerrDexLiquidityLauncher()
        calldata_pkg = launcher.build_atomic_aerodrome_launch_calldata(500000.0, 500.0)
        self.assertEqual(
            calldata_pkg["deterministic_pool_address"].lower(),
            "0xda15b610f7de7a494cd1f7f80b6b73e8b34108a5"
        )
        self.assertEqual(calldata_pkg["implied_werr_price_usd"], 0.001)
        self.assertEqual(len(calldata_pkg["transactions"]), 3)

        engine = WerrBuybackBurnEngine()
        rep = engine.generate_surplus_buyback_report()
        self.assertEqual(rep["already_burned_werr"], 99000.0)
        self.assertEqual(rep["remaining_period_burn_werr"], 1000.0)
        self.assertEqual(rep["next_reflex_burn_instruction"]["selector"], "0x828d7c72")
        self.assertEqual(
            rep["next_reflex_burn_instruction"]["werr_amount_wei"],
            "1000000000000000000000"
        )

    def test_10_faz_b_shield_and_phase3_unit(self):
        """Faz-B Anti-Liquidation Shield hesaplama ve pre-flight karar mantigini dogrular."""
        sys.path.insert(0, os.path.join(ROOT_DIR, "staging_answerr"))
        import radar_shield

        sample = [{
            "chain": "base",
            "protocol": "Morpho Blue",
            "market_id": "0x" + "1" * 64,
            "market_pair": "WETH/USDC",
            "health_factor": 1.30,
            "debt_usd": 1000.0,
            "collateral_usd": 1500.0,
            "lltv": 0.86,
        }]
        res_pass = radar_shield.evaluate_preflight_check(
            address="0x" + "a" * 40,
            chain="base",
            action="preflight",
            delta_debt_usd=0.0,
            min_safe_hf=1.15,
            shock_pct=10.0,
            use_graphql=False,
            positions_override=sample,
        )
        self.assertIn(res_pass["verdict"], ("PASS", "WARN"))

        res_block = radar_shield.evaluate_preflight_check(
            address="0x" + "a" * 40,
            chain="base",
            action="borrow",
            delta_debt_usd=350.0,
            min_safe_hf=1.15,
            shock_pct=10.0,
            tier="pro",
            use_graphql=False,
            positions_override=sample,
        )
        self.assertEqual(res_block["verdict"], "BLOCK")
        self.assertIn("rescue_targets", res_block)

if __name__ == "__main__":
    unittest.main(verbosity=2)

