from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://ethereum-sepolia-rpc.publicnode.com"))
bal = w3.eth.get_balance("0x2034422F8bA7A38981a0d4e7dC3ED80FE859c0c2")
gas_price = w3.eth.gas_price
total = 6500000 * gas_price
print("Balance:", w3.from_wei(bal, "ether"), "ETH")
print("Gas Price:", w3.from_wei(gas_price, "gwei"), "Gwei")
print("Total cost for 6.5M gas:", w3.from_wei(total, "ether"), "ETH")
print("Affordable?", bal >= total)
