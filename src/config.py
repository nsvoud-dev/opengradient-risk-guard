"""Load configuration from environment with safe defaults."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of src/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def get_private_key() -> str | None:
    """OpenGradient wallet private key. Prefer env; otherwise use opengradient config."""
    return os.environ.get("OPENGRADIENT_PRIVATE_KEY") or os.environ.get("OG_PRIVATE_KEY")


def get_memsync_api_key() -> str | None:
    """MemSync API key for memory layer."""
    return os.environ.get("MEMSYNC_API_KEY")


def get_agent_id() -> str:
    """Agent identifier for MemSync (agent_id)."""
    return os.environ.get("AGENT_ID", "og-chronos-agent")


def get_default_thread_id() -> str:
    """Default conversation thread id for MemSync."""
    return os.environ.get("DEFAULT_THREAD_ID", "main")


def get_rpc_url() -> str | None:
    """OpenGradient RPC URL (e.g. Testnet). From .env OPENGRADIENT_RPC_URL."""
    return os.environ.get("OPENGRADIENT_RPC_URL")


def get_chain_id() -> int | None:
    """OpenGradient chain ID (e.g. 10740 for Testnet). From .env OPENGRADIENT_CHAIN_ID."""
    val = os.environ.get("OPENGRADIENT_CHAIN_ID")
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None
