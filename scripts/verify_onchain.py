from web3 import Web3
import json

w3 = Web3(Web3.HTTPProvider("https://ethereum-sepolia-rpc.publicnode.com"))
contract_addr = "0xe6ecc9575B4D52642c55FCf64E8E2d3baa6e6EF7"
user_addr = "0x803a439fa8F7cf078302b51111Ae003b5221FC19"

with open("/opt/apps/werrealm/contracts/artifacts/WerriumToken.json") as f:
    art = json.load(f)

token = w3.eth.contract(address=contract_addr, abi=art["abi"])

name = token.functions.name().call()
symbol = token.functions.symbol().call()
decimals = token.functions.decimals().call()
total_supply = token.functions.totalSupply().call()
user_bal = token.functions.balanceOf(user_addr).call()
treasury = token.functions.genesisTreasury().call()

print("=" * 65)
print("CANLI ON-CHAIN WERRIUM DOĞRULAMASI:")
print("=" * 65)
print(f"Token Adı       : {name}")
print(f"Sembol          : {symbol}")
print(f"Decimals        : {decimals}")
print(f"Toplam Arz      : {total_supply / 10**decimals:,.0f} {symbol}")
print(f"Hazine Adresi   : {treasury}")
print(f"Kullanıcı Bakiyesi: {user_bal / 10**decimals:,.0f} {symbol}")
print(f"Eşleşme Durumu  : {'%100 TAM EŞLEŞTİ' if user_bal == total_supply else 'UYUŞMAZLIK'}")
print("=" * 65)
