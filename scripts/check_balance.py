from web3 import Web3

w_eth_sep = Web3(Web3.HTTPProvider("https://ethereum-sepolia-rpc.publicnode.com"))
w_base_sep = Web3(Web3.HTTPProvider("https://sepolia.base.org"))

targets = {
    "User Metamask (0x803a43...)": "0x803a439fa8F7cf078302b51111Ae003b5221FC19",
    "Worker Srv   (0x203442...)": "0x2034422F8bA7A38981a0d4e7dC3ED80FE859c0c2"
}

print("=" * 65)
print("ETHEREUM SEPOLIA (L1):")
for name, addr in targets.items():
    bal = w_eth_sep.eth.get_balance(addr)
    tx = w_eth_sep.eth.get_transaction_count(addr)
    print(f" - {name}: {w_eth_sep.from_wei(bal, 'ether')} ETH ({bal} wei) | tx: {tx}")

print("\nBASE SEPOLIA (L2):")
for name, addr in targets.items():
    bal = w_base_sep.eth.get_balance(addr)
    tx = w_base_sep.eth.get_transaction_count(addr)
    print(f" - {name}: {w_base_sep.from_wei(bal, 'ether')} ETH ({bal} wei) | tx: {tx}")
print("=" * 65)
