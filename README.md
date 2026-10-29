# Werralem ($WERR)

**Werralem** is the world's first bio-synthetic, neuromorphic, in-consensus oracle blockchain network.

By unifying the **WERR 0-VRAM Fractal Reflex Engine** (arXiv:2609.25498), the **Werralim Living Cell Organism** (FlyWire whole-brain connectome with 158,262 neurons and 3,990,039 synapses), the **Werracle In-Consensus Oracle**, and **Lean4 formally verified mathematics** (81 theorems), Werralem solves the fundamental trilemma of AI on blockchain: zero VRAM consumption, 100% integer EVM parity (Q16.16), and zero-latency biological reflexes.

---

## Repository Structure

```text
werralem/
├── contracts/
│   ├── WerrToken.sol              # 1,000,000,000 $WERR ERC-20 contract (Base L2) with EIP-2612 & ATP Burn
│   ├── interfaces/                # Standard interfaces (IERC20, IERC20Permit, IWerracleOracle)
│   └── test/                      # Smart contract unit tests
├── core/
│   ├── q16_evm_engine.py          # Deterministic Q16.16 EVM fixed-point parity engine
│   └── werracle_connector.py      # Sub-second in-consensus oracle state extractor
├── gateway/
│   └── werr_stake_gate.py         # Stake-to-Access & B2B API billing gateway
├── docs/
│   ├── HARDWARE_STORAGE_ARCHITECTURE.md  # 3-Tier storage plan (RAMDisk, NVMe, 5.4TB HDDs)
│   └── STARTUP_BUSINESS_PLAN_AND_GTM.md  # Go-To-Market, 1B $WERR Tokenomics, Revenue Flywheel
└── scripts/
    └── deploy_base.py             # Deployment and verification script for Base L2
```

---

## Hardware & Tiered Storage Architecture

Werralem runs on an enterprise dual-socket NUMA server with 40 CPU threads, 251 GiB DDR4 RAM, and 5.9 Terabytes of total physical storage:
- **Tier 0 (RAMDisk - `/dev/shm`, 225 GiB Free):** Living cell 8,192 colonies, Q16 lookup tables, live mempool (`<0.5 ms` latency).
- **Tier 1 (PCIe 4.0 NVMe - `/`, 108 GB Free):** Reth/Base execution client, active state trie, API cache.
- **Tier 2 (Bulk HDDs - `/data` & `/werracle_vault`, 2.3 TB Free):** Historical blockchain blocks, Lean4 theorem archives, cold evolutionary snapshots.

---

## Tokenomics ($WERR)

- **Total Max Supply:** `1,000,000,000 WERR` (1 Billion, Fixed)
- **Primary Chain:** Base (Coinbase L2)
- **Token Utility:**
  1. **Gas Currency:** Native execution fee on Werralem App-Rollup.
  2. **Stake-to-Access:** Tiered access to `radar.werracle.com` B2B Institutional APIs (600 - 3,000 req/min).
  3. **Metabolic Burn:** `$WERR` burned on-chain to generate high-priority ATP quota (`burnForATP`).
  4. **Revenue-Backed Buyback & Burn:** 40% of B2B subscription revenues and MEV liquidation profits automatically buy back and burn $WERR on DEXes.

---

## Scientific & Patent Foundations
- **Patent:** TÜRKPATENT National Priority Application TR 2026/016633
- **Mathematics:** 81 Lean4 formally verified theorems (GDT PR #2 Unified Density, Niemeier 24D Moonshine)
- **Neuromorphic Substrate:** Princeton FlyWire whole-brain Drosophila connectome
