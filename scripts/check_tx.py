from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://ethereum-sepolia-rpc.publicnode.com"))
tx_hash = "476b7fe9c92c8841078d633d78810d737b6285792800051195b0906fcb8b7b46"
rcpt = w3.eth.get_transaction_receipt(tx_hash)
print("Receipt Status:", rcpt.status)
print("Gas Used:", rcpt.gasUsed)
print("Contract Address:", rcpt.contractAddress)
code = w3.eth.get_code(rcpt.contractAddress)
print("Code length at contract:", len(code))
