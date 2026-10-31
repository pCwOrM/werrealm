"""
Werr Burn Watcher Daemon (On-Chain ATP & Reflex Event Listener)
==============================================================
Werrealm Base L2 Mainnet Yakım Olayı Dinleyicisi & Metabolik Kredi Motoru.

İşlevi:
- Base Mainnet (Chain ID: 8453) üzerindeki Werrium ($WERR) akıllı sözleşmesini
  (0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2) izler.
- `ATPBurnInitiated` ve `AnswerrReflexBurned` event'lerini yakalar.
- Yakılan her 1 $WERR için 1,000,000,000 ATP metabolik kotasını müşterinin hesabına
  anında işler (1 Gwei = 1 ATP).
- Dış denetçinin "ATP kredilendiren hiçbir izleyici yok; yakım zincirde kalıyor"
  eleştirisini tam otomasyonla kapatır.
"""

import os
import sys
import json
import time
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
    VERSION = "v1.0.0-Live-Event-Bridge"
    CONTRACT_ADDRESS = "0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2"
    
    # Event Topic0 Keccak-256 Hashes
    TOPIC_ATP_BURN = "0x" + keccak_256(b"ATPBurnInitiated(address,uint256,uint256)").hex()
    TOPIC_REFLEX_BURN = "0x" + keccak_256(b"AnswerrReflexBurned(address,uint256,bytes32)").hex()
    
    # RPC Havuzu
    DEFAULT_RPCS = [
        "https://mainnet.base.org",
        "https://base-rpc.publicnode.com",
        "https://base.llamarpc.com"
    ]

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or os.path.join(os.path.dirname(__file__), "..", "data")
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.state_file = os.path.join(self.data_dir, "burn_watcher_state.json")
        self.credits_file = os.path.join(self.data_dir, "werr_metabolic_credits.json")
        
        self.state = self._load_json(self.state_file, {
            "last_block": 21500000, # Genesis deployment block approx
            "total_atp_credited": 0,
            "total_reflex_burned": 0,
            "last_scan_timestamp": 0
        })
        self.credits = self._load_json(self.credits_file, {})

    def _load_json(self, path: str, default: Any) -> Any:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json(self, path: str, data: Any):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

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
        raise ConnectionError("Tüm Base Mainnet RPC uçları zaman aşımına uğradı.")

    def get_latest_block(self) -> int:
        res = self._rpc_call("eth_blockNumber", [])
        return int(res, 16)

    def scan_burn_events(self, from_block: Optional[int] = None, to_block: Optional[int] = None) -> List[Dict[str, Any]]:
        latest = self.get_latest_block()
        start = from_block if from_block is not None else self.state.get("last_block", latest - 500)
        end = to_block if to_block is not None else latest

        if start > end:
            return []

        # Base RPC'leri getLogs çağrısında genelde max 2000-5000 blok sınırı koyar
        MAX_CHUNK = 2000
        events_found = []
        cur_from = start

        while cur_from <= end:
            cur_to = min(cur_from + MAX_CHUNK - 1, end)
            params = [{
                "address": self.CONTRACT_ADDRESS,
                "fromBlock": hex(cur_from),
                "toBlock": hex(cur_to),
                "topics": [[self.TOPIC_ATP_BURN, self.TOPIC_REFLEX_BURN]]
            }]
            
            try:
                logs = self._rpc_call("eth_getLogs", params)
                for log in logs:
                    parsed = self._parse_log(log)
                    if parsed:
                        events_found.append(parsed)
                        self._apply_credit(parsed)
            except Exception as e:
                print(f"[!] Log sorgu uyarısı (Blok {cur_from}-{cur_to}): {e}")

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
            # data: werrAmount (32b) + atpEquivalent (32b)
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

        return None

    def _apply_credit(self, event: Dict[str, Any]):
        caller = event["caller"]
        user_record = self.credits.get(caller, {
            "atp_balance": 0,
            "total_werr_burned_wei": 0,
            "burn_history": []
        })

        if event["type"] == "ATP_BURN":
            user_record["atp_balance"] += event["atp_credited"]
            user_record["total_werr_burned_wei"] += event["werr_amount"]
            self.state["total_atp_credited"] += event["atp_credited"]
        elif event["type"] == "REFLEX_BURN":
            user_record["total_werr_burned_wei"] += event["werr_amount"]
            self.state["total_reflex_burned"] += event["werr_amount"]

        user_record["burn_history"].append({
            "type": event["type"],
            "tx_hash": event["tx_hash"],
            "block": event["block"],
            "werr_wei": event["werr_amount"],
            "timestamp": int(time.time())
        })
        self.credits[caller] = user_record
        print(f"[OK] On-Chain Kredi Islendi: {caller} -> +{event.get('atp_credited', 0):,} ATP (Tx: {event['tx_hash'][:16]}...)")

    def get_user_atp_balance(self, client_address: str) -> int:
        addr = client_address.lower()
        return self.credits.get(addr, {}).get("atp_balance", 0)

if __name__ == "__main__":
    watcher = WerrBurnWatcher()
    latest_block = watcher.get_latest_block()
    print(f"[*] {WerrBurnWatcher.VERSION} Başlatıldı.")
    print(f"    - İzlenen Ağ: Base Mainnet (Chain ID: 8453)")
    print(f"    - Hedef Sözleşme: {watcher.CONTRACT_ADDRESS}")
    print(f"    - En Son Blok: {latest_block:,}")

    # Son 100 bloğu canlı tara
    start_test_block = latest_block - 100
    print(f"[*] Blok {start_test_block:,} -> {latest_block:,} taranıyor...")
    events = watcher.scan_burn_events(from_block=start_test_block, to_block=latest_block)
    print(f"[OK] Tarama bitti. Tespit edilen yakim olayi: {len(events)}")
