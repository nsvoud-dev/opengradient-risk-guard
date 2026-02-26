"""Agent and integration errors for clear handling (x402, memory, network)."""


class OGChronosError(Exception):
    """Base for OG Chronos agent errors."""


class MemoryError(OGChronosError):
    """MemSync memory operation failed (store/search)."""


class MemoryConfigError(OGChronosError):
    """MemSync not configured (e.g. missing API key)."""


class InsufficientFundsError(OGChronosError):
    """x402 / OpenGradient: wallet has insufficient $OPG for LLM payment."""


class LLMError(OGChronosError):
    """LLM inference failed (network, gateway, or payment)."""


class NetworkError(OGChronosError):
    """Generic network/connectivity failure."""
