// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title WerrTreasuryTimelock
 * @dev Sovereign Ecosystem & Treasury Linear Vesting Timelock Contract.
 *
 * Implements non-custodial, mathematically verifiable linear token release
 * for the 999,500,000 $WERR Genesis Treasury to eliminate single-point-of-failure
 * (EOA centralization risk) identified by external audits.
 *
 * Invariants:
 * - Beneficiary can only withdraw tokens that have legally unlocked based on block.timestamp.
 * - Immutable start time, cliff, and duration.
 * - Zero backdoors: No owner function to drain unvested tokens.
 */

interface IERC20 {
    function transfer(address to, uint256 value) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract WerrTreasuryTimelock {
    // Werrium ($WERR) token contract on Base Mainnet
    IERC20 public immutable token;

    // Beneficiary address (Recommended: Gnosis Safe 2/3 or 3/5 Multisig)
    address public immutable beneficiary;

    // Vesting Schedule Parameters (in seconds)
    uint256 public immutable startTimestamp;
    uint256 public immutable cliffDuration;
    uint256 public immutable vestingDuration;

    // Track total released tokens
    uint256 public totalReleased;

    event TokensReleased(address indexed beneficiary, uint256 amount);

    /**
     * @param _token Address of Werrium token (0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2).
     * @param _beneficiary Destination multisig / treasury address.
     * @param _cliffDuration Cliff period in seconds (e.g., 90 days = 7,776,000s).
     * @param _vestingDuration Total vesting duration in seconds (e.g., 730 days = 24 months = 63,072,000s).
     */
    constructor(
        address _token,
        address _beneficiary,
        uint256 _cliffDuration,
        uint256 _vestingDuration
    ) {
        require(_token != address(0), "Invalid token address");
        require(_beneficiary != address(0), "Invalid beneficiary address");
        require(_vestingDuration > _cliffDuration, "Vesting must exceed cliff");

        token = IERC20(_token);
        beneficiary = _beneficiary;
        startTimestamp = block.timestamp;
        cliffDuration = _cliffDuration;
        vestingDuration = _vestingDuration;
    }

    /**
     * @notice Computes total amount of tokens vested up to the current block.timestamp.
     */
    function vestedAmount() public view returns (uint256) {
        uint256 currentBalance = token.balanceOf(address(this));
        uint256 totalAllocation = currentBalance + totalReleased;

        if (block.timestamp < startTimestamp + cliffDuration) {
            return 0;
        } else if (block.timestamp >= startTimestamp + vestingDuration) {
            return totalAllocation;
        } else {
            return (totalAllocation * (block.timestamp - startTimestamp)) / vestingDuration;
        }
    }

    /**
     * @notice Computes tokens currently available for release.
     */
    function releasableAmount() public view returns (uint256) {
        return vestedAmount() - totalReleased;
    }

    /**
     * @notice Releases all currently vested tokens to the beneficiary multisig.
     */
    function release() external returns (uint256) {
        uint256 releasable = releasableAmount();
        require(releasable > 0, "No tokens are releasable at this time");

        totalReleased += releasable;
        emit TokensReleased(beneficiary, releasable);

        require(token.transfer(beneficiary, releasable), "Token transfer failed");
        return releasable;
    }
}
