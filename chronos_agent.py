#!/usr/bin/env python3
"""
OG-CHRONOS AGENT — Smart Toggle (Online / Offline).

At startup, checks wallet balance for 0x4Fa0f435e736A04D7da547E681ce092a427D6205:
  - Balance > 0: Real OpenGradientLLM + OpenGradientVectorStore (MemSync), x402 payments.
  - Balance == 0: MockAgent simulates inference and memory; run without tokens.

Features: vector memory (search past context), x402 payment/proof notice, reflection (what we save).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

# Project root (directory containing this file)
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Colors: use colorama for Windows-safe ANSI
try:
    import colorama
    colorama.init()
    C = type("C", (), {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "cyan": "\033[36m",
        "magenta": "\033[35m",
        "red": "\033[31m",
    })()
except Exception:
    C = type("C", (), {k: "" for k in "reset bold dim green yellow blue cyan magenta red".split()})()

WALLET_ADDRESS = "0x4Fa0f435e736A04D7da547E681ce092a427D6205"
OG_CONFIG_FILE = Path.home() / ".opengradient_config.json"

# ---------------------------------------------------------------------------
# Config & balance check
# ---------------------------------------------------------------------------


def load_og_config() -> dict | None:
    """Load OpenGradient config from ~/.opengradient_config.json."""
    if not OG_CONFIG_FILE.exists():
        return None
    try:
        with OG_CONFIG_FILE.open("r") as f:
            return json.load(f)
    except Exception:
        return None


def get_wallet_balance() -> int | None:
    """Return native balance (wei) for WALLET_ADDRESS on OpenGradient RPC, or None on error."""
    config = load_og_config()
    if not config or not config.get("private_key"):
        return None
    try:
        import opengradient as og
        import os
        from opengradient.defaults import (
            DEFAULT_RPC_URL,
            DEFAULT_API_URL,
            DEFAULT_INFERENCE_CONTRACT_ADDRESS,
        )
        rpc_url = os.environ.get("OPENGRADIENT_RPC_URL") or DEFAULT_RPC_URL
        client = og.Client(
            private_key=config["private_key"],
            rpc_url=rpc_url,
            api_url=DEFAULT_API_URL,
            contract_address=DEFAULT_INFERENCE_CONTRACT_ADDRESS,
            email=config.get("email"),
            password=config.get("password"),
        )
        balance = client._blockchain.eth.get_balance(WALLET_ADDRESS)
        return balance
    except Exception:
        return None


def is_online() -> bool:
    """True if wallet has balance > 0 and we can use real LLM + MemSync."""
    bal = get_wallet_balance()
    return bal is not None and bal > 0


# ---------------------------------------------------------------------------
# MockAgent: simulates vector search, inference, and reflection (no tokens)
# ---------------------------------------------------------------------------

MOCK_RESPONSES = [
    "That's a great question. In a fully connected world I'd run this on OpenGradient's TEE and return a verified result—for now, consider this a preview of Chronos!",
    "I'd love to help. Once we're on-chain, I'll use MemSync to remember this and x402 to pay for inference. For now: you're building something cool with OG.",
    "Interesting! My memory layer would store this for future context. Right now I'm in mock mode—add testnet tokens to go live.",
    "Noted. In production I'd search vector memory first, then call the real LLM and save new facts. Here's a simulated reply to keep the conversation going.",
    "Chronos is designed to remember and reflect. This turn would be embedded and stored; for now, here's a placeholder with personality.",
]


class MockAgent:
    """Simulates OG-Chronos: vector search, inference, and reflection—no network."""

    def __init__(self):
        self._session_memories: list[str] = []

    def retrieve_context(self, query: str) -> str:
        """Simulate vector memory search (MemSync / OpenGradientVectorStore)."""
        if self._session_memories:
            return "Prior context from this session:\n" + "\n".join(f"- {m}" for m in self._session_memories[-5:])
        return "(No prior memories in this session.)"

    def think(self, user_message: str) -> tuple[str, str]:
        """
        Simulate: 1) search memory, 2) inference, 3) reflection.
        Returns (reply, what_to_save).
        """
        context = self.retrieve_context(user_message)
        # Simulate creative response
        reply = random.choice(MOCK_RESPONSES)
        # Simulate reflection: what we would save
        what_to_save = f"User asked about: {user_message[:60]}{'...' if len(user_message) > 60 else ''}"
        self._session_memories.append(what_to_save)
        return reply, what_to_save


# ---------------------------------------------------------------------------
# Real agent (OpenGradientLLM + MemSync / OpenGradientVectorStore)
# ---------------------------------------------------------------------------

def build_real_agent():
    """Build OGChronosAgent with langchain-opengradient + MemSync; None if not possible."""
    config = load_og_config()
    private_key = (config or {}).get("private_key")
    if not private_key:
        import os
        private_key = os.environ.get("OPENGRADIENT_PRIVATE_KEY") or os.environ.get("OG_PRIVATE_KEY")
    if not private_key:
        return None

    try:
        from src.llm import get_llm
        from src.memory import MemSyncClient
        from src.agent import OGChronosAgent
        from src.config import get_default_thread_id
    except ImportError:
        return None

    # Prefer langchain-opengradient OpenGradientLLM; fallback to our wrapper (x402)
    llm = get_llm(use_langchain_llm=True, private_key=private_key)
    memory = None
    try:
        memory = MemSyncClient()
        if not memory.api_key:
            memory = None
    except Exception:
        memory = None

    agent = OGChronosAgent(
        llm=llm,
        memory=memory,
        thread_id=get_default_thread_id(),
        reflection_enabled=True,
    )
    return agent


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_header(online: bool):
    title = "OG-CHRONOS AGENT"
    mode = "ONLINE" if online else "OFFLINE"
    color = C.green if online else C.yellow
    width = 50
    print()
    print(C.bold + color + "=" * width + C.reset)
    print(C.bold + color + f"  {title} [{mode}]" + C.reset)
    print(C.bold + color + "=" * width + C.reset)
    print(C.dim + f"  Wallet: {WALLET_ADDRESS}" + C.reset)
    if online:
        print(C.dim + "  LLM: OpenGradientLLM (x402) | Memory: MemSync (OpenGradientVectorStore)" + C.reset)
    else:
        print(C.dim + "  Simulating inference & memory (balance was 0 or unavailable)" + C.reset)
    print()


def run_mock_loop():
    agent = MockAgent()
    print(C.cyan + "Commands: /quit, /clear" + C.reset)
    print()
    while True:
        try:
            user_input = input(C.blue + "You: " + C.reset).strip()
        except EOFError:
            break
        if not user_input:
            continue
        if user_input.startswith("/quit"):
            break
        if user_input.startswith("/clear"):
            agent._session_memories.clear()
            print(C.dim + "[Session memory cleared.]" + C.reset)
            continue

        # 1) Vector memory search
        print(C.dim + "  Searching MemSync for past context..." + C.reset)
        context = agent.retrieve_context(user_input)
        print(C.dim + f"  Context: {context[:200]}{'...' if len(context) > 200 else ''}" + C.reset)

        # 2) Inference (simulated)
        print(C.dim + "  Simulating on-chain inference..." + C.reset)
        reply, what_to_save = agent.think(user_input)
        print(C.green + "Chronos: " + C.reset + reply)

        # 3) Reflection
        print(C.magenta + "  Saving to memory: " + C.reset + what_to_save)
        print()


def run_real_loop(agent):
    from src.config import get_default_thread_id
    print(C.cyan + "Commands: /quit, /clear" + C.reset)
    print()
    while True:
        try:
            user_input = input(C.blue + "You: " + C.reset).strip()
        except EOFError:
            break
        if not user_input:
            continue
        if user_input.startswith("/quit"):
            break
        if user_input.startswith("/clear"):
            agent.clear_session()
            print(C.dim + "[Session cleared.]" + C.reset)
            continue

        # 1) Vector memory (OpenGradientVectorStore / MemSync)
        print(C.dim + "  Searching MemSync (vector store) for past context..." + C.reset)
        context = agent.retrieve_context(user_input)
        if context:
            print(C.dim + f"  Context: {context[:250]}{'...' if len(context) > 250 else ''}" + C.reset)
        else:
            print(C.dim + "  (No prior context.)" + C.reset)

        # 2) LLM via x402
        print(C.dim + "  Calling OpenGradientLLM (x402 Gateway)..." + C.reset)
        try:
            reply = agent.think(user_input, include_memory_context=True)
            print(C.dim + "  Payment & proof: settled via x402 Gateway (Base Sepolia $OPG)." + C.reset)
        except Exception as e:
            print(C.red + f"  Error: {e}" + C.reset)
            continue
        print(C.green + "Chronos: " + C.reset + reply)

        # 3) Reflection (what we save to permanent memory)
        print(C.magenta + "  Saving to memory: " + C.reset + "Last exchange stored in MemSync for extraction and indexing.")
        print()


def main():
    online = is_online()
    print_header(online)

    if online:
        agent = build_real_agent()
        if agent is None:
            print(C.yellow + "Could not build real agent (missing config or imports). Falling back to mock." + C.reset)
            online = False
        else:
            run_real_loop(agent)
            return 0

    if not online:
        run_mock_loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
