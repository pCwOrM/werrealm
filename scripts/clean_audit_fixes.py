import os

def update_files():
    # 1. Update index.html
    index_path = r'c:\Users\maat\Documents\antigravity\wonderful-raman\werrealm\docs\index.html'
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        target = '<span>Sepolia Testnet: <a href="https://sepolia.etherscan.io/address/0xe6ecc9575B4D52642c55FCf64E8E2d3baa6e6EF7" target="_blank" style="color: var(--secondary); text-decoration: underline;">0xe6ecc9575...</a></span>'
        replacement = '<span>BaseScan Verified: <a href="https://basescan.org/address/0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2#code" target="_blank" style="color: var(--secondary); text-decoration: underline;">100% Verified Match (#875262)</a></span>'
        
        if target in content:
            content = content.replace(target, replacement)
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("Successfully updated index.html (Sepolia removed, BaseScan verified linked).")
        else:
            print("Target not found in index.html.")

    # 2. Update tokenomics.html
    tokenomics_path = r'c:\Users\maat\Documents\antigravity\wonderful-raman\werrealm\docs\tokenomics.html'
    if os.path.exists(tokenomics_path):
        with open(tokenomics_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        target = '<strong>Ethereum Sepolia Testnet:</strong> <a href="https://sepolia.etherscan.io/address/0xe6ecc9575B4D52642c55FCf64E8E2d3baa6e6EF7" target="_blank" style="color: var(--accent);">0xe6ecc9575B4D52642c55FCf64E8E2d3baa6e6EF7</a>'
        replacement = '<strong>Chain ID:</strong> <span style="color: var(--text-muted);">8453 (Base Layer-2 Mainnet)</span> &bull; <strong>Verification:</strong> <span style="color: #10b981;">Contract Source Code Verified (#875262)</span>'
        
        if target in content:
            content = content.replace(target, replacement)
            with open(tokenomics_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("Successfully updated tokenomics.html (Sepolia removed).")
        else:
            print("Target not found in tokenomics.html.")

if __name__ == '__main__':
    update_files()
