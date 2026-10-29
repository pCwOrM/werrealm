import urllib.request

urls = [
    "https://portal.cdp.coinbase.com/products/faucet",
    "https://console.optimism.io/faucet",
    "https://faucets.chain.link/",
    "https://sepolia-faucet.pk910.de/",
    "https://learnweb3.io/faucets/base_sepolia",
    "https://bwarelabs.com/faucets/base-sepolia",
    "https://bridge.base.org/deposit"
]

for u in urls:
    try:
        req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=8)
        print(f"[{res.getcode()}] OK -> {u}")
    except Exception as e:
        print(f"[ERR] {e} -> {u}")
