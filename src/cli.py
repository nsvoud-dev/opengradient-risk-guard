"""
CLI to chat with OG Chronos agent.
Before each reply the agent retrieves context from MemSync; after each turn it saves the exchange.
"""
from __future__ import annotations

import argparse
import logging
import sys

from .agent import OGChronosAgent
from .errors import InsufficientFundsError, LLMError, MemoryConfigError, MemoryError, NetworkError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("og_chronos")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OG Chronos: persistent AI agent (MemSync + OpenGradient x402 LLM)",
    )
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Disable MemSync (no retrieve/remember).",
    )
    parser.add_argument(
        "--thread",
        default=None,
        help="MemSync thread id (default from env or 'main').",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Less log output.",
    )
    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    try:
        from .memory import MemSyncClient
        memory = None if args.no_memory else MemSyncClient()
        if not args.no_memory and (memory is None or not memory.api_key):
            raise MemoryConfigError("MEMSYNC_API_KEY is not set. Set it in .env or use --no-memory.")
        agent = OGChronosAgent(
            memory=memory,
            thread_id=args.thread,
            reflection_enabled=not args.no_memory,
        )
    except ValueError as e:
        print("Configuration error:", e, file=sys.stderr)
        return 1
    except MemoryConfigError as e:
        print("Memory (MemSync) config error:", e, file=sys.stderr)
        print("Set MEMSYNC_API_KEY in .env or use --no-memory to run without memory.", file=sys.stderr)
        return 1

    print("OG Chronos (OpenGradient + MemSync). Commands: /quit, /thread <id>, /clear")
    print("-" * 50)

    while True:
        try:
            line = input("You: ").strip()
        except EOFError:
            break
        if not line:
            continue
        if line.startswith("/quit"):
            break
        if line.startswith("/thread"):
            parts = line.split(maxsplit=1)
            thread_id = (parts[1] if len(parts) > 1 else "").strip() or "main"
            agent.set_thread_id(thread_id)
            print(f"[thread set to: {thread_id}]")
            continue
        if line.startswith("/clear"):
            agent.clear_session()
            print("[session cleared]")
            continue

        try:
            reply = agent.think(line, include_memory_context=not args.no_memory)
            print("Chronos:", reply)
        except InsufficientFundsError as e:
            print("Payment error (insufficient $OPG):", e, file=sys.stderr)
            print("Get testnet tokens: https://faucet.opengradient.ai/", file=sys.stderr)
        except NetworkError as e:
            print("Network error:", e, file=sys.stderr)
        except LLMError as e:
            print("LLM error:", e, file=sys.stderr)
        except MemoryError as e:
            print("Memory error (MemSync):", e, file=sys.stderr)
        except Exception as e:
            logger.exception("Unexpected error")
            print("Error:", e, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
