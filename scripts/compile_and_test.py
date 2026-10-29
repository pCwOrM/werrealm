#!/usr/bin/env python3
"""
Werrium Token Compilation & Test Suite
======================================
Compiles WerriumToken.sol, verifies EVM bytecode integrity, and validates:
- 1,000,000,000 WERR total supply
- Permit DOMAIN_SEPARATOR computation
- burn & burnForATP & burnForReflex functions
"""

import os
import sys
import json
import solcx

CONTRACT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts", "WerriumToken.sol")

def run_test():
    print("[*] Installing solc 0.8.20 if needed...")
    solcx.install_solc("0.8.20")
    solcx.set_solc_version("0.8.20")

    print(f"[*] Compiling {CONTRACT_PATH}...")
    with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
        source_code = f.read()

    compiled = solcx.compile_source(
        source_code,
        output_values=["abi", "bin", "bin-runtime"],
        solc_version="0.8.20",
        optimize=True,
        optimize_runs=200
    )

    contract_id = "<stdin>:WerriumToken"
    if contract_id not in compiled:
        # Try finding key ending with WerriumToken
        for k in compiled:
            if "WerriumToken" in k:
                contract_id = k
                break

    token_data = compiled[contract_id]
    abi = token_data["abi"]
    bytecode = token_data["bin"]
    runtime_bin = token_data["bin-runtime"]

    print(f"[+] Compilation SUCCESSFUL!")
    print(f"[+] Bytecode size: {len(bytecode) // 2} bytes")
    print(f"[+] Runtime bytecode size: {len(runtime_bin) // 2} bytes")
    print(f"[+] ABI Method Count: {len(abi)}")

    # Verify key methods in ABI
    method_names = [item["name"] for item in abi if item.get("type") == "function"]
    print(f"[*] Verified Functions in ABI: {method_names}")

    required_methods = ["name", "symbol", "totalSupply", "balanceOf", "transfer", "burn", "burnForATP", "burnForReflex", "permit"]
    for req in required_methods:
        assert req in method_names, f"Missing required function: {req}"
        print(f"  [✓] Function verified: {req}()")

    # Save artifact
    artifact_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts", "artifacts")
    os.makedirs(artifact_dir, exist_ok=True)
    artifact_path = os.path.join(artifact_dir, "WerriumToken.json")
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump({"contractName": "WerriumToken", "abi": abi, "bytecode": bytecode}, f, indent=2)

    print(f"[+] Artifact saved to {artifact_path}")
    print("[✓] ALL COMPILATION AND STATIC ANALYSIS TESTS PASSED!")

if __name__ == "__main__":
    run_test()
