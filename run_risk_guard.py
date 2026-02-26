#!/usr/bin/env python3
"""
Verifiable DeFi Risk Guard — CLI.

Usage:
  python run_risk_guard.py [address]
  python run_risk_guard.py 0x4Fa0f435e736A04D7da547E681ce092a427D6205

Output: [Risk Score] | [Model ID] | [Verification Status: VALID/INVALID] | [Transaction Hash]

If $OPG token balance (Base Sepolia) is 0, runs in Demo Mode (simulated infer + SIMULATED VALID).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_ADDRESS = "0x4Fa0f435e736A04D7da547E681ce092a427D6205"
DEMO_MODE_REASON = "ZERO BALANCE"

# $OPG token on Base Sepolia (Zee / OpenGradient)
OPG_TOKEN_ADDRESS = "0x240b09731D96979f50B2C649C9CE10FcF9C7987F"
BASE_SEPOLIA_RPC = "https://sepolia.base.org"
BASE_SEPOLIA_CHAIN_ID = 84532

ERC20_BALANCE_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


def get_opg_token_balance(
    wallet_address: str,
    rpc_url: str | None = None,
    token_address: str | None = None,
) -> int:
    """
    Return $OPG token balance (wei/smallest unit) for wallet on Base Sepolia.
    Uses the specific token contract address; RPC must be Base Sepolia.
    """
    from web3 import Web3
    rpc = rpc_url or BASE_SEPOLIA_RPC
    token = (token_address or OPG_TOKEN_ADDRESS).strip()
    addr = (wallet_address or "").strip()
    if not addr.startswith("0x"):
        addr = "0x" + addr
    if len(addr) != 42:
        return 0
    try:
        w3 = Web3(Web3.HTTPProvider(rpc))
        if not w3.is_connected():
            return 0
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(token),
            abi=ERC20_BALANCE_ABI,
        )
        return contract.functions.balanceOf(Web3.to_checksum_address(addr)).call()
    except Exception:
        return 0


def get_wallet_balance(client) -> int:
    """Return native balance (wei) for the client's wallet address (legacy; prefer get_opg_token_balance)."""
    try:
        return client._blockchain.eth.get_balance(client._wallet_account.address)
    except Exception:
        return 0


def run_demo_mode(address: str, guard, model_id: str) -> "RiskCheckResult":
    """Simulate infer + verification; return result with fake tx and SIMULATED VALID."""
    from src.defi_risk_guard import RiskCheckResult, DEFAULT_RISK_MODEL_CID
    # Deterministic but realistic-looking risk score from address (0.0 - 1.0)
    raw = hashlib.sha256(address.lower().encode()).digest()
    risk_score = round((raw[0] / 255.0) * 0.5 + (raw[1] / 255.0) * 0.5, 4)
    risk_score = max(0.0, min(1.0, risk_score))
    # Realistic fake transaction hash (64 hex chars)
    fake_tx = "0x" + hashlib.sha256(raw + address.encode()).hexdigest()
    verifier = guard._get_verifier()
    verification_status = verifier.verify_inference_tx_simulated(fake_tx)
    return RiskCheckResult(
        risk_score=risk_score,
        model_id=model_id or DEFAULT_RISK_MODEL_CID,
        verification_status=verification_status,
        transaction_hash=fake_tx,
    )


def main():
    address = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADDRESS).strip()
    if not address.startswith("0x"):
        address = "0x" + address

    from src.defi_risk_guard import DeFiRiskGuard, _load_client, DEFAULT_RISK_MODEL_CID
    from src.memory import MemSyncClient

    client = _load_client()
    if client is None:
        print("Error: OpenGradient client not available. Run 'opengradient config init' or set OPENGRADIENT_PRIVATE_KEY.", file=sys.stderr)
        return 1

    memsync = None
    try:
        m = MemSyncClient()
        if m.api_key:
            memsync = m
    except Exception:
        pass

    guard = DeFiRiskGuard(client=client, memsync=memsync)

    # Use $OPG token balance on Base Sepolia (not native chain balance)
    wallet_addr = client._wallet_account.address
    balance = get_opg_token_balance(wallet_addr)

    if balance == 0:
        # Full simulation: no real infer; fake score + fake tx, verifier returns SIMULATED VALID
        print(f"[DEMO MODE: REASON - {DEMO_MODE_REASON}]")
        result = run_demo_mode(address, guard, DEFAULT_RISK_MODEL_CID)
        print(result.to_output_line())
        if memsync:
            profiles = guard.get_risk_profiles_for_address(address, limit=3)
            if profiles:
                print("MemSync risk profiles for this address:", len(profiles))
        return 0

    try:
        result = guard.check_address(address)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(result.to_output_line())
    if memsync:
        profiles = guard.get_risk_profiles_for_address(address, limit=3)
        if profiles:
            print("MemSync risk profiles for this address:", len(profiles))
    return 0


if __name__ == "__main__":
    sys.exit(main())
