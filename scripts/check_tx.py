import urllib.request
import json

tx_hash = '0xf6c1840349a40f86789b0de302ebe641d51eb6f82cf7e5c68d5a993e2b6372a6'
rpc_urls = ['https://base-rpc.publicnode.com', 'https://mainnet.base.org']

payload = {
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'eth_getTransactionReceipt',
    'params': [tx_hash]
}
headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

for rpc in rpc_urls:
    try:
        req = urllib.request.Request(rpc, json.dumps(payload).encode('utf-8'), headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            res = data.get('result')
            if res:
                print('RPC Used:', rpc)
                print('Tx Status:', res.get('status'))
                print('Block Number:', int(res.get('blockNumber'), 16))
                for log in res.get('logs', []):
                    d = log.get('data', '0x')
                    val = int(d, 16) / 10**18 if d != '0x' else 0
                    topics = log.get('topics', [])
                    from_addr = '0x' + topics[1][-40:] if len(topics) > 1 else 'N/A'
                    to_addr = '0x' + topics[2][-40:] if len(topics) > 2 else 'N/A'
                    print(f'Token: {log.get("address")}')
                    print(f'From:  {from_addr}')
                    print(f'To:    {to_addr}')
                    print(f'Amount: {val:,.2f} WERR')
                break
    except Exception as e:
        print(f'RPC {rpc} failed: {e}')
