from web3 import Web3
import json

w3 = Web3(Web3.HTTPProvider("https://sepolia.base.org"))
target = "0xb563DE1D0dD3431486b313F90f2D9f53bd8Ef96d"
bal = w3.eth.get_balance(target)
gas_price = w3.eth.gas_price

with open("/opt/apps/werrealm/contracts/artifacts/WerriumToken.json") as f:
    art = json.load(f)

bytecode = art["bytecode"]
# estimate gas for deployment
contract = w3.eth.contract(abi=art["abi"], bytecode=bytecode)
try:
    est_gas = contract.constructor(target).estimate_gas({'from': target})
except Exception as e:
    est_gas = 1600000 # fallback approx

total_cost = est_gas * gas_price
print("=" * 60)
print(f"CÜZDAN BAKIYESI : {w3.from_wei(bal, 'ether')} ETH ({bal} wei)")
print(f"GUNCEL GAS FIYATI: {w3.from_wei(gas_price, 'gwei')} Gwei ({gas_price} wei)")
print(f"TAHMINI DEPLOY GAS: {est_gas}")
print(f"GEREKLI TOPLAM ETH: {w3.from_wei(total_cost, 'ether')} ETH ({total_cost} wei)")
print(f"YETERLI MI?       : {'EVET' if bal >= total_cost else 'HAYIR'}")
print("=" * 60)
