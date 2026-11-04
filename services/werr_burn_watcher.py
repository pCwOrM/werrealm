"""
Werr Burn Watcher Daemon (On-Chain ATP & Reflex Event Listener - v1.1 Production)
================================================================================
Werrealm Base L2 Mainnet Yakım Olayı Dinleyicisi & Metabolik Kredi Motoru.

İşlevi:
- Base Mainnet (Chain ID: 8453) üzerindeki Werrium ($WERR) akıllı sözleşmesini
  (0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2) izler.
- `ATPBurnInitiated(address caller, uint256 werrAmount, uint256 atpEquivalent)` ve
  `AnswerrReflexBurned(address caller, uint256 werrAmount, bytes32 queryHash)` event'lerini yakalar.
- Yakılan her 1 $WERR için 1,000,000,000 ATP metabolik kotasını müşterinin hesabına
  anında işler (1 Gwei = 1 ATP).
- Hem yerel JSON durum dosyasını (`werr_metabolic_credits.json`) hem de SQLite veritabanını
  (`werracle_api_keys.db`) atomik işlemlerle günceller.
- Systemd uyumlu arka plan daemon modu (`--daemon`), sinyal yakalama (SIGINT/SIGTERM) ve
  hata kurtarma mekanizmalarına sahiptir.
"""

import os
import sys
import json
import time
import signal
import sqlite3
import argparse
import requests
from typing import Dict, Any, List, Optional

# Pure Python EVM-Compliant Keccak-256
def keccak_256(data: bytes) -> bytes:
    RC = [
        0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
        0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
        0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
        0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
        0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
        0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008
    ]
    rot = [
        [0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
        [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]
    ]
    rate = 136 # 1088 bits
    state = [[0]*5 for _ in range(5)]
    padded = bytearray(data) + b'\x01'
    while len(padded) % rate != (rate - 1):
        padded += b'\x00'
    padded += b'\x80'
    
    for i in range(0, len(padded), rate):
        block = padded[i:i+rate]
        for idx in range(0, len(block), 8):
            lane_idx = idx // 8
            state[lane_idx % 5][lane_idx // 5] ^= int.from_bytes(block[idx:idx+8], 'little')
        for round_idx in range(24):
            C = [state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4] for x in range(5)]
            D = [C[(x-1)%5] ^ (((C[(x+1)%5] << 1) & 0xFFFFFFFFFFFFFFFF) | (C[(x+1)%5] >> 63)) for x in range(5)]
            for x in range(5):
                for y in range(5):
                    state[x][y] ^= D[x]
            B = [[0]*5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    r = rot[x][y]
                    val = state[x][y]
                    B[y][(2*x + 3*y)%5] = ((val << r) & 0xFFFFFFFFFFFFFFFF) | (val >> (64 - r)) if r else val
            for x in range(5):
                for y in range(5):
                    state[x][y] = B[x][y] ^ ((~B[(x+1)%5][y]) & B[(x+2)%5][y])
            state[0][0] ^= RC[round_idx]
            
    out = bytearray()
    for y in range(5):
        for x in range(5):
            out += state[x][y].to_bytes(8, 'little')
            if len(out) >= 32:
                return bytes(out[:32])
    return bytes(out[:32])

class WerrBurnWatcher:
    VERSION = "v1.2.0-Daemon-Production"
    CONTRACT_ADDRESS = "0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2"
    
    # Event Topic0 Keccak-256 Hashes
    TOPIC_ATP_BURN = "0x" + keccak_256(b"ATPBurnInitiated(address,uint256,uint256)").hex()
    TOPIC_REFLEX_BURN = "0x" + keccak_256(b"AnswerrReflexBurned(address,uint256,bytes32)").hex()
    TOPIC_TRANSFER = "0x" + keccak_256(b"Transfer(address,address,uint256)").hex()
    DEAD_ADDRESS_TOPIC = "0x000000000000000000000000000000000000000000000000000000000000dead"
    
    # RPC Havuzu (Yüksek Erişilebilirlik)
    DEFAULT_RPCS = [
        "https://mainnet.base.org",
        "https://base-rpc.publicnode.com",
        "https://base.llamarpc.com"
    ]

    def __init__(self, data_dir: Optional[str] = None, db_path: Optional[str] = None):
        self.data_dir = data_dir or os.path.join(os.path.dirname(__file__), "..", "data")
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.db_path = db_path or os.environ.get("WERRACLE_DB_PATH", "/var/lib/werracle-health/werracle_api_keys.db")
        self.state_file = os.path.join(self.data_dir, "burn_watcher_state.json")
        self.credits_file = os.path.join(self.data_dir, "werr_metabolic_credits.json")
        
        self.running = True
        
        self.state = self._load_json(self.state_file, {
            "last_block": 21500000,
            "total_atp_credited": 0,
            "total_reflex_burned": 0,
            "last_scan_timestamp": 0
        })
        self.credits = self._load_json(self.credits_file, {})
        
        # SQLite tablosunu hazırla (eğer DB varsa)
        self._init_sqlite_table()

    def _load_json(self, path: str, default: Any) -> Any:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json(self, path: str, data: Any):
        temp_path = path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, path)

    def _init_sqlite_table(self):
        """SQLite üzerinde on-chain yakımları ve kredileri tutan tabloyu oluşturur."""
        if not self.db_path:
            return
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS werr_burn_events (
                        tx_hash TEXT PRIMARY KEY,
                        caller_address TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        werr_amount_wei TEXT NOT NULL,
                        atp_credited INTEGER NOT NULL DEFAULT 0,
                        query_hash TEXT,
                        block_number INTEGER NOT NULL,
                        created_at REAL NOT NULL
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_burn_caller ON werr_burn_events(caller_address);")
                for caller_addr, rec in (self.credits or {}).items():
                    for h in rec.get("burn_history", []):
                        if h.get("tx_hash"):
                            conn.execute("""
                                INSERT OR IGNORE INTO werr_burn_events (
                                    tx_hash, caller_address, event_type, werr_amount_wei,
                                    atp_credited, query_hash, block_number, created_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                h["tx_hash"], caller_addr.lower(), h.get("type", "BURN"),
                                str(h.get("werr_wei", 0)), int(h.get("atp_credited", 0)),
                                h.get("query_hash", ""), int(h.get("block", 0)),
                                float(h.get("timestamp", time.time()))
                            ))
                conn.commit()
        except Exception as e:
            # SQLite erişilemezse bile JSON fallback devrededir
            pass

    def _rpc_call(self, method: str, params: list) -> Any:
        for rpc in self.DEFAULT_RPCS:
            try:
                res = requests.post(rpc, json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params
                }, timeout=6)
                data = res.json()
                if "result" in data:
                    return data["result"]
            except Exception:
                continue
        raise ConnectionError("Tum Base Mainnet RPC uclari zaman asimina ugradi.")

    def get_latest_block(self) -> int:
        res = self._rpc_call("eth_blockNumber", [])
        return int(res, 16)

    def scan_burn_events(self, from_block: Optional[int] = None, to_block: Optional[int] = None) -> List[Dict[str, Any]]:
        latest = self.get_latest_block()
        start = from_block if from_block is not None else self.state.get("last_block", latest - 500)
        end = to_block if to_block is not None else latest

        if start > end:
            return []

        MAX_CHUNK = 2000
        events_found = []
        cur_from = start

        while cur_from <= end:
            cur_to = min(cur_from + MAX_CHUNK - 1, end)
            params = [{
                "address": self.CONTRACT_ADDRESS,
                "fromBlock": hex(cur_from),
                "toBlock": hex(cur_to),
                "topics": [[self.TOPIC_ATP_BURN, self.TOPIC_REFLEX_BURN, self.TOPIC_TRANSFER]]
            }]
            
            try:
                logs = self._rpc_call("eth_getLogs", params)
                for log in logs:
                    parsed = self._parse_log(log)
                    if parsed:
                        events_found.append(parsed)
                        self._apply_credit(parsed)
            except Exception as e:
                print(f"[!] Log sorgu uyarisi (Blok {cur_from}-{cur_to}): {e}")

            cur_from = cur_to + 1

        self.state["last_block"] = end
        self.state["last_scan_timestamp"] = int(time.time())
        self._save_json(self.state_file, self.state)
        self._save_json(self.credits_file, self.credits)
        return events_found

    def _parse_log(self, log: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        topics = log.get("topics", [])
        if not topics:
            return None
        
        t0 = topics[0].lower()
        caller = "0x" + topics[1][-40:].lower() if len(topics) > 1 else "0x0"
        data_hex = log.get("data", "0x")[2:]
        tx_hash = log.get("transactionHash", "")
        block_num = int(log.get("blockNumber", "0x0"), 16)

        if t0 == self.TOPIC_ATP_BURN.lower():
            if len(data_hex) >= 128:
                werr_amount = int(data_hex[0:64], 16)
                atp_amount = int(data_hex[64:128], 16)
            else:
                werr_amount = int(data_hex[:64], 16) if data_hex else 0
                atp_amount = werr_amount // (10**9)

            return {
                "type": "ATP_BURN",
                "caller": caller,
                "werr_amount": werr_amount,
                "atp_credited": atp_amount,
                "tx_hash": tx_hash,
                "block": block_num
            }

        elif t0 == self.TOPIC_REFLEX_BURN.lower():
            query_hash = topics[2] if len(topics) > 2 else "0x0"
            werr_amount = int(data_hex[:64], 16) if data_hex else 0
            
            return {
                "type": "REFLEX_BURN",
                "caller": caller,
                "query_hash": query_hash,
                "werr_amount": werr_amount,
                "tx_hash": tx_hash,
                "block": block_num
            }

        elif t0 == self.TOPIC_TRANSFER.lower() and len(topics) > 2:
            to_topic = topics[2].lower()
            if to_topic == self.DEAD_ADDRESS_TOPIC:
                werr_amount = int(data_hex[:64], 16) if data_hex else 0
                atp_amount = werr_amount // (10**9)
                return {
                    "type": "DEAD_TRANSFER_BURN",
                    "caller": caller,
                    "werr_amount": werr_amount,
                    "atp_credited": atp_amount,
                    "tx_hash": tx_hash,
                    "block": block_num
                }

        return None

    def _apply_credit(self, event: Dict[str, Any]):
        caller = event["caller"].lower()
        now = time.time()
        
        # 1. JSON Bellek Guncelleme (Idempotent)
        user_record = self.credits.get(caller, {
            "atp_balance": 0,
            "total_werr_burned_wei": 0,
            "burn_history": []
        })

        existing_txs = {h.get("tx_hash", "").lower() for h in user_record.get("burn_history", [])}
        if event["tx_hash"].lower() in existing_txs:
            return

        if event["type"] == "ATP_BURN":
            user_record["atp_balance"] += event["atp_credited"]
            user_record["total_werr_burned_wei"] += event["werr_amount"]
            self.state["total_atp_credited"] = self.state.get("total_atp_credited", 0) + event["atp_credited"]
        elif event["type"] == "REFLEX_BURN":
            user_record["total_werr_burned_wei"] += event["werr_amount"]
            self.state["total_reflex_burned"] = self.state.get("total_reflex_burned", 0) + round(event["werr_amount"] / 10**18, 4)
        elif event["type"] == "DEAD_TRANSFER_BURN":
            user_record["atp_balance"] += event["atp_credited"]
            user_record["total_werr_burned_wei"] += event["werr_amount"]
            self.state["total_atp_credited"] = self.state.get("total_atp_credited", 0) + event["atp_credited"]
            self.state["total_reflex_burned"] = round(user_record["total_werr_burned_wei"] / 10**18, 4)
            self.state["last_burn_tx"] = event["tx_hash"]

        user_record["burn_history"].append({
            "type": event["type"],
            "tx_hash": event["tx_hash"],
            "block": event["block"],
            "werr_wei": event["werr_amount"],
            "werr_burned": round(event["werr_amount"] / 10**18, 4),
            "atp_credited": event.get("atp_credited", 0),
            "timestamp": int(now)
        })
        self.credits[caller] = user_record

        # 2. SQLite Veritabani Guncelleme
        if self.db_path and os.path.exists(self.db_path):
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT OR IGNORE INTO werr_burn_events (
                            tx_hash, caller_address, event_type, werr_amount_wei,
                            atp_credited, query_hash, block_number, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        event["tx_hash"], caller, event["type"], str(event["werr_amount"]),
                        event.get("atp_credited", 0), event.get("query_hash", ""),
                        event["block"], now
                    ))
                    conn.commit()
            except Exception:
                pass

        print(f"[OK] On-Chain Kredi Islendi: {caller} -> +{event.get('atp_credited', 0):,} ATP (Tx: {event['tx_hash'][:16]}...)")

    def consume_atp(self, caller_address: str, amount_atp: int, reason: str = "WERRALIM_METABOLIC_SURGE") -> Dict[str, Any]:
        """Werralim Living Cell veya API kapısı tarafından ATP tüketimini on-chain kredi havuzuna işler."""
        addr = caller_address.lower()
        if addr not in self.credits and self.credits:
            # Havuzdaki ana hazine / kurucu yakım havuzunu varsayılan olarak kullan
            addr = next(iter(self.credits.keys()))
        rec = self.credits.get(addr, {
            "atp_balance": 0,
            "total_atp_consumed": 0,
            "total_werr_burned_wei": 0,
            "burn_history": []
        })
        avail = int(rec.get("atp_balance", 0))
        deducted = min(avail, max(0, int(amount_atp)))
        rec["atp_balance"] = avail - deducted
        rec["total_atp_consumed"] = int(rec.get("total_atp_consumed", 0)) + int(amount_atp)
        self.credits[addr] = rec
        self.state["total_atp_consumed"] = int(self.state.get("total_atp_consumed", 0)) + int(amount_atp)
        self._save_json(self.credits_file, self.credits)
        self._save_json(self.state_file, self.state)
        return {
            "pool_address": addr,
            "requested_atp": amount_atp,
            "deducted_from_onchain_pool": deducted,
            "remaining_atp_balance": rec["atp_balance"],
            "total_atp_consumed": rec["total_atp_consumed"],
            "reason": reason
        }

    def get_user_atp_balance(self, client_address: str) -> Dict[str, Any]:
        """İstemcinin birikmiş ATP ve yakılmış WERR dökümünü döner."""
        if not isinstance(client_address, str) or len(client_address.strip()) != 42 or not client_address.strip().startswith("0x"):
            raise ValueError("Invalid EVM address format")
        addr = client_address.strip().lower()
        int(addr[2:], 16)  # Strict hex validation
        rec = self.credits.get(addr, {
            "atp_balance": 0,
            "total_atp_consumed": 0,
            "total_werr_burned_wei": 0,
            "burn_history": []
        })
        return {
            "address": client_address.strip(),
            "atp_balance": rec.get("atp_balance", 0),
            "total_atp_consumed": rec.get("total_atp_consumed", 0),
            "total_werr_burned": round(rec.get("total_werr_burned_wei", 0) / 10**18, 4),
            "total_burn_events": len(rec.get("burn_history", [])),
            "recent_burns": rec.get("burn_history", [])[-5:]
        }

    def run_daemon(self, poll_interval: int = 12):
        """Systemd ve arka plan servisi olarak kesintisiz calisir (2-blok L2 reorg/replica-lag tamponu ile)."""
        SAFE_CONFIRMATIONS = 2
        print(f"[*] {self.VERSION} Daemon Baslatildi (Safe Confirmations: {SAFE_CONFIRMATIONS}).")
        print(f"    - Sozlesme: {self.CONTRACT_ADDRESS} (Base Mainnet)")
        print(f"    - Tarama Araligi: {poll_interval} saniye")
        print(f"    - Durum Dosyasi: {self.state_file}")
        
        while self.running:
            try:
                latest = self.get_latest_block()
                safe_end = max(0, latest - SAFE_CONFIRMATIONS)
                last = self.state.get("last_block", safe_end - 50)
                if safe_end > last:
                    events = self.scan_burn_events(from_block=last + 1, to_block=safe_end)
                    if events:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {len(events)} yeni yakim olayi islendi (Blok: {safe_end:,}).")
                time.sleep(poll_interval)
            except KeyboardInterrupt:
                print("\n[!] Kullanici tarafindan durduruldu.")
                break
            except Exception as e:
                print(f"[!] Hata: {e}. {poll_interval} sn sonra tekrar denenecek...")
                time.sleep(poll_interval)

    def stop(self, *args):
        self.running = False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Werr Burn Watcher Service")
    parser.add_argument("--daemon", action="store_true", help="Kesintisiz arka plan modunda calis")
    parser.add_argument("--interval", type=int, default=12, help="Tarama araligi (saniye)")
    parser.add_argument("--blocks", type=int, default=200, help="Son kac blogu tara (tek seferlik modda)")
    parser.add_argument("--data-dir", type=str, default=None, help="Durum dizini")
    parser.add_argument("--db-path", type=str, default=None, help="SQLite veritabani yolu")
    args = parser.parse_args()

    watcher = WerrBurnWatcher(data_dir=args.data_dir, db_path=args.db_path)
    
    # Sinyalleri yakala
    signal.signal(signal.SIGINT, watcher.stop)
    signal.signal(signal.SIGTERM, watcher.stop)

    if args.daemon:
        watcher.run_daemon(poll_interval=args.interval)
    else:
        latest = watcher.get_latest_block()
        start = latest - args.blocks
        print(f"[*] Tek Seferlik Tarama: Blok {start:,} -> {latest:,}")
        evs = watcher.scan_burn_events(from_block=start, to_block=latest)
        print(f"[OK] Tarama tamamlandi. Bulunan olay sayisi: {len(evs)}")
        print(f"[OK] Genel Durum: Toplam ATP: {watcher.state.get('total_atp_credited', 0):,} | Toplam Reflex Yakimi: {watcher.state.get('total_reflex_burned', 0):,}")
