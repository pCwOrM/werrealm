"""
Werracle B2B DaaS Authentication, Multi-Pay Checkout & Key Management Module
Handles API Key issuance, SHA-256 hashing, SQLite storage, sliding window rate limiting,
Multi-Chain Crypto verification (Base USDC, TRON TRC20 USDT, Ethereum/Arbitrum/BSC USDT & USDC,
Binance SAPI Deposit History reconciliation), and iyzico 3D Secure Credit Card checkout.
"""

import os
import sys
import time
import json
import hmac
import base64
import secrets
import hashlib
import sqlite3
import urllib.parse
import urllib.request
import urllib.error
import requests
from typing import Optional, Dict, Any, List

DB_PATH = "/var/lib/werracle-health/werracle_api_keys.db"
CONFIG_PATH = "/opt/apps/answerr/api/radar_b2b_config.json"

DEFAULT_CONFIG = {
    "usdc_deposit_address": "0x4945ef6e124eea2176ddf050b33db42b0ae8c7f7",
    "trc20_usdt_deposit_address": "TLMhaDJTVYBHBSGJ9nCQGLvqnYFPsBgLJu",
    "payments_enabled": True,
    "max_payment_age_days": 7,
    "usdc_contract_base": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "usdt_contract_tron": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "network": "base_mainnet",
    "chain_id": 8453,
    "base_rpcs": [
        "https://mainnet.base.org",
        "https://base-rpc.publicnode.com"
    ],
    "evm_networks": {
        "base": {
            "name": "Base Mainnet",
            "chain_id": 8453,
            "rpcs": ["https://mainnet.base.org", "https://base-rpc.publicnode.com"],
            "tokens": {
                "USDC": {"address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "decimals": 6},
                "USDT": {"address": "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2", "decimals": 6}
            }
        },
        "ethereum": {
            "name": "Ethereum Mainnet (ERC20)",
            "chain_id": 1,
            "rpcs": ["https://ethereum-rpc.publicnode.com", "https://rpc.ankr.com/eth"],
            "tokens": {
                "USDC": {"address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "decimals": 6},
                "USDT": {"address": "0xdac17f958d2ee523a2206206994597c13d831ec7", "decimals": 6}
            }
        },
        "arbitrum": {
            "name": "Arbitrum One",
            "chain_id": 42161,
            "rpcs": ["https://arb1.arbitrum.io/rpc", "https://arbitrum-one-rpc.publicnode.com"],
            "tokens": {
                "USDC": {"address": "0xaf88d065e77c8cc2239327c5edb3a432268e5831", "decimals": 6},
                "USDT": {"address": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", "decimals": 6}
            }
        },
        "bsc": {
            "name": "BNB Smart Chain (BEP20)",
            "chain_id": 56,
            "rpcs": ["https://bsc-dataseed.binance.org", "https://bsc-rpc.publicnode.com"],
            "tokens": {
                "USDC": {"address": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", "decimals": 18},
                "USDT": {"address": "0x55d398326f99059ff775485246999027b3197955", "decimals": 18}
            }
        }
    },
    "pricing": {
        "developer": {
            "name": "Developer & Algorithmic Builder",
            "amount_usdc": 99.0,
            "amount_try_net": 4100.0,
            "amount_try_vat": 0.0,
            "amount_try_total": 4100.0,
            "vat_rate": 0.0,
            "vat_exemption": "0% KDV (4691 s. TGB Kanunu & 3065 s. KDV Kanunu Geçici 20/1 Teknopark Ar-Ge Yazılım İstisnası)",
            "duration_days": 30,
            "rate_limit_per_min": 300,
            "quota_decisions": 250000,
            "features": [
                "250.000 Karar / Sorgu Aylık Kota (300 req/dk)",
                "Morpho Blue & Aave v3 Canlı Pozisyonlar (/v1/radar/hot-positions)",
                "Chainlink SVR Solver Marj & Teklif Analitiği (/v1/radar/solvers)",
                "Standart 50ms REST API Gateway Erişimi",
                "Resmi e-Arşiv Uyumlu Onaylı PDF Ticari Fatura (%0 KDV)"
            ]
        },
        "pro": {
            "name": "Pro Searcher & High-Frequency Arbiter",
            "amount_usdc": 199.0,
            "amount_try_net": 8250.0,
            "amount_try_vat": 0.0,
            "amount_try_total": 8250.0,
            "vat_rate": 0.0,
            "vat_exemption": "0% KDV (4691 s. TGB Kanunu & 3065 s. KDV Kanunu Geçici 20/1 Teknopark Ar-Ge Yazılım İstisnası)",
            "duration_days": 30,
            "rate_limit_per_min": 1200,
            "quota_decisions": "Unlimited",
            "features": [
                "1.200 req/dakika Özel Ayrılmış Kapasite (Aylık Sınırsız İstek)",
                "Rezonans Filtreli Kritik Tasfiyeler (/v1/radar/hot-positions?filter=resonance)",
                "Çift Zincirli Canlı Gözlem (Base L2 Flashblocks + Arbitrum One Sequencer)",
                "İşlem Başına OEV Analitiği ve Tarihsel Veri Seti (/v1/radar/oev-analytics)",
                "25ms Optimize Bellek İçi RAMDisk Gecikmesi",
                "Özel Webhook & Telegram/Discord Sinyal Boru Hattı"
            ]
        },
        "institutional": {
            "name": "Institutional Sovereign Syndicate & Curator Feed",
            "amount_usdc": 499.0,
            "amount_try_net": 20700.0,
            "amount_try_vat": 0.0,
            "amount_try_total": 20700.0,
            "vat_rate": 0.0,
            "vat_exemption": "0% KDV (4691 s. TGB Kanunu & 3065 s. KDV Kanunu Geçici 20/1 Teknopark Ar-Ge Yazılım İstisnası)",
            "duration_days": 30,
            "rate_limit_per_min": 3000,
            "quota_decisions": "Unlimited Bare-Metal",
            "features": [
                "3.000 req/dakika Özel Çıplak Donanım (Bare-Metal) Kapasitesi",
                "Milisaniyelik Neural-Alpha Sinyal Beslemesi (/v1/radar/neural-alpha)",
                "Üç Zincirli Tam Kapsam: Base L2 + Arbitrum One + Ethereum L1 (Reth Yerel Düğüm)",
                "MetaMorpho Kasa Stres Simülasyon Motoru (/v1/radar/curator/{vault})",
                "SLA Garantili Sub-15ms Yanıt & %99.99 Kesintisiz Çalışma Taahhüdü",
                "Otomatik Resmi Ticari PDF Faturalandırma & Kurumsal Destek Masası"
            ]
        }
    },
    "bank_accounts": {
        "bank_name": "TEB (Türk Ekonomi Bankası A.Ş.) — Adana Toros Şubesi (446)",
        "account_holder": "ITOUCH BİLİŞİM SİSTEMLERİ MÜHENDİSLİK DANIŞMANLIK SANAYİ VE TİCARET LİMİTED ŞİRKETİ",
        "customer_no": "23764109",
        "swift_bic": "TEBUTRIS",
        "iban_try": "TR920003200000000070575465",
        "iban_usd": "TR830003200000000088946748",
        "iban_eur": "TR280003200000000088946768"
    }
}

# 28 Oct 2026 (external audit): signed invoice links, TRON recipient check, key e-mail
INVOICE_SECRET_PATH = os.path.join(os.path.dirname(DB_PATH), "radar_invoice_link.secret")
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _invoice_secret() -> bytes:
    try:
        with open(INVOICE_SECRET_PATH, "rb") as f:
            s = f.read().strip()
            if len(s) >= 32:
                return s
    except FileNotFoundError:
        pass
    s = secrets.token_hex(32).encode()
    os.makedirs(os.path.dirname(INVOICE_SECRET_PATH), exist_ok=True)
    fd = os.open(INVOICE_SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(s)
    return s


def invoice_token(ref: str) -> str:
    return hmac.new(_invoice_secret(), (ref or "").strip().lower().encode(), hashlib.sha256).hexdigest()[:32]


def invoice_url(ref: str) -> str:
    """Link handed to the buyer only (claim response, callback page, e-mail)."""
    return f"https://radar.werracle.com/v1/radar/invoice/{ref}.pdf?t={invoice_token(ref)}"


def check_invoice_token(ref: str, token: str) -> bool:
    return bool(token) and hmac.compare_digest(invoice_token(ref), token.strip().lower())


def admin_wire_approve_token(ref: str) -> str:
    return hmac.new(_invoice_secret(), f"admin_wire_approve:{ref.strip().lower()}".encode(), hashlib.sha256).hexdigest()[:32]


def check_admin_wire_approve_token(ref: str, token: str) -> bool:
    return bool(token) and hmac.compare_digest(admin_wire_approve_token(ref), token.strip().lower())


def tron_to_hex20(addr: str) -> str:
    """Base58Check TRON address -> 20-byte hex (as TronGrid reports Transfer 'to')."""
    n = 0
    for ch in (addr or "").strip():
        n = n * 58 + _B58.index(ch)
    raw = n.to_bytes(25, "big")
    payload, chk = raw[:-4], raw[-4:]
    if hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] != chk or payload[0] != 0x41:
        raise ValueError("invalid TRON address")
    return payload[1:].hex()


def _mask_email(e: str) -> str:
    e = (e or "").strip()
    if "@" not in e:
        return ""
    u, d = e.split("@", 1)
    return (u[:2] + "***@" + d) if len(u) > 2 else ("***@" + d)


def send_key_email(email: str, tier: str, api_key: str, invoice_no: str, ref: str, expires_utc: str, method: str) -> bool:
    """Deliver the API key + signed invoice link by e-mail (the success page shows the key only once). Never raises."""
    email = (email or "").strip()
    if "@" not in email:
        return False
    try:
        import smtplib, ssl
        from email.mime.text import MIMEText
        creds_path = "/opt/apps/werracle/reporting/mail_creds.json"
        with open(creds_path) as f:
            creds = json.load(f)
        link = invoice_url(ref)
        body = f"""Werracle Radar API — {tier.upper()} aboneliğiniz aktif / your subscription is active

API anahtarınız / Your API key:
{api_key}

Fatura / Receipt: {invoice_no}
PDF: {link}
Ödeme yöntemi / Payment method: {method}
Bitiş / Expires: {expires_utc}

Kullanım / Usage:
curl -H "X-API-Key: {api_key}" https://radar.werracle.com/v1/radar/hot-positions

Bu anahtar size özeldir; paylaşmayın. Keep this key private.
Docs: https://radar.werracle.com/docs · Destek / Support: contact@werracle.com

ITouch Bilişim Sistemleri Ltd. Şti. · Çukurova Üniversitesi Teknokent, Adana
"""
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"Werracle Radar API key — {tier.upper()} ({invoice_no})"
        msg["From"] = f"Werracle Radar <{creds['from_addr']}>"
        msg["To"] = email
        msg["Bcc"] = "ask@answerr.me"
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(creds["smtp_host"], creds["smtp_port"], context=ctx, timeout=15) as s:
            s.login(creds["smtp_user"], creds["smtp_pass"])
            s.sendmail(creds["from_addr"], [email, "ask@answerr.me"], msg.as_string())
        return True
    except Exception as e:
        print("[radar_auth] key e-mail failed:", e, file=sys.stderr)
        return False


# In-memory validation cache (TTL 60s)
_KEY_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_EXPIRY: Dict[str, float] = {}
_RATE_LIMIT_COUNTERS: Dict[str, Dict[int, int]] = {}


def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                merged = {**DEFAULT_CONFIG, **cfg}
                for t_k, t_v in DEFAULT_CONFIG["pricing"].items():
                    if t_k in merged.get("pricing", {}):
                        merged["pricing"][t_k] = {**t_v, **merged["pricing"][t_k]}
                return merged
        except Exception:
            pass
    return {**DEFAULT_CONFIG, "payments_enabled": False}


def claim_message(tx_hash: str, tier: str, email: str) -> str:
    """Exact text the payer signs (EIP-191 personal_sign) to bind a self-custody payment to this claim."""
    return ("Werracle Radar API key claim\n"
            f"tx: {tx_hash.strip().lower()}\n"
            f"tier: {tier.strip().lower()}\n"
            f"email: {(email or '').strip().lower()}")


def _rpc(rpcs, method, params):
    for rpc in rpcs:
        try:
            r = requests.post(rpc, json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                              headers={"User-Agent": "WerracleRadar/2.2"}, timeout=8)
            data = r.json()
            if data.get("result") is not None:
                return data["result"]
        except Exception:
            continue
    return None


def _signature_matches(payer: str, message: str, signature: str, rpcs) -> bool:
    """EOA (ecrecover) or smart-contract wallet (EIP-1271 isValidSignature)."""
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
        if Account.recover_message(encode_defunct(text=message), signature=signature).lower() == payer.lower():
            return True
    except Exception:
        pass
    try:  # EIP-1271
        from eth_account.messages import _hash_eip191_message, encode_defunct
        h = _hash_eip191_message(encode_defunct(text=message)).hex().removeprefix("0x")
        sig = signature.lower().removeprefix("0x")
        data = ("0x1626ba7e" + h.rjust(64, "0") + "40".rjust(64, "0") + hex(len(sig) // 2)[2:].rjust(64, "0")
                + sig.ljust(((len(sig) + 63) // 64) * 64, "0"))
        res = _rpc(rpcs, "eth_call", [{"to": payer, "data": data}, "latest"])
        return bool(res) and res.lower().startswith("0x1626ba7e")
    except Exception:
        return False


def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_db(db_path: str = DB_PATH):
    conn = get_db_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_hash TEXT PRIMARY KEY,
                key_prefix TEXT NOT NULL,
                tier TEXT NOT NULL,
                email TEXT,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                rate_limit_per_min INTEGER NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 0,
                last_used_at REAL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                tx_hash TEXT PRIMARY KEY,
                payer_address TEXT NOT NULL,
                amount_usdc REAL NOT NULL,
                tier TEXT NOT NULL,
                claimed_at REAL NOT NULL,
                key_hash TEXT NOT NULL,
                verified_on_chain INTEGER NOT NULL DEFAULT 1,
                binance_synced INTEGER NOT NULL DEFAULT 0,
                network TEXT DEFAULT 'base_mainnet',
                currency TEXT DEFAULT 'USDC',
                payment_method TEXT DEFAULT 'On-Chain Crypto',
                billing_json TEXT DEFAULT '{}',
                invoice_no TEXT DEFAULT '',
                key_prefix TEXT DEFAULT '',
                raw_api_key TEXT DEFAULT '',
                FOREIGN KEY (key_hash) REFERENCES api_keys(key_hash)
            );
        """)
        # Safe alter table for existing DBs
        for col, ctype in [
            ("network", "TEXT DEFAULT 'base_mainnet'"),
            ("currency", "TEXT DEFAULT 'USDC'"),
            ("payment_method", "TEXT DEFAULT 'On-Chain Crypto'"),
            ("billing_json", "TEXT DEFAULT '{}'"),
            ("invoice_no", "TEXT DEFAULT ''"),
            ("key_prefix", "TEXT DEFAULT ''"),
            ("raw_api_key", "TEXT DEFAULT ''")
        ]:
            try:
                conn.execute(f"ALTER TABLE payments ADD COLUMN {col} {ctype};")
            except Exception:
                pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS card_checkouts (
                basket_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                token TEXT DEFAULT '',
                tier TEXT NOT NULL,
                email TEXT NOT NULL,
                net_try REAL NOT NULL,
                vat_try REAL NOT NULL,
                total_try REAL NOT NULL,
                billing_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'initiated',
                created_at REAL NOT NULL,
                paid_at REAL,
                payment_id TEXT DEFAULT '',
                card_last4 TEXT DEFAULT '',
                key_hash TEXT DEFAULT '',
                raw_api_key TEXT DEFAULT '',
                invoice_no TEXT DEFAULT ''
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS crypto_orders (
                order_id TEXT PRIMARY KEY,
                tier TEXT NOT NULL,
                email TEXT NOT NULL,
                network TEXT NOT NULL,
                token TEXT NOT NULL,
                exact_amount REAL NOT NULL,
                deposit_address TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                tx_hash TEXT DEFAULT '',
                billing_json TEXT DEFAULT '{}'
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crypto_orders_email ON crypto_orders(email);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crypto_orders_amt ON crypto_orders(exact_amount, status);")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                key_hash TEXT NOT NULL,
                minute_bucket INTEGER NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (key_hash, minute_bucket)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_tier ON api_keys(tier);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_expires ON api_keys(expires_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_bucket ON rate_limits(minute_bucket);")
    conn.close()


# Ensure DB schema is initialized on import
try:
    init_db()
except Exception:
    pass


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def generate_api_key(tier: str = "pro", email: str = "", days: int = 30, db_path: str = DB_PATH) -> Dict[str, Any]:
    cfg = load_config()
    tier_info = cfg.get("pricing", {}).get(tier.lower(), cfg["pricing"]["pro"])

    prefix = f"wrk_{tier[:4]}_live_"
    random_token = secrets.token_hex(20)
    raw_key = f"{prefix}{random_token}"
    k_hash = hash_key(raw_key)

    now = time.time()
    expires_at = now + (days * 86400.0)
    rate_limit = tier_info.get("rate_limit_per_min", 600)

    conn = get_db_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO api_keys (
                key_hash, key_prefix, tier, email, created_at, expires_at, status, rate_limit_per_min, request_count
            ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, 0)
        """, (k_hash, prefix, tier.lower(), email, now, expires_at, rate_limit))
    conn.close()

    _KEY_CACHE[k_hash] = {
        "key_hash": k_hash,
        "tier": tier.lower(),
        "email": email,
        "expires_at": expires_at,
        "status": "active",
        "rate_limit_per_min": rate_limit
    }
    _CACHE_EXPIRY[k_hash] = now + 60.0

    return {
        "api_key": raw_key,
        "key_hash": k_hash,
        "key_prefix": f"{prefix}{random_token[:6]}...{random_token[-4:]}",
        "tier": tier.lower(),
        "email": email,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "expires_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_at)),
        "expires_at": expires_at,
        "rate_limit_per_min": rate_limit
    }


def authenticate_key(raw_key: Optional[str], db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    if not raw_key:
        return None
    raw_key = raw_key.strip()
    if raw_key.startswith("Bearer "):
        raw_key = raw_key[7:].strip()
    if not raw_key.startswith("wrk_"):
        return None

    k_hash = hash_key(raw_key)
    now = time.time()

    cached = _KEY_CACHE.get(k_hash)
    if cached and now < _CACHE_EXPIRY.get(k_hash, 0):
        if cached["status"] == "active" and now < cached["expires_at"]:
            return cached
        return None

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys WHERE key_hash = ?", (k_hash,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    data = dict(row)
    if data["status"] != "active" or now >= data["expires_at"]:
        return None

    _KEY_CACHE[k_hash] = {
        "key_hash": k_hash,
        "tier": data["tier"],
        "email": data["email"],
        "expires_at": data["expires_at"],
        "status": data["status"],
        "rate_limit_per_min": data["rate_limit_per_min"]
    }
    _CACHE_EXPIRY[k_hash] = now + 60.0
    return _KEY_CACHE[k_hash]


def check_rate_limit(key_hash: str, limit_per_min: int, db_path: str = DB_PATH) -> bool:
    now_min = int(time.time() // 60)
    try:
        conn = get_db_connection(db_path)
        with conn:
            cursor = conn.execute("""
                INSERT INTO rate_limits (key_hash, minute_bucket, request_count)
                VALUES (?, ?, 1)
                ON CONFLICT(key_hash, minute_bucket) DO UPDATE SET request_count = request_count + 1
                RETURNING request_count;
            """, (key_hash, now_min))
            row = cursor.fetchone()
            current_count = row[0] if row else 1
            if now_min % 5 == 0:
                conn.execute("DELETE FROM rate_limits WHERE minute_bucket < ?", (now_min - 5,))
        conn.close()
        return current_count <= limit_per_min
    except Exception:
        counters = _RATE_LIMIT_COUNTERS.setdefault(key_hash, {})
        old_buckets = [b for b in counters if b < now_min - 2]
        for b in old_buckets:
            del counters[b]
        current_count = counters.get(now_min, 0)
        if current_count >= limit_per_min:
            return False
        counters[now_min] = current_count + 1
        return True


def _check_binance_deposit_by_txid(cfg: Dict[str, Any], tx_hash: str, required_amount: float) -> Optional[Dict[str, Any]]:
    """Checks Binance SAPI deposit history for USDC or USDT matching tx_hash."""
    ak = cfg.get("binance_api_key")
    sk = cfg.get("binance_api_secret")
    if not ak or not sk:
        return None
    tx_clean = tx_hash.strip().lower().removeprefix("0x")
    for coin in ["USDC", "USDT"]:
        try:
            ts = int(time.time() * 1000)
            q = urllib.parse.urlencode({"coin": coin, "timestamp": ts, "recvWindow": 10000})
            sig = hmac.new(sk.encode("utf-8"), q.encode("utf-8"), hashlib.sha256).hexdigest()
            url = f"https://api.binance.com/sapi/v1/capital/deposit/hisrec?{q}&signature={sig}"
            req = urllib.request.Request(url, headers={"X-MBX-APIKEY": ak, "User-Agent": "WerracleRadar/2.2"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                deposits = json.loads(resp.read().decode())
                for dep in deposits:
                    d_tx = str(dep.get("txId", "")).strip().lower().removeprefix("0x")
                    # Sometimes Binance prefixes or suffixes internal info, check substring match on 64-hex
                    if tx_clean and len(tx_clean) >= 60 and tx_clean in d_tx:
                        amt = float(dep.get("amount", 0))
                        status = int(dep.get("status", 0))
                        ins = float(dep.get("insertTime", 0)) / 1000.0
                        if ins and time.time() - ins > float(cfg.get("max_payment_age_days", 7)) * 86400.0:
                            continue
                        if status in (1, 6) and amt >= required_amount - 1.0:  # allow $1 network fee tolerance on CEX withdrawals
                            return {
                                "verified": True,
                                "coin": coin,
                                "amount": amt,
                                "network": dep.get("network", "BINANCE"),
                                "payer": dep.get("sourceAddress") or "Binance Verified Deposit",
                                "binance_synced": 1
                            }
        except Exception:
            continue
    return None


def _verify_trc20_usdt_onchain(tx_hash: str, expected_recipient: str, required_amount: float, max_age_days: float = 7.0) -> Optional[Dict[str, Any]]:
    """Verifies a TRON TRC20 USDT transfer via TronGrid API."""
    tx_clean = tx_hash.strip().removeprefix("0x")
    if len(tx_clean) != 64:
        return None
    try:
        want_to = tron_to_hex20(expected_recipient)
    except Exception:
        return None  # no valid treasury configured -> never accept
    try:
        url = f"https://api.trongrid.io/v1/transactions/{tx_clean}/events?only_confirmed=true"
        r = requests.get(url, headers={"User-Agent": "WerracleRadar/2.2"}, timeout=8)
        if r.status_code == 200:
            data = r.json()
            for ev in data.get("data", []):
                if ev.get("event_name") == "Transfer" and ev.get("contract_address") == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t":
                    blk_ts = float(ev.get("block_timestamp", 0)) / 1000.0
                    if blk_ts > 0 and (time.time() - blk_ts) > max_age_days * 86400.0:
                        continue
                    res = ev.get("result", {})
                    to_hex = str(res.get("to", "")).lower().removeprefix("0x")
                    if to_hex[-40:] != want_to:
                        continue  # 28 Oct 2026: transfers to other addresses were accepted before
                    val = float(res.get("value", 0)) / 1e6
                    if val >= required_amount - 1.0:
                        return {
                            "verified": True,
                            "coin": "USDT",
                            "amount": val,
                            "network": "tron_trc20",
                            "payer": res.get("from", "TRON TRC20 Sender"),
                            "binance_synced": 0
                        }
    except Exception:
        pass
    return None



def create_crypto_order(
    tier: str,
    email: str,
    network: str = "trc20",
    token: str = "USDT",
    billing: Optional[Dict[str, Any]] = None,
    db_path: str = DB_PATH,
    client_ip: str = ""
) -> Dict[str, Any]:
    """Assigns a unique fractional amount to the buyer (e.g. 149.37 USDT), preventing any front-running."""
    init_db(db_path)
    cfg = load_config()
    tier = (tier or "pro").strip().lower()
    if tier not in cfg.get("pricing", {}):
        tier = "pro"
    tier_info = cfg["pricing"][tier]
    base_amt = float(tier_info["amount_usdc"])

    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"success": False, "error": "A valid billing email is required to register a unique crypto payment order."}

    net_key = (network or "trc20").strip().lower()
    if net_key in ("trc20", "tron", "trx"):
        deposit_addr = cfg.get("trc20_usdt_deposit_address", "TLMhaDJTVYBHBSGJ9nCQGLvqnYFPsBgLJu")
        settled_token = "USDT"
    else:
        deposit_addr = cfg.get("usdc_deposit_address", "0x4945ef6e124eea2176ddf050b33db42b0ae8c7f7")
        settled_token = (token or "USDC").upper()

    now = time.time()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM crypto_orders 
        WHERE email = ? AND tier = ? AND status = 'pending' AND expires_at > ?
        ORDER BY created_at DESC LIMIT 1
    """, (email, tier, now))
    existing = cursor.fetchone()
    if existing:
        ex = dict(existing)
        conn.close()
        return {
            "success": True,
            "order_id": ex["order_id"],
            "tier": ex["tier"],
            "email": ex["email"],
            "exact_amount": ex["exact_amount"],
            "token": ex["token"],
            "network": ex["network"],
            "deposit_address": ex["deposit_address"],
            "expires_in_minutes": max(1, int((ex["expires_at"] - now) / 60)),
            "instructions": f"Send exactly {ex['exact_amount']:.2f} {ex['token']} to bind this payment exclusively to {email}."
        }

    # 28 Oct 2026: at most 3 open orders per client IP (an attacker could otherwise reserve every amount slot
    # with throw-away e-mails and block real buyers for 2 h); amounts never repeat while an order is open.
    try:
        conn.execute("ALTER TABLE crypto_orders ADD COLUMN client_ip TEXT DEFAULT ''")
    except Exception:
        pass
    if client_ip:
        cursor.execute("SELECT count(*) FROM crypto_orders WHERE client_ip = ? AND status = 'pending' AND expires_at > ?", (client_ip, now))
        if cursor.fetchone()[0] >= 3:
            conn.close()
            return {"success": False, "error": "Too many open payment orders from this connection. Use an existing order or try again later."}
    cursor.execute("SELECT exact_amount FROM crypto_orders WHERE deposit_address = ? AND status = 'pending' AND expires_at > ?", (deposit_addr, now))
    used_amts = {round(row[0], 2) for row in cursor.fetchall()}
    free = [c for c in range(1, 100) if round(base_amt + c / 100.0, 2) not in used_amts]
    if not free:
        conn.close()
        return {"success": False, "error": "All unique payment amounts are reserved right now. Please try again in a few minutes, or pay by card / bank wire."}
    seed = int(hashlib.sha256(f"{email}-{now}".encode()).hexdigest()[:6], 16)
    cents = free[seed % len(free)]
    candidate = round(base_amt + (cents / 100.0), 2)

    h_tag = hashlib.sha256(f"{email}-{candidate}".encode()).hexdigest()[:6].upper()
    order_id = f"ORD-{int(now)}-{h_tag}"
    expires_at = now + 7200.0
    b_json = json.dumps(billing or {}, ensure_ascii=False)

    cursor.execute("""
        INSERT INTO crypto_orders (order_id, tier, email, network, token, exact_amount, deposit_address, created_at, expires_at, status, billing_json, client_ip)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
    """, (order_id, tier, email, net_key, settled_token, candidate, deposit_addr, now, expires_at, b_json, client_ip or ""))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "order_id": order_id,
        "tier": tier,
        "email": email,
        "exact_amount": candidate,
        "token": settled_token,
        "network": net_key,
        "deposit_address": deposit_addr,
        "expires_in_minutes": 120,
        "instructions": f"Send exactly {candidate:.2f} {settled_token} to bind this payment exclusively to {email}."
    }


def verify_base_usdc_payment(
    tx_hash: str,
    target_tier: str,
    email: str = "",
    signature: str = "",
    network: str = "base",
    token: str = "USDC",
    billing: Optional[Dict[str, Any]] = None,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    init_db(db_path)
    tx_hash_raw = tx_hash.strip()
    net_key = (network or "base").strip().lower()
    if net_key in ("trc20", "tron", "trx"):
        tx_hash = tx_hash_raw.lower().removeprefix("0x")
        if len(tx_hash) != 64:
            return {"success": False, "error": "Invalid TRON TRC20 tx_hash format (must be 64 hex characters)."}
    else:
        tx_hash = tx_hash_raw.lower()
        if not tx_hash.startswith("0x") or len(tx_hash) != 66:
            return {"success": False, "error": "Invalid EVM tx_hash format (must be 0x followed by 64 hex characters)."}

    cfg = load_config()
    if not cfg.get("payments_enabled", True) or not cfg.get("usdc_deposit_address"):
        return {"success": False, "error": "Self-serve payments are currently disabled. Contact sales: contact@werracle.com"}

    target_tier = target_tier.lower()
    if target_tier not in cfg["pricing"]:
        return {"success": False, "error": "Invalid tier requested. Choose 'pro' or 'institutional'."}

    tier_info = cfg["pricing"][target_tier]
    required_usdc = float(tier_info["amount_usdc"])

    # 1. Replay prevention check
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE lower(tx_hash) = ?", (tx_hash.lower(),))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        ex_dict = dict(existing)
        inv_no = ex_dict.get("invoice_no") or f"INV-2026-{hashlib.sha256(tx_hash.encode()).hexdigest()[:8].upper()}"
        return {
            "success": False,
            "error": f"Transaction {tx_hash} has already been claimed for an API Key.",
            "invoice_no": inv_no,
            "invoice_pdf_url": None
        }

    verified_transfer = False
    payer_address = None
    transferred_usdc = 0.0
    settled_coin = (token or "USDC").upper()
    settled_network = net_key
    binance_synced = 0

    # 2A. Check TRON TRC20 if network is trc20/tron
    if net_key in ("trc20", "tron", "trx"):
        trc_res = _verify_trc20_usdt_onchain(tx_hash, cfg.get("trc20_usdt_deposit_address", ""), required_usdc, float(cfg.get("max_payment_age_days", 7)))
        if not trc_res:
            trc_res = _check_binance_deposit_by_txid(cfg, tx_hash, required_usdc)
        if not trc_res:
            conn.close()
            return {
                "success": False,
                "error": f"No confirmed TRC20 USDT deposit of >= {required_usdc} USDT found for tx {tx_hash} yet. Please wait 1-2 minutes for TRON confirmation and retry."
            }
        verified_transfer = True
        payer_address = trc_res["payer"]
        transferred_usdc = trc_res["amount"]
        settled_coin = trc_res["coin"]
        settled_network = "tron_trc20"
        binance_synced = trc_res.get("binance_synced", 0)
    else:
        # 2B. EVM Networks (base, ethereum, arbitrum, bsc)
        evm_nets = cfg.get("evm_networks", DEFAULT_CONFIG["evm_networks"])
        net_cfg = evm_nets.get(net_key, evm_nets["base"])
        rpcs = net_cfg.get("rpcs", cfg.get("base_rpcs", DEFAULT_CONFIG["base_rpcs"]))
        deposit_recipient = cfg["usdc_deposit_address"].lower()

        receipt = _rpc(rpcs, "eth_getTransactionReceipt", [tx_hash])
        if not receipt:
            # Fallback: check Binance deposit history directly
            bin_res = _check_binance_deposit_by_txid(cfg, tx_hash, required_usdc)
            if bin_res:
                verified_transfer = True
                payer_address = bin_res["payer"]
                transferred_usdc = bin_res["amount"]
                settled_coin = bin_res["coin"]
                settled_network = bin_res["network"]
                binance_synced = 1
            else:
                conn.close()
                return {"success": False, "error": f"Transaction receipt not found on {net_cfg['name']}. Ensure tx is confirmed."}
        else:
            if receipt.get("status") != "0x1":
                conn.close()
                return {"success": False, "error": "Transaction failed or reverted on-chain."}

            blk = _rpc(rpcs, "eth_getBlockByNumber", [receipt.get("blockNumber"), False])
            max_age = float(cfg.get("max_payment_age_days", 7)) * 86400.0
            if not blk or time.time() - int(blk["timestamp"], 16) > max_age:
                conn.close()
                return {"success": False, "error": f"Payment is older than {cfg.get('max_payment_age_days', 7)} days. Contact sales: contact@werracle.com"}

            TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
            accepted_tokens = net_cfg.get("tokens", {"USDC": {"address": cfg["usdc_contract_base"].lower(), "decimals": 6}})
            token_map = {v["address"].lower(): (k, v["decimals"]) for k, v in accepted_tokens.items()}

            for l in receipt.get("logs", []):
                contract_addr = l.get("address", "").lower()
                if contract_addr not in token_map:
                    continue
                t_sym, t_dec = token_map[contract_addr]
                topics = l.get("topics", [])
                if len(topics) >= 3 and topics[0].lower() == TRANSFER_TOPIC:
                    from_addr = "0x" + topics[1][-40:].lower()
                    to_addr = "0x" + topics[2][-40:].lower()
                    raw_val = int(l.get("data", "0x0"), 16)
                    val_usd = raw_val / (10 ** t_dec)
                    if to_addr == deposit_recipient and (payer_address is None or from_addr == payer_address):
                        payer_address = from_addr
                        transferred_usdc += val_usd
                        settled_coin = t_sym
                        settled_network = net_cfg["name"]
                        if transferred_usdc >= required_usdc - 1.0:
                            verified_transfer = True

            if not verified_transfer:
                conn.close()
                return {
                    "success": False,
                    "error": f"No matching USDC/USDT transfer of >= {required_usdc} found to deposit address {deposit_recipient}. Detected: {transferred_usdc:.2f}."
                }

            # Check signature OR Binance deposit match
            if signature:
                if not _signature_matches(payer_address, claim_message(tx_hash, target_tier, email), signature, rpcs):
                    conn.close()
                    return {
                        "success": False,
                        "error": "Signature does not match the paying address.",
                        "sign_this_message": claim_message(tx_hash, target_tier, email),
                        "payer_address": payer_address
                    }
            else:
                # Check if Binance SAPI already sees this deposit (allows exchange withdrawals without signature)
                bin_res = _check_binance_deposit_by_txid(cfg, tx_hash, required_usdc)
                if bin_res:
                    binance_synced = 1
                else:
                    conn.close()
                    return {
                        "success": False,
                        "error": "signature required",
                        "sign_this_message": claim_message(tx_hash, target_tier, email),
                        "payer_address": payer_address,
                        "how": "Sign the exact message with the wallet that sent the USDC/USDT (personal_sign / EIP-191) and resend with 'signature'."
                    }

    
    # 28 Oct 2026 (external audit): e-mail is checked BEFORE an order is consumed (an empty-e-mail claim used to
    # mark the buyer's order as claimed without issuing a key), and payments without a wallet signature
    # (TRON / exchange withdrawals) must match a unique-amount order registered to the same e-mail.
    if not email or "@" not in email:
        conn.close()
        return {"success": False, "error": "A billing e-mail is required: your API key and receipt are sent there."}
    cursor.execute("""
        SELECT * FROM crypto_orders
        WHERE status = 'pending' AND abs(exact_amount - ?) < 0.005 AND expires_at > ?
        ORDER BY created_at DESC LIMIT 1
    """, (transferred_usdc, time.time() - 86400.0))
    matching_ord = cursor.fetchone()
    if matching_ord:
        ord_d = dict(matching_ord)
        if (ord_d.get("email") or "").strip().lower() != email.strip().lower():
            conn.close()
            return {
                "success": False,
                "error": f"This payment of {transferred_usdc:.2f} {settled_coin} was registered for a different account ({_mask_email(ord_d['email'])}). Front-running is blocked."
            }
        cursor.execute("UPDATE crypto_orders SET status = 'claimed', tx_hash = ? WHERE order_id = ?", (tx_hash, ord_d["order_id"]))
        conn.commit()
    elif not signature:
        conn.close()
        return {
            "success": False,
            "error": ("This payment has no wallet signature and does not match a payment order. Create an order first "
                      "(it gives you a unique amount such as 149.37), send exactly that amount, then claim with the same e-mail. "
                      "Already paid without an order? Contact contact@werracle.com with the transaction hash.")
        }

    # 3. Generate and store API key + Invoice Metadata
    if not email or "@" not in email:
        conn.close()
        return {"success": False, "error": "A billing e-mail is required: your API key and receipt are sent there."}
    key_info = generate_api_key(tier=target_tier, email=email, days=30, db_path=db_path)
    now = time.time()
    inv_no = f"INV-{time.strftime('%Y', time.gmtime(now))}-{hashlib.sha256(tx_hash.encode()).hexdigest()[:8].upper()}"
    billing_str = json.dumps(billing or {}, ensure_ascii=False)

    with conn:
        conn.execute("""
            INSERT INTO payments (
                tx_hash, payer_address, amount_usdc, tier, claimed_at, key_hash, verified_on_chain, binance_synced,
                network, currency, payment_method, billing_json, invoice_no, key_prefix, raw_api_key
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_hash, payer_address, transferred_usdc, target_tier, now, key_info["key_hash"], binance_synced,
            settled_network, settled_coin, f"On-Chain Crypto ({settled_network})", billing_str, inv_no,
            key_info["key_prefix"], ""
        ))
    conn.close()
    mailed = send_key_email(email, target_tier, key_info["api_key"], inv_no, tx_hash, key_info["expires_at_utc"],
                            f"{settled_coin} on {settled_network}")

    return {
        "success": True,
        "message": f"Payment of {transferred_usdc:.2f} {settled_coin} on {settled_network} verified successfully!",
        "tier": target_tier,
        "api_key": key_info["api_key"],
        "rate_limit_per_min": key_info["rate_limit_per_min"],
        "expires_at_utc": key_info["expires_at_utc"],
        "invoice_no": inv_no,
        "invoice_pdf_url": invoice_url(tx_hash),
        "key_emailed_to": _mask_email(email) if mailed else None,
        "instructions": "Pass header 'X-API-Key: wrk_...' or 'Authorization: Bearer wrk_...' with your requests."
    }


# ==============================================================================
# IYZICO 3D SECURE CREDIT CARD CHECKOUT FOR RADAR.WERRACLE.COM
# ==============================================================================

def _iyzico_headers(api_key: str, secret_key: str, uri_path: str, body: str) -> Dict[str, str]:
    rnd = f"{int(time.time() * 1000)}{secrets.randbelow(10 ** 9)}"
    sig = hmac.new(secret_key.encode("utf-8"), (rnd + uri_path + body).encode("utf-8"), hashlib.sha256).hexdigest()
    token = base64.b64encode(f"apiKey:{api_key}&randomKey:{rnd}&signature:{sig}".encode("utf-8")).decode("utf-8")
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "WerracleRadar-Billing/2.2",
        "Authorization": "IYZWSv2 " + token,
        "x-iyzi-rnd": rnd
    }


def _iyzico_post(cfg: Dict[str, Any], path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    iyz = cfg.get("iyzico", {})
    ak = iyz.get("api_key", "")
    sk = iyz.get("secret_key", "")
    base_url = iyz.get("base_url", "https://api.iyzipay.com").rstrip("/")
    if not ak or not sk:
        return {"status": "failure", "errorMessage": "iyzico merchant credentials not configured."}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    headers = _iyzico_headers(ak, sk, path, body)
    req = urllib.request.Request(base_url + path, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"status": "failure", "errorMessage": f"HTTP {e.code}"}
    except Exception as e:
        return {"status": "failure", "errorMessage": str(e)}


def init_iyzico_card_checkout(tier: str, billing: Dict[str, Any], client_ip: str = "127.0.0.1", locale: str = "tr", db_path: str = DB_PATH) -> Dict[str, Any]:
    init_db(db_path)
    cfg = load_config()
    tier = (tier or "pro").lower()
    if tier not in cfg["pricing"]:
        return {"success": False, "error": "Invalid tier. Choose 'pro' or 'institutional'."}

    p_info = cfg["pricing"][tier]
    net_try = float(p_info.get("amount_try_net", 5190.0 if tier == "pro" else 17390.0))
    vat_try = 0.0
    total_try = net_try
    total_str = f"{total_try:.2f}"

    email = (billing.get("email") or "").strip()
    legal_name = (billing.get("company") or billing.get("legal_name") or "").strip()
    contact_name = (billing.get("contact_name") or legal_name).strip()
    # iyzico requires these buyer fields; placeholders are used only in the iyzico request, never on the invoice
    tax_id = (billing.get("tax_id") or "11111111111").strip()
    address = (billing.get("address") or "Not provided").strip()
    city = (billing.get("city") or "Not provided").strip()
    country = (billing.get("country") or "Türkiye").strip()
    phone = "".join(ch for ch in (billing.get("phone") or "+908503115203") if ch.isdigit() or ch == "+")
    if not phone.startswith("+"):
        phone = "+90" + phone.lstrip("0")

    if not email or "@" not in email or not legal_name:
        return {"success": False, "error": "Please provide your Company/Full Name and Email address for the invoice."}

    parts = contact_name.split()
    first, last = (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else (contact_name, "Customer")
    digits = "".join(ch for ch in tax_id if ch.isdigit())
    identity = digits if len(digits) == 11 else "11111111111"

    basket_id = f"WRK-{int(time.time())}-{secrets.token_hex(4).upper()}"
    conv_id = f"CONV-{basket_id}"
    item_name = f"Werracle B2B Risk Radar API — {p_info['name']} (30 Gün)"

    payload = {
        "locale": "en" if locale == "en" else "tr",
        "conversationId": conv_id,
        "price": total_str,
        "paidPrice": total_str,
        "currency": "TRY",
        "basketId": basket_id,
        "paymentGroup": "PRODUCT",
        "callbackUrl": "https://radar.werracle.com/v1/radar/auth/iyzico/callback",
        "enabledInstallments": [1],
        "buyer": {
            "id": basket_id,
            "name": first[:60],
            "surname": last[:60],
            "identityNumber": identity,
            "email": email[:100],
            "gsmNumber": phone[:20],
            "registrationAddress": address[:200],
            "city": city[:60],
            "country": country[:60],
            "ip": client_ip or "127.0.0.1"
        },
        "billingAddress": {
            "contactName": legal_name[:100],
            "address": address[:200],
            "city": city[:60],
            "country": country[:60]
        },
        "basketItems": [
            {
                "id": f"werracle_{tier}",
                "name": item_name[:100],
                "category1": "Yazılım",
                "category2": "B2B DaaS API Abonelik",
                "itemType": "VIRTUAL",
                "price": total_str
            }
        ]
    }

    res = _iyzico_post(cfg, "/payment/iyzipos/checkoutform/initialize/auth/ecom", payload)
    if res.get("status") != "success" or not res.get("token") or not res.get("paymentPageUrl"):
        return {
            "success": False,
            "error": f"iyzico payment initialization failed: {res.get('errorMessage') or 'unknown error'}"
        }

    conn = get_db_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO card_checkouts (
                basket_id, conversation_id, token, tier, email, net_try, vat_try, total_try, billing_json, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'initiated', ?)
        """, (
            basket_id, conv_id, res["token"], tier, email, net_try, vat_try, total_try,
            json.dumps(billing, ensure_ascii=False), time.time()
        ))
    conn.close()

    return {
        "success": True,
        "provider": "iyzico",
        "basket_id": basket_id,
        "payment_page_url": res["paymentPageUrl"],
        "net_try": net_try,
        "vat_try": vat_try,
        "total_try": total_try,
        "currency": "TRY"
    }


def settle_iyzico_card_callback(token: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    init_db(db_path)
    token = (token or "").strip()
    if not token:
        return {"success": False, "error": "Missing token"}

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM card_checkouts WHERE token = ?", (token,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "Checkout session not found"}

    chk = dict(row)
    if chk["status"] == "paid":
        conn.close()
        return {  # key is shown once and e-mailed; a replayed callback never reveals it again
            "success": True,
            "already_paid": True,
            "basket_id": chk["basket_id"],
            "tier": chk["tier"],
            "key_emailed_to": _mask_email(chk["email"]),
            "invoice_no": chk["invoice_no"],
            "invoice_pdf_url": invoice_url(chk["basket_id"])
        }

    cfg = load_config()
    res = _iyzico_post(cfg, "/payment/iyzipos/checkoutform/auth/ecom/detail", {
        "locale": "tr",
        "token": token,
        "conversationId": chk["conversation_id"]
    })

    if res.get("status") != "success" or (res.get("paymentStatus") or "").upper() != "SUCCESS":
        with conn:
            conn.execute("UPDATE card_checkouts SET status = 'failed' WHERE basket_id = ?", (chk["basket_id"],))
        conn.close()
        return {"success": False, "error": res.get("errorMessage") or "Card payment was not approved."}
    # 28 Oct 2026: bind the result to this checkout (amount, currency, basket) and require fraud approval
    try:
        paid = float(res.get("paidPrice") or res.get("price") or 0)
    except (TypeError, ValueError):
        paid = 0.0
    problems = []
    if abs(paid - float(chk["total_try"])) > 0.01:
        problems.append(f"amount {paid} != {chk['total_try']}")
    if (res.get("currency") or "TRY").upper() != "TRY":
        problems.append("currency")
    if res.get("basketId") and res.get("basketId") != chk["basket_id"]:
        problems.append("basket")
    if str(res.get("fraudStatus", "1")) != "1":
        problems.append(f"fraudStatus={res.get('fraudStatus')}")
    if problems:
        with conn:
            conn.execute("UPDATE card_checkouts SET status = 'review' WHERE basket_id = ?", (chk["basket_id"],))
        conn.close()
        print(f"[radar_auth] card checkout {chk['basket_id']} held for review: {problems}", file=sys.stderr)
        return {"success": False, "error": "Your payment was received and is under review. We will e-mail your API key once it is approved (usually within one business day). Reference: " + chk["basket_id"]}

    # Issue API key & record payment
    key_info = generate_api_key(tier=chk["tier"], email=chk["email"], days=30, db_path=db_path)
    now = time.time()
    inv_no = f"INV-{time.strftime('%Y', time.gmtime(now))}-{chk['basket_id'][-8:]}"
    pay_id = str(res.get("paymentId") or chk["basket_id"])
    last4 = str(res.get("lastFourDigits") or "****")

    with conn:
        conn.execute("""
            UPDATE card_checkouts
            SET status = 'paid', paid_at = ?, payment_id = ?, card_last4 = ?, key_hash = ?, raw_api_key = ?, invoice_no = ?
            WHERE basket_id = ?
        """, (now, pay_id, last4, key_info["key_hash"], "", inv_no, chk["basket_id"]))

        conn.execute("""
            INSERT OR REPLACE INTO payments (
                tx_hash, payer_address, amount_usdc, tier, claimed_at, key_hash, verified_on_chain, binance_synced,
                network, currency, payment_method, billing_json, invoice_no, key_prefix, raw_api_key
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 'iyzico_card', 'TRY', ?, ?, ?, ?, ?)
        """, (
            chk["basket_id"], f"Card **** {last4} (iyzico #{pay_id})", chk["total_try"], chk["tier"], now,
            key_info["key_hash"], f"iyzico 3D Secure Card (**** {last4})", chk["billing_json"], inv_no,
            key_info["key_prefix"], ""
        ))
    conn.close()
    mailed = send_key_email(chk["email"], chk["tier"], key_info["api_key"], inv_no, chk["basket_id"],
                            key_info["expires_at_utc"], f"Card **** {last4} (iyzico)")

    return {
        "success": True,
        "basket_id": chk["basket_id"],
        "tier": chk["tier"],
        "email": chk["email"],
        "api_key": key_info["api_key"],
        "rate_limit_per_min": key_info["rate_limit_per_min"],
        "expires_at_utc": key_info["expires_at_utc"],
        "invoice_no": inv_no,
        "key_emailed_to": _mask_email(chk["email"]) if mailed else None,
        "invoice_pdf_url": invoice_url(chk["basket_id"])
    }



def dispatch_wire_created_notifications(ref_id: str, inv_no: str, tier: str, amt: float, curr: str, iban: str, billing: Dict[str, Any]) -> None:
    """Dispatches instant email alert to operations desk and customer proforma notification."""
    try:
        import smtplib, ssl
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        creds_path = "/opt/apps/werracle/reporting/mail_creds.json"
        if not os.path.exists(creds_path):
            return
        with open(creds_path) as f:
            creds = json.load(f)

        buyer_name = billing.get("company") or billing.get("legal_name") or "Değerli Müşteri"
        buyer_email = (billing.get("email") or "").strip()
        tax_id = billing.get("tax_id") or "-"
        phone = billing.get("phone") or "-"
        pdf_url = invoice_url(ref_id)

        approve_tok = admin_wire_approve_token(ref_id)
        approve_link = f"https://radar.werracle.com/v1/radar/auth/admin-approve-wire?ref={ref_id}&t={approve_tok}"

        # 1. Admin Alert to pcworm@pcworm.net (Executive 1-Click Approval)
        admin_subject = f"[RADAR HAVALE TALEP] {buyer_name} — {amt} {curr} ({inv_no})"
        admin_text = f"""Yeni Banka Havalesi / EFT Başvurusu Alındı:

Fatura No       : {inv_no}
Referans Kodu   : {ref_id}
Alıcı Kurum/Kişi: {buyer_name}
E-Posta         : {buyer_email}
Vergi No / TC   : {tax_id}
Telefon         : {phone}
Paket           : {tier.upper()}
Tutar           : {amt} {curr}
Banka Hesabı    : {iban}

Proforma Fatura PDF: {pdf_url}

======================================================================
👉 HAVALE HESABA GELDİĞİNDE TEK TIKLA ONAYLAYIP ANAHTARI GÖNDERMEK İÇİN:
{approve_link}

(Bu bağlantıya tıkladığınızda:
 1. Fatura resmi olarak ÖDENDİ (INV-...) statüsüne geçer.
 2. 30 Kasım 2026'ya kadar geçerli (29-31 Ekim Hediye) API anahtarı üretilir.
 3. Müşteriye resmi faturası ve API anahtarı otomatik mail olarak teslim edilir.)
======================================================================

Alternatif Sunucu Komutu:
python3 /opt/apps/answerr/api/confirm_wire_payment.py --ref {ref_id}
"""
        msg_admin = MIMEText(admin_text, "plain", "utf-8")
        msg_admin["Subject"] = admin_subject
        msg_admin["From"] = f"Werracle Radar Alert <{creds['from_addr']}>"
        msg_admin["To"] = "pcworm@pcworm.net"

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(creds["smtp_host"], creds["smtp_port"], context=ctx, timeout=15) as s:
            s.login(creds["smtp_user"], creds["smtp_pass"])
            s.sendmail(creds["from_addr"], ["pcworm@pcworm.net"], msg_admin.as_string())

            # 2. Customer Notification (if valid email)
            if buyer_email and "@" in buyer_email:
                cust_subject = f"Werracle Risk Radar & OEV DaaS API — Proforma Faturanız ({inv_no})"
                cust_text = f"""Sayın {buyer_name},

Werracle Risk Radar & OEV DaaS API ({tier.upper()} Tier) için banka havalesi (EFT/Havale) talebiniz alınmış ve Proforma Faturanız oluşturulmuştur.

ÖDEME DETAYLARI:
--------------------------------------------------
Proforma Fatura No : {inv_no}
Ödeme Referans Kodu: {ref_id}
Tutar              : {amt:.2f} {curr} (KDV İstisnası: 3065 s. KDV Kanunu Geçici 20/1 md. %0 KDV)
Banka Hesabı       : {iban}

Proforma Fatura PDF: {pdf_url}

ÖNEMLİ: Lütfen banka transferinizin açıklama alanına '{ref_id}' referans kodunu yazınız.
Ödemeniz TEB hesabımıza ulaştığında API erişim anahtarınız ve onaylı faturanız anında e-posta ile tarafınıza iletilecektir.

Saygılarımızla,
ITouch Bilişim Sistemleri Ltd. Şti. · Çukurova Teknokent
Werracle Destek Ekibi: contact@werracle.com
"""
                msg_cust = MIMEText(cust_text, "plain", "utf-8")
                msg_cust["Subject"] = cust_subject
                msg_cust["From"] = f"Werracle & ITouch Systems <{creds['from_addr']}>"
                msg_cust["To"] = buyer_email
                s.sendmail(creds["from_addr"], [buyer_email], msg_cust.as_string())
    except Exception as e:
        print("[radar_auth] Wire email notification dispatch failed:", e, file=sys.stderr)


def approve_wire_transfer(ref: str, tier: Optional[str] = None, credits: int = 250000, expires_timestamp: Optional[int] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Admin wire approval: stamps invoice PAID, generates API key valid until 30 Nov 2026, and emails client."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE lower(tx_hash) = ? OR lower(invoice_no) = ?", (ref.strip().lower(), ref.strip().lower()))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": f"Banka havalesi kaydı bulunamadı: '{ref}'"}

    p = dict(row)
    if p.get("verified_on_chain"):
        conn.close()
        return {
            "success": True,
            "already_paid": True,
            "invoice_no": p.get("invoice_no"),
            "key_prefix": p.get("key_prefix"),
            "pdf_url": invoice_url(p["tx_hash"]),
            "email": json.loads(p.get("billing_json") or "{}").get("email", ""),
            "tier": p.get("tier"),
            "message": "Bu havale faturası daha önce zaten onaylanmış ve API anahtarı teslim edilmiş."
        }

    billing = {}
    try:
        billing = json.loads(p.get("billing_json") or "{}")
    except Exception:
        pass

    email = (billing.get("email") or "customer@example.com").strip()
    assigned_tier = (tier or p.get("tier") or "pro").lower()
    
    # 30 November 2026 23:59:59 UTC
    default_nov_end = 1796083199
    exp_time = expires_timestamp or default_nov_end
    days_left = max(1, int((exp_time - time.time()) / 86400))

    key_info = generate_api_key(tier=assigned_tier, email=email, days=days_left, db_path=db_path)
    api_key = key_info["api_key"]
    k_hash = key_info["key_hash"]
    k_prefix = key_info["key_prefix"]

    old_inv = p.get("invoice_no") or ""
    new_inv = old_inv.replace("PRO-", "INV-") if "PRO-" in old_inv else old_inv
    now = time.time()

    with conn:
        conn.execute("UPDATE api_keys SET expires_at = ? WHERE key_hash = ?", (exp_time, k_hash))
        conn.execute("""
            UPDATE payments
            SET verified_on_chain = 1,
                binance_synced = 1,
                key_hash = ?,
                key_prefix = ?,
                invoice_no = ?,
                claimed_at = ?
            WHERE tx_hash = ?
        """, (k_hash, k_prefix, new_inv, now, p["tx_hash"]))
    conn.close()

    mailed = send_key_email(email, assigned_tier, api_key, new_inv, p["tx_hash"],
                            key_info["expires_at_utc"], p.get("payment_method") or "Bank Wire / EFT (TEB)")

    return {
        "success": True,
        "already_paid": False,
        "ref": p["tx_hash"],
        "invoice_no": new_inv,
        "email": email,
        "tier": assigned_tier,
        "api_key": api_key,
        "key_prefix": k_prefix,
        "expires_utc": key_info["expires_at_utc"],
        "mailed": mailed,
        "pdf_url": invoice_url(p["tx_hash"])
    }


def create_bank_transfer_invoice(tier: str, currency: str, billing: Dict[str, Any], wire_ref: str = "", db_path: str = DB_PATH) -> Dict[str, Any]:
    """Creates an UNPAID (Proforma / Pending Wire) Commercial Invoice record in SQLite so the buyer can download an official UNPAID PDF invoice and pay via TEB IBAN."""
    init_db(db_path)
    cfg = load_config()
    tier = (tier or "developer").lower()
    if tier not in cfg["pricing"]:
        return {"success": False, "error": f"Invalid tier '{tier}'. Choose 'developer', 'pro' or 'institutional'."}
    if not (billing.get("company") or "").strip() or "@" not in (billing.get("email") or ""):
        return {"success": False, "error": "Please provide your Company/Full Name and a valid e-mail address for the invoice."}
    curr = (currency or "TRY").upper()
    if curr not in ("TRY", "USD", "EUR"):
        curr = "TRY"
    p_info = cfg["pricing"][tier]
    if curr == "TRY":
        amt = float(p_info.get("amount_try_net", 4100.0 if tier == "developer" else (8250.0 if tier == "pro" else 20700.0)))
        iban = "TR92 0003 2000 0000 0070 5754 65 (TEB TRY)"
    elif curr == "EUR":
        amt = 95.0 if tier == "developer" else (185.0 if tier == "pro" else 465.0)
        iban = "TR28 0003 2000 0000 0088 9467 68 (TEB EUR)"
    else:
        amt = float(p_info.get("amount_usdc", 99.0 if tier == "developer" else (199.0 if tier == "pro" else 499.0)))
        iban = "TR83 0003 2000 0000 0088 9467 48 (TEB USD)"

    now = time.time()
    ref_id = f"WIRE-{int(now)}-{secrets.token_hex(3).upper()}"
    inv_no = f"PRO-{time.strftime('%Y', time.gmtime(now))}-{ref_id[-6:]}"
    conn = get_db_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO payments (
                tx_hash, payer_address, amount_usdc, tier, claimed_at, key_hash, verified_on_chain, binance_synced,
                network, currency, payment_method, billing_json, invoice_no, key_prefix, raw_api_key
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 'bank_wire_teb', ?, ?, ?, ?, 'PENDING_WIRE_VERIFICATION', '')
        """, (
            ref_id,
            wire_ref or (billing.get("company") or "Bank Wire Transfer"),
            amt,
            tier,
            now,
            f"pending_{ref_id}",
            curr,
            f"Bank Wire / EFT ({iban})",
            json.dumps(billing, ensure_ascii=False),
            inv_no
        ))
    conn.close()
    dispatch_wire_created_notifications(ref_id, inv_no, tier, amt, curr, iban, billing)
    return {
        "success": True,
        "status": "unpaid",
        "reference": ref_id,
        "invoice_no": inv_no,
        "tier": tier,
        "amount": amt,
        "currency": curr,
        "bank_iban": iban,
        "invoice_pdf_url": invoice_url(ref_id),
        "message": "Unpaid (Proforma) Commercial Invoice generated. Once your TEB wire transfer is verified, your invoice status updates to PAID and your API key is activated."
    }


def get_payment_for_invoice(payment_ref: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    init_db(db_path)
    ref = (payment_ref or "").strip().removesuffix(".pdf")
    if ref.lower() in ("sample", "sample-unpaid", "proforma"):
        now = time.time()
        is_unpaid_sample = ref.lower() in ("sample-unpaid", "proforma")
        return {
            "status": "unpaid" if is_unpaid_sample else "paid",
            "tx_hash": "WIRE-PENDING-TEB-446" if is_unpaid_sample else "0x8f94e2c7d3b109a4e6c218d5b049f1a2c3d4e5f60718293a4b5c6d7e8f901234",
            "payer_address": "Bank Wire / EFT Transfer (Awaiting Confirmation)" if is_unpaid_sample else "0x71C...89A (Verified Institutional Subscriber)",
            "amount_usdc": 149.00,
            "net_amount": 149.00,
            "vat_amount": 0.00,
            "tier": "pro",
            "claimed_at": now,
            "expires_at": now + 30 * 86400,
            "network": "TEB Bank Wire (SWIFT: TEBUTRIS)" if is_unpaid_sample else "Base Mainnet (Chain ID 8453)",
            "currency": "USD" if is_unpaid_sample else "USDC",
            "payment_method": "Bank Wire / EFT (TEB USD IBAN)" if is_unpaid_sample else "On-Chain Crypto (Base Mainnet USDC)",
            "recipient_address": "TR83 0003 2000 0000 0088 9467 48 (TEB USD)" if is_unpaid_sample else "0x4945ef6e124eea2176ddf050b33db42b0ae8c7f7 (Base Treasury)",
            "invoice_no": f"PRO-{time.strftime('%Y', time.gmtime(now))}-SAMPLE" if is_unpaid_sample else f"INV-{time.strftime('%Y', time.gmtime(now))}-SAMPLE01",
            "key_prefix": "PENDING_WIRE_VERIFICATION" if is_unpaid_sample else "wrk_pro_live_sample***",
            "rate_limit_per_min": 600,
            "billing": {
                "company": "SAMPLE — Example Customer Ltd. (illustrative)",
                "contact_name": "Risk & Treasury Operations Desk",
                "tax_id": "SAMPLE-0000",
                "address": "Example Street 1, Example City (sample)",
                "email": "billing@example.com"
            }
        }

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE lower(tx_hash) = ? OR lower(invoice_no) = ?", (ref.lower(), ref.lower()))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    p = dict(row)
    cursor.execute("SELECT * FROM api_keys WHERE key_hash = ?", (p["key_hash"],))
    k_row = cursor.fetchone()
    conn.close()

    k_dict = dict(k_row) if k_row else {}
    billing = {}
    try:
        billing = json.loads(p.get("billing_json") or "{}")
    except Exception:
        pass

    curr = p.get("currency") or "USDC"
    amt = float(p.get("amount_usdc") or 149.0)
    net_amt = amt
    vat_amt = 0.0
    is_paid = bool(p.get("verified_on_chain", 1))
    if "bank_wire" in str(p.get("network", "")).lower():
        recip = "TEB (Adana Toros Şb. 446, SWIFT: TEBUTRIS) — Beneficiary: ITOUCH BILISIM SISTEMLERI LTD. STI."
    elif curr == "TRY":
        recip = "ITouch Bilişim Sistemleri Ltd. Şti. — iyzico Merchant #276514"
    else:
        recip = (
            "TLMhaDJTVYBHBSGJ9nCQGLvqnYFPsBgLJu (TRON TRC20 Treasury)"
            if "trc20" in str(p.get("network", "")).lower()
            else "0x4945ef6e124eea2176ddf050b33db42b0ae8c7f7 (EVM Treasury)"
        )

    return {
        "status": "paid" if is_paid else "unpaid",
        "tx_hash": p["tx_hash"],
        "payer_address": p["payer_address"],
        "amount_usdc": amt,
        "net_amount": net_amt,
        "vat_amount": vat_amt,
        "tier": p["tier"],
        "claimed_at": p["claimed_at"],
        "expires_at": k_dict.get("expires_at") or (p["claimed_at"] + 30 * 86400),
        "email": k_dict.get("email") or billing.get("email") or "",
        "network": p.get("network") or "Base Mainnet",
        "currency": curr,
        "payment_method": p.get("payment_method") or "On-Chain Crypto",
        "recipient_address": recip,
        "invoice_no": p.get("invoice_no") or f"INV-2026-{hashlib.sha256(p['tx_hash'].encode()).hexdigest()[:8].upper()}",
        "key_prefix": p.get("key_prefix") or k_dict.get("key_prefix") or (f"wrk_{p['tier'][:4]}_live_***" if is_paid else "PENDING_WIRE_VERIFICATION"),
        "rate_limit_per_min": k_dict.get("rate_limit_per_min") or (3000 if p["tier"] == "institutional" else 600),
        "key_hash": p.get("key_hash") or "",
        "billing": billing
    }
