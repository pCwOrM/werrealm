from web3 import Web3
import json

w3 = Web3(Web3.HTTPProvider("https://mainnet.base.org"))
gas_price = w3.eth.gas_price
base_fee = w3.eth.get_block('latest')['baseFeePerGas']

with open("/opt/apps/werrealm/contracts/artifacts/WerriumToken.json") as f:
    art = json.load(f)

# Estimate gas for Base Mainnet
bytecode = art["bytecode"]
est_gas = 865000 # deployment gas

# Priority fee on Base is usually 0.001 gwei or less
cost_wei = est_gas * (base_fee + w3.to_wei(0.005, 'gwei'))
cost_eth = w3.from_wei(cost_wei, 'ether')
cost_usd = float(cost_eth) * 2600 # approx ETH price ($2,600)

print("=" * 65)
print("BASE MAINNET DEPLOY GEREKSINIMLERI:")
print("=" * 65)
print(f"Base Fee       : {w3.from_wei(base_fee, 'gwei')} Gwei")
print(f"Tahmini Gas    : {est_gas:,}")
print(f"Gereken Real ETH: {cost_eth:.8f} ETH ({cost_wei:,} wei)")
print(f"USD Karsiligi  : ~${cost_usd:.4f} USD")
print("=" * 65)

# Check Worker and User balances on Base Mainnet
user_addr = "0x803a439fa8F7cf078302b51111Ae003b5221FC19"
worker_addr = "0x2034422F8bA7A38981a0d4e7dC3ED80FE859c0c2"

user_bal = w3.eth.get_balance(user_addr)
worker_bal = w3.eth.get_balance(worker_addr)

print(f"Kullanici Base Mainnet Bakiye: {w3.from_wei(user_bal, 'ether')} ETH")
print(f"Isici      Base Mainnet Bakiye: {w3.from_wei(worker_bal, 'ether')} ETH")
print("=" * 65)
