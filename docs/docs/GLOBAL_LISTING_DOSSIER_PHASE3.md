# WERREALM ($WERR) — PHASE 3 DEX LIQUIDITY, PRICE DISCOVERY & GLOBAL LISTING DOSSIER
**Network:** Base Mainnet (Chain ID: `8453`)  
**Token Name:** Werrium (`$WERR`)  
**Token Contract:** [`0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2`](https://basescan.org/token/0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2)  
**Governing Institution:** ITOUCH BILISIM SISTEMLERI LTD. STI. (Çukurova University Science Park / Teknokent)  

---

## 1. Base Mainnet DEX Liquidity Architecture (Aerodrome Finance & Uniswap v3)

| Parameter | Value / Address | Verification / Notes |
| :--- | :--- | :--- |
| **Primary DEX** | **Aerodrome Finance (Base #1 DEX)** | Automatic indexing by DexScreener, GeckoTerminal, CoinGecko, CMC & BaseScan |
| **Aerodrome Router** | [`0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43`](https://basescan.org/address/0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43) | Supports atomic `createPool` + `addLiquidity` in a single transaction |
| **Aerodrome PoolFactory** | [`0x420DD381b31aEf6683db6B902084cB0FFECe40Da`](https://basescan.org/address/0x420DD381b31aEf6683db6B902084cB0FFECe40Da) | Standard volatile (`vAMM`) & stable (`sAMM`) pool factory |
| **Deterministic `vAMM-WERR/USDC` Pool** | [`0xdA15b610f7De7A494CD1F7f80B6B73E8b34108A5`](https://basescan.org/address/0xdA15b610f7De7A494CD1F7f80B6B73E8b34108A5) | Verified via `Router.poolFor(WERR, USDC, false, Factory)` |
| **Deterministic `vAMM-WERR/WETH` Pool** | [`0x53D7Ff2ef9B02860bf9F476602832f75594Bfa06`](https://basescan.org/address/0x53D7Ff2ef9B02860bf9F476602832f75594Bfa06) | Verified via `Router.poolFor(WERR, WETH, false, Factory)` |
| **Genesis Reference Rate** | **`$0.001000 USD / WERR`** (`1 USD = 1,000 WERR`) | Implied FDV: **`$1,000,000.00 USD`** |
| **LP Lock Mechanism** | Direct mint to `0x000000000000000000000000000000000000dEaD` or `WerrTreasuryTimelock` (`0x839A6d7E726D60EA2B587e793aE36342297e8C63`) | Earns automatic **100% Liquidity Locked** badge on DexScreener & DEXTools |

---

## 2. Live API Endpoints for CoinGecko, CoinMarketCap & Aggregators

All supply and market telemetry endpoints are live over HTTPS (`CORS: *`, no API key required):

- **Total Supply (Plain Text — CG/CMC Standard):**  
  `https://radar.werracle.com/v1/radar/supply/total` → Returns `1000000000`
- **Effective Circulating Supply (Plain Text — CG/CMC Standard):**  
  `https://radar.werracle.com/v1/radar/supply/circulating` → Returns `999901000`
- **Live Market & DEX Discovery Ticker (JSON):**  
  `https://radar.werracle.com/v1/radar/market/ticker`
- **Live On-Chain Treasury, Safe 2/3 & Timelock Audit (JSON):**  
  `https://radar.werracle.com/v1/radar/treasury/health`

---

## 3. On-Chain Supply & Smart-Contract Lock Proof (98.9501% Locked)

| Holder / Vault | Address | Balance (`$WERR`) | Share (`%`) | Lock / Governance Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sovereign Treasury Safe (2/3 Multi-Sig)** | [`0x7CC5fd367e210F4678Bcfca054cbe0F87291E355`](https://basescan.org/address/0x7CC5fd367e210F4678Bcfca054cbe0F87291E355) | `949,501,000` | `94.9501%` | **2-of-3 Multi-Sig Smart Contract** ([Tx `0x72197374...`](https://basescan.org/tx/0x72197374911008a5d6122543f5f3b1eee5062817e96f1d5eb829d1961e4cb4fe)) |
| **`WerrTreasuryTimelock` (Vesting Vault)** | [`0x839A6d7E726D60EA2B587e793aE36342297e8C63`](https://basescan.org/address/0x839A6d7E726D60EA2B587e793aE36342297e8C63) | `40,000,000` | `4.0000%` | **90-Day Cliff + 24-Month Linear Vesting** ([Tx `0xdae1e4ba...`](https://basescan.org/tx/0xdae1e4bad42417dacef0cd39b3b406d8480eb42f3330791c19e64feed7abccf0)) |
| **Founder Operational & DEX LP Reserve** | [`0x803a439fa8F7cf078302b51111Ae003b5221FC19`](https://basescan.org/address/0x803a439fa8F7cf078302b51111Ae003b5221FC19) | `9,900,000` | `0.9900%` | Reserved for DEX Liquidity Seeding & B2B Reflex Burns |
| **Alpha Liquidator Stakeholder** | [`0xB89AecB2A19CFCc13EE060154A1eAbc42C94485f`](https://basescan.org/address/0xB89AecB2A19CFCc13EE060154A1eAbc42C94485f) | `500,000` | `0.0500%` | Active Institutional `Alpha` Tier Staker |
| **EVM Dead Burn Address** | [`0x000000000000000000000000000000000000dEaD`](https://basescan.org/address/0x000000000000000000000000000000000000dEaD) | `99,000` | `0.0099%` | Permanently Burned ([Tx `0xfa96b3d0...`](https://basescan.org/tx/0xfa96b3d04a2d6e8066abd92345b16c5e5d63bc4539a18cee78f699f265117e68)) |

---

## 4. Anti-Sniping Atomic Launch & Buyback-Burn Execution Commands

1. **Audit DEX Pools & Generate Atomic Calldata:**
   ```bash
   python scripts/dex_liquidity_launcher.py --werr 500000 --usdc 500
   ```
2. **Generate Monthly Surplus Buyback & `burnForReflex(value, queryHash)` Payload:**
   ```bash
   python services/werr_buyback_burn_engine.py
   ```
