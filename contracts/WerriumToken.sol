// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title Werrium Token ($WERR)
 * @dev The native utility and gas currency of Werrealm — The Biomimetic Sovereign Brain-Chain.
 *
 * Total Supply: 1,000,000,000 WERR (Fixed, Non-inflationary)
 * Decimals: 18
 * Chain: Base (Layer 2)
 *
 * Core Ecosystem Components:
 * - Werrealm: The sovereign cognitive realm & consensus network
 * - Werrium ($WERR): The protocol currency & staking collateral
 * - Werron: The neuromorphic cognitive unit (Drosophila connectome synapses)
 * - Werror Engine: The orbital error dynamics & Byzantine fault immunity core
 *
 * Features:
 * - ERC-20 Standard Compliant
 * - EIP-2612 Permit for gasless signatures
 * - Native burn & burnFrom for Metabolic ATP conversion & API Priority Bidding
 */

interface IERC20 {
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 value) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function approve(address spender, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
}

interface IERC20Permit {
    function permit(
        address owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external;
    function nonces(address owner) external view returns (uint256);
    function DOMAIN_SEPARATOR() external view returns (bytes32);
}

contract WerriumToken is IERC20, IERC20Permit {
    string public constant name = "Werrium";
    string public constant symbol = "WERR";
    uint8 public constant decimals = 18;

    uint256 public constant MAX_SUPPLY = 1_000_000_000 * 10**18; // 1 Billion $WERR
    uint256 private _totalSupply;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    // EIP-2612 Permit
    mapping(address => uint256) public override nonces;
    bytes32 public immutable override DOMAIN_SEPARATOR;
    bytes32 public constant PERMIT_TYPEHASH =
        keccak256("Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)");

    // Metabolic Events
    event Burn(address indexed burner, uint256 value);
    event ATPBurnInitiated(address indexed caller, uint256 werrAmount, uint256 atpEquivalent);

    // Initial Treasury / Deployer
    address public immutable genesisTreasury;

    constructor(address _initialTreasury) {
        require(_initialTreasury != address(0), "Invalid treasury address");
        genesisTreasury = _initialTreasury;

        _totalSupply = MAX_SUPPLY;
        _balances[_initialTreasury] = MAX_SUPPLY;
        emit Transfer(address(0), _initialTreasury, MAX_SUPPLY);

        // Compute EIP-712 Domain Separator
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes(name)),
                keccak256(bytes("1")),
                block.chainid,
                address(this)
            )
        );
    }

    function totalSupply() external view override returns (uint256) {
        return _totalSupply;
    }

    function balanceOf(address account) external view override returns (uint256) {
        return _balances[account];
    }

    function transfer(address to, uint256 value) external override returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function allowance(address owner, address spender) external view override returns (uint256) {
        return _allowances[owner][spender];
    }

    function approve(address spender, uint256 value) external override returns (bool) {
        _approve(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external override returns (bool) {
        address spender = msg.sender;
        _spendAllowance(from, spender, value);
        _transfer(from, to, value);
        return true;
    }

    /**
     * @notice Burns WERR tokens permanently from the caller's balance.
     * @param value Amount of WERR to burn.
     */
    function burn(uint256 value) external returns (bool) {
        _burn(msg.sender, value);
        emit Burn(msg.sender, value);
        return true;
    }

    /**
     * @notice Burns WERR tokens on behalf of an account with allowance.
     * @param account Target account to burn from.
     * @param value Amount to burn.
     */
    function burnFrom(address account, uint256 value) external returns (bool) {
        _spendAllowance(account, msg.sender, value);
        _burn(account, value);
        emit Burn(account, value);
        return true;
    }

    /**
     * @notice Metabolic Burn: Burns WERR in exchange for prioritized Werralim ATP quota.
     * 1 WERR (10^18 wei) yields 1,000,000,000 ATP units (1 Gwei = 1 ATP).
     */
    function burnForATP(uint256 value) external returns (uint256 atpGenerated) {
        _burn(msg.sender, value);
        atpGenerated = value / 10**9;
        emit ATPBurnInitiated(msg.sender, value, atpGenerated);
    }

    // EIP-2612 Permit Implementation
    function permit(
        address owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external override {
        require(block.timestamp <= deadline, "Permit expired");

        bytes32 structHash = keccak256(
            abi.encode(PERMIT_TYPEHASH, owner, spender, value, nonces[owner]++, deadline)
        );
        bytes32 hash = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash));
        address signer = ecrecover(hash, v, r, s);

        require(signer != address(0) && signer == owner, "Invalid permit signature");
        _approve(owner, spender, value);
    }

    // Internal Transfer Engine
    function _transfer(address from, address to, uint256 value) internal {
        require(from != address(0), "Transfer from zero address");
        require(to != address(0), "Transfer to zero address");

        uint256 fromBalance = _balances[from];
        require(fromBalance >= value, "Transfer amount exceeds balance");
        unchecked {
            _balances[from] = fromBalance - value;
            _balances[to] += value;
        }

        emit Transfer(from, to, value);
    }

    function _approve(address owner, address spender, uint256 value) internal {
        require(owner != address(0), "Approve from zero address");
        require(spender != address(0), "Approve to zero address");

        _allowances[owner][spender] = value;
        emit Approval(owner, spender, value);
    }

    function _spendAllowance(address owner, address spender, uint256 value) internal {
        uint256 currentAllowance = _allowances[owner][spender];
        if (currentAllowance != type(uint256).max) {
            require(currentAllowance >= value, "Insufficient allowance");
            unchecked {
                _approve(owner, spender, currentAllowance - value);
            }
        }
    }

    function _burn(address account, uint256 value) internal {
        require(account != address(0), "Burn from zero address");

        uint256 accountBalance = _balances[account];
        require(accountBalance >= value, "Burn amount exceeds balance");
        unchecked {
            _balances[account] = accountBalance - value;
            _totalSupply -= value;
        }

        emit Transfer(account, address(0), value);
    }
}
