#!/usr/bin/env python3
"""
Verify OpenGradient setup: load local config, check balance, ping RPC.
Uses OpenGradient Testnet: RPC https://ogevmdevnet.opengradient.ai, Chain ID 10740.
Set OPENGRADIENT_RPC_URL and OPENGRADIENT_CHAIN_ID in .env.
"""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env so OPENGRADIENT_RPC_URL / OPENGRADIENT_CHAIN_ID are used
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Expected address from your setup
EXPECTED_ADDRESS = "0x4Fa0f435e736A04D7da547E681ce092a427D6205"

OG_CONFIG_FILE = Path.home() / ".opengradient_config.json"


def load_local_config():
    """Load OpenGradient config created by 'opengradient config init'."""
    if not OG_CONFIG_FILE.exists():
        print(f"Config not found: {OG_CONFIG_FILE}")
        print("Run: opengradient config init")
        return None
    with OG_CONFIG_FILE.open("r") as f:
        config = json.load(f)
    if not config.get("private_key"):
        print("Config exists but private_key is missing.")
        return None
    return config


def save_local_config_rpc(config: dict, rpc_url: str, chain_id: int):
    """Write rpc_url and chain_id into SDK config so they persist (opengradient config show / manual check)."""
    config["rpc_url"] = rpc_url
    config["chain_id"] = chain_id
    try:
        with OG_CONFIG_FILE.open("w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Could not update config file with RPC: {e}")


def main():
    print("OpenGradient setup verification")
    print("-" * 40)

    config = load_local_config()
    if not config:
        sys.exit(1)

    try:
        import opengradient as og
        from opengradient.defaults import (
            DEFAULT_RPC_URL,
            DEFAULT_API_URL,
            DEFAULT_INFERENCE_CONTRACT_ADDRESS,
        )
    except ImportError as e:
        print("OpenGradient SDK not installed:", e)
        print("Run: pip install opengradient")
        sys.exit(1)

    # RPC: OpenGradient Testnet from .env (10740)
    rpc_url = os.environ.get("OPENGRADIENT_RPC_URL") or DEFAULT_RPC_URL
    expected_chain_id = os.environ.get("OPENGRADIENT_CHAIN_ID")
    if expected_chain_id is not None:
        try:
            expected_chain_id = int(expected_chain_id)
        except ValueError:
            expected_chain_id = 10740
    else:
        expected_chain_id = 10740

    # Initialize client from local config with Testnet RPC
    private_key = config["private_key"]
    client = og.Client(
        private_key=private_key,
        rpc_url=rpc_url,
        api_url=DEFAULT_API_URL,
        contract_address=DEFAULT_INFERENCE_CONTRACT_ADDRESS,
        email=config.get("email"),
        password=config.get("password"),
    )

    address = client._wallet_account.address
    print(f"Address: {address}")
    if address.lower() != EXPECTED_ADDRESS.lower():
        print(f"(Expected: {EXPECTED_ADDRESS})")

    # 1. Balance on OpenGradient network (native token)
    try:
        balance_wei = client._blockchain.eth.get_balance(address)
        balance_ether = balance_wei / 1e18
        print(f"Balance (OpenGradient chain): {balance_ether} (wei: {balance_wei})")
    except Exception as e:
        print("Balance check failed:", e)
        sys.exit(1)

    # 2. Ping RPC: get block number / chain id (OpenGradient Testnet)
    try:
        block = client._blockchain.eth.block_number
        chain_id = client._blockchain.eth.chain_id
        print(f"RPC ping OK — chain_id={chain_id}, block_number={block}")
        print(f"RPC (Testnet): {rpc_url}")
        if chain_id != expected_chain_id:
            print(f"WARNING: expected chain_id={expected_chain_id}, got {chain_id}")
    except Exception as e:
        print("RPC ping failed:", e)
        sys.exit(1)

    # 3. $OPG token on Base Sepolia (for Risk Guard live/demo and x402)
    OPG_TOKEN = "0x240b09731D96979f50B2C649C9CE10FcF9C7987F"
    BASE_SEPOLIA_RPC = "https://sepolia.base.org"
    try:
        from run_risk_guard import get_opg_token_balance
        opg_balance = get_opg_token_balance(address, rpc_url=BASE_SEPOLIA_RPC, token_address=OPG_TOKEN)
        print(f"$OPG token (Base Sepolia): balance={opg_balance} (token: {OPG_TOKEN})")
        print(f"Base Sepolia RPC: {BASE_SEPOLIA_RPC} (chain_id=84532)")
    except Exception as e:
        print(f"$OPG balance check skipped: {e}")

    # Persist RPC/chain_id in SDK config file for visibility
    try:
        save_local_config_rpc(config, rpc_url, expected_chain_id)
        print(f"Config updated: rpc_url={rpc_url}, chain_id={expected_chain_id}")
    except Exception as e:
        print(f"Config update skipped: {e}")

    print("-" * 40)
    print("READY TO BUILD CHRONOS AGENT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
