from web3 import Web3
import sys
sys.path.append("/opt/apps/werracle/blockchain_vault")
import werracle_keyloader

w3 = Web3(Web3.HTTPProvider("https://ethereum-sepolia-rpc.publicnode.com"))
account = werracle_keyloader.load_worker_account()

# Base Sepolia OptimismPortal on Ethereum Sepolia
# Calling depositTransaction or sending ETH to L1StandardBridge
bridge_addr = Web3.to_checksum_address("0x3154Cf16ccdb4C6d922629664174b904d80F2C35")
bridge_abi = [
    {
        "inputs": [
            {"internalType": "uint32", "name": "_minGasLimit", "type": "uint32"},
            {"internalType": "bytes", "name": "_extraData", "type": "bytes"}
        ],
        "name": "depositETH",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    }
]

bridge = w3.eth.contract(address=bridge_addr, abi=bridge_abi)
amount_wei = w3.to_wei(0.02, 'ether')

nonce = w3.eth.get_transaction_count(account.address)
base_fee = w3.eth.get_block('latest')['baseFeePerGas']
priority_fee = w3.to_wei(0.05, 'gwei')

tx = bridge.functions.depositETH(200000, b"").build_transaction({
    'from': account.address,
    'value': amount_wei,
    'nonce': nonce,
    'gas': 300000,
    'maxFeePerGas': base_fee * 2 + priority_fee,
    'maxPriorityFeePerGas': priority_fee,
    'chainId': 11155111
})

signed = account.sign_transaction(tx)
raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
tx_hash = w3.eth.send_raw_transaction(raw_tx)
print("Bridge tx sent:", tx_hash.hex())
rcpt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
print("Bridge receipt status:", rcpt.status)
