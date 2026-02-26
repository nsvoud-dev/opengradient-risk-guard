"""
LLM inference via OpenGradient x402 Gateway.
Uses opengradient SDK for payment handling; optional LangChain OpenGradientLLM when available.
"""
from __future__ import annotations

import logging
from typing import Any, List

from .config import get_private_key
from .errors import InsufficientFundsError, LLMError, NetworkError

logger = logging.getLogger(__name__)

# Map model id string to og.TEE_LLM enum
_MODEL_MAP = {
    "gpt-4o": "GPT_4O",
    "gpt-4.1": "GPT_4_1_2025_04_14",
    "claude-4.0-sonnet": "CLAUDE_4_0_SONNET",
    "claude-3.5-haiku": "CLAUDE_3_5_HAIKU",
    "gemini-2.5-pro-preview": "GEMINI_2_5_PRO_PREVIEW",
    "gemini-2.5-flash-preview": "GEMINI_2_5_FLASH_PREVIEW",
}


def _model_to_tee_llm(og, model_id: str):
    key = (model_id or "").split("/")[-1].lower()
    name = _MODEL_MAP.get(key)
    if name and hasattr(og.TEE_LLM, name):
        return getattr(og.TEE_LLM, name)
    return og.TEE_LLM.GPT_4O


def _get_opengradient_llm():
    """Use langchain_opengradient.OpenGradientLLM if available."""
    try:
        from langchain_opengradient import OpenGradientLLM

        return OpenGradientLLM
    except ImportError:
        return None


OpenGradientLLM = _get_opengradient_llm()


class OpenGradientLLMWrapper:
    """
    LangChain-compatible chat model using opengradient SDK (x402).
    Use this when langchain_opengradient.OpenGradientLLM is not available or for full control.
    """

    def __init__(
        self,
        private_key: str | None = None,
        model: str = "openai/gpt-4o",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        ensure_approval_opg: float = 5.0,
    ):
        import opengradient as og

        self._og = og
        key = private_key or get_private_key()
        if not key:
            raise ValueError(
                "OpenGradient private key required. Set OPENGRADIENT_PRIVATE_KEY in .env or run: opengradient config init"
            )
        self._client = og.Client(private_key=key)
        self.model_id = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._ensure_approval_opg = ensure_approval_opg
        self._approval_done = False

    def _ensure_approval(self) -> None:
        if self._approval_done:
            return
        try:
            self._client.llm.ensure_opg_approval(opg_amount=self._ensure_approval_opg)
            self._approval_done = True
        except Exception as e:
            err_msg = str(e).lower()
            if "insufficient" in err_msg or "balance" in err_msg or "allowance" in err_msg:
                raise InsufficientFundsError(
                    "Insufficient $OPG or allowance. Fund wallet on Base Sepolia: https://faucet.opengradient.ai/"
                ) from e
            raise LLMError(f"Permit2 approval failed: {e}") from e

    def _messages_to_og(self, messages: List[dict]) -> List[dict]:
        """Convert LangChain-style messages to OpenGradient API format."""
        out = []
        for m in messages:
            role = m.get("role") or (m.get("type") if isinstance(m.get("type"), str) else "user")
            if role == "human":
                role = "user"
            if role == "ai" or role == "assistant":
                role = "assistant"
            content = m.get("content") or m.get("text") or ""
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", part) if isinstance(part, dict) else str(part)
                    for part in content
                )
            out.append({"role": role, "content": str(content)})
        return out

    def invoke(self, messages: List[dict]) -> str:
        """Run chat completion; return assistant content. Raises InsufficientFundsError, LLMError, NetworkError."""
        self._ensure_approval()
        og_messages = self._messages_to_og(messages)
        model_enum = _model_to_tee_llm(self._og, self.model_id)
        try:
            result = self._client.llm.chat(
                model=model_enum,
                messages=og_messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except Exception as e:
            err_msg = str(e).lower()
            if "402" in str(e) or "payment" in err_msg or "insufficient" in err_msg or "balance" in err_msg:
                raise InsufficientFundsError(
                    "Insufficient $OPG for LLM request. Get testnet tokens: https://faucet.opengradient.ai/"
                ) from e
            if "connection" in err_msg or "timeout" in err_msg or "network" in err_msg:
                raise NetworkError(f"Network error during LLM request: {e}") from e
            raise LLMError(f"LLM request failed: {e}") from e

        try:
            content = result.chat_output.get("content") or result.chat_output.get("message", {}).get("content") or ""
        except AttributeError:
            content = getattr(result, "completion_output", "") or str(result)
        return content if isinstance(content, str) else str(content)


def get_llm(
    use_langchain_llm: bool = True,
    private_key: str | None = None,
    **kwargs: Any,
):
    """
    Return an LLM instance: OpenGradientLLM from langchain_opengradient if available and use_langchain_llm,
    else OpenGradientLLMWrapper (opengradient SDK).
    Both support .invoke(messages) -> str.
    """
    if use_langchain_llm and OpenGradientLLM is not None:
        key = private_key or get_private_key()
        return OpenGradientLLM(private_key=key, **kwargs)
    return OpenGradientLLMWrapper(private_key=private_key, **kwargs)
