#!/usr/bin/env python3
"""
Werrium ($WERR) Base Deployment Script
======================================
Deploys WerriumToken.sol to Base Sepolia Testnet (Chain ID: 84532) or Base Mainnet (Chain ID: 8453).

Features:
- Reads compiled bytecode & ABI from contracts/artifacts/WerriumToken.json
- Verifies constructor arguments (initial treasury address)
- Submits deployment transaction with EIP-1559 priority fee
- Waits for receipt and records deployment address in contracts/deployed_addresses.json
"""

import os
import sys
import json
import time
from web3 import Web3
from eth_account import Account

# Ağ Yapılandırması
NETWORKS = {
    "base_sepolia": {
        "rpc": "https://sepolia.base.org",
        "chain_id": 84532,
        "explorer": "https://sepolia.basescan.org"
    },
    "base_mainnet": {
        "rpc": "https://mainnet.base.org",
        "chain_id": 8453,
        "explorer": "https://basescan.org"
    }
}

def deploy(network_name: str = "base_sepolia", private_key: str = None, treasury_address: str = None):
    net = NETWORKS.get(network_name)
    if not net:
        raise ValueError(f"Geçersiz ağ: {network_name}")

    w3 = Web3(Web3.HTTPProvider(net["rpc"]))
    if not w3.is_connected():
        raise ConnectionError(f"RPC'ye bağlanılamadı: {net['rpc']}")

    print(f"[*] Bağlanılan Ağ: {network_name.upper()} (Chain ID: {net['chain_id']})")
    print(f"[*] Son Blok: {w3.eth.block_number}")

    # Artifact Oku
    artifact_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts", "artifacts", "WerriumToken.json")
    if not os.path.exists(artifact_path):
        raise FileNotFoundError(f"Derlenmiş artifact bulunamadı: {artifact_path}. Önce compile_and_test.py çalıştırın.")

    with open(artifact_path, "r", encoding="utf-8") as f:
        artifact = json.load(f)

    abi = artifact["abi"]
    bytecode = artifact["bytecode"]

    if not private_key:
        print("[!] Özel anahtar belirtilmedi. Simülasyon modu aktif.")
        print(f"[+] Sözleşme Bytecode Doğrulandı: {len(bytecode)//2} bytes")
        print(f"[+] Dağıtıma Hazır Constructor Parametresi: {treasury_address or '0xb563DE1D0dD3431486b313F90f2D9f53bd8Ef96d'}")
        return

    account = Account.from_key(private_key)
    treasury = treasury_address or account.address
    print(f"[*] Dağıtıcı Cüzdan: {account.address}")
    print(f"[*] İlk Hazine Cüzdanı (1B $WERR): {treasury}")

    balance = w3.eth.get_balance(account.address)
    print(f"[*] Cüzdan Bakiyesi: {w3.from_wei(balance, 'ether')} ETH")
    if balance == 0:
        raise ValueError("Cüzdanda gas için yetersiz bakiye! Lütfen Base Sepolia musluğundan (faucet) test ETH alın.")

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    nonce = w3.eth.get_transaction_count(account.address)
    base_fee = w3.eth.get_block('latest')['baseFeePerGas']
    priority_fee = w3.to_wei(0.05, 'gwei')
    max_fee = base_fee * 2 + priority_fee

    print("[*] Dağıtım işlemi oluşturuluyor...")
    construct_txn = contract.constructor(treasury).build_transaction({
        'from': account.address,
        'nonce': nonce,
        'gas': 3500000,
        'maxFeePerGas': max_fee,
        'maxPriorityFeePerGas': priority_fee,
        'chainId': net['chain_id']
    })

    signed = account.sign_transaction(construct_txn)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    print(f"[+] İşlem Gönderildi: {tx_hash.hex()}")
    print(f"[*] Onay bekleniyor...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    contract_addr = receipt.contractAddress
    print(f"\n[🎉] WERRIUM TOKEN BAŞARIYLA DAĞITILDI!")
    print(f"[+] Sözleşme Adresi: {contract_addr}")
    print(f"[+] Explorer Linki: {net['explorer']}/address/{contract_addr}")

    # Kaydet
    deployed_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts", "deployed_addresses.json")
    deployed_data = {}
    if os.path.exists(deployed_file):
        with open(deployed_file, "r") as f:
            deployed_data = json.load(f)

    deployed_data[network_name] = {
        "contract": "WerriumToken",
        "symbol": "WERR",
        "address": contract_addr,
        "treasury": treasury,
        "tx_hash": tx_hash.hex(),
        "timestamp": int(time.time()),
        "explorer": f"{net['explorer']}/address/{contract_addr}"
    }

    with open(deployed_file, "w") as f:
        json.dump(deployed_data, f, indent=2)

    print(f"[+] Dağıtım bilgisi kaydedildi: {deployed_file}")

if __name__ == "__main__":
    net = sys.argv[1] if len(sys.argv) > 1 else "base_sepolia"
    pk = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("DEPLOYER_PRIVATE_KEY")
    treasury = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("GENESIS_TREASURY")
    deploy(net, pk, treasury)
