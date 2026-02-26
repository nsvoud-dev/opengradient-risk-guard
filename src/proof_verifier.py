"""
Low-level cryptographic proof verification for OpenGradient inference.

Verifies that an inference transaction was successfully executed and that
the InferenceResult event was emitted on-chain. This is the programmatic
validation layer for verifiable ML/LLM inference.
"""
from __future__ import annotations

import logging
from typing import Any

from web3.logs import DISCARD

logger = logging.getLogger(__name__)

VERIFIED = "VALID"
NOT_VERIFIED = "INVALID"
SIMULATED_VERIFIED = "SIMULATED VALID"


class ProofVerifier:
    """
    Programmatically verify inference proof by checking on-chain transaction
    receipt and InferenceResult event emission.
    """

    def __init__(
        self,
        blockchain,  # Web3 instance
        contract_address: str,
        inference_abi: dict[str, Any],
    ):
        self._blockchain = blockchain
        self._contract_address = contract_address
        self._inference_abi = inference_abi
        self._contract = self._blockchain.eth.contract(
            address=self._blockchain.to_checksum_address(contract_address),
            abi=inference_abi,
        )

    def verify_inference_tx(self, tx_hash: str) -> str:
        """
        Verify that the transaction represents a valid inference execution.

        Steps:
        1. Fetch transaction receipt by tx_hash.
        2. Confirm receipt exists and transaction succeeded (status == 1).
        3. Parse InferenceResult event from logs and confirm at least one emitted.

        Returns:
            "VALID" if all checks pass, "INVALID" otherwise.
        """
        if not tx_hash or not isinstance(tx_hash, str):
            return NOT_VERIFIED
        tx_hash = tx_hash.strip()
        if tx_hash.startswith("0x"):
            pass
        else:
            tx_hash = "0x" + tx_hash

        try:
            receipt = self._blockchain.eth.get_transaction_receipt(tx_hash)
        except Exception as e:
            logger.debug("ProofVerifier: get_transaction_receipt failed: %s", e)
            return NOT_VERIFIED

        if receipt is None:
            return NOT_VERIFIED

        if receipt.get("status") != 1:
            return NOT_VERIFIED

        try:
            parsed = self._contract.events.InferenceResult().process_receipt(
                receipt, errors=DISCARD
            )
        except Exception as e:
            logger.debug("ProofVerifier: process_receipt InferenceResult failed: %s", e)
            return NOT_VERIFIED

        if not parsed or len(parsed) < 1:
            return NOT_VERIFIED

        return VERIFIED

    def verify_llm_completion_tx(self, tx_hash: str) -> str:
        """
        Verify a transaction that emitted LLMCompletionResult (LLM completion path).
        Same logic: receipt exists, status == 1, and the corresponding event is present.
        """
        if not tx_hash or not isinstance(tx_hash, str):
            return NOT_VERIFIED
        tx_hash = tx_hash.strip()
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash

        try:
            receipt = self._blockchain.eth.get_transaction_receipt(tx_hash)
        except Exception:
            return NOT_VERIFIED
        if receipt is None or receipt.get("status") != 1:
            return NOT_VERIFIED
        try:
            parsed = self._contract.events.LLMCompletionResult().process_receipt(
                receipt, errors=DISCARD
            )
        except Exception:
            return NOT_VERIFIED
        return VERIFIED if (parsed and len(parsed) >= 1) else NOT_VERIFIED

    def verify_llm_chat_tx(self, tx_hash: str) -> str:
        """Verify a transaction that emitted LLMChatResult (LLM chat path)."""
        if not tx_hash or not isinstance(tx_hash, str):
            return NOT_VERIFIED
        tx_hash = tx_hash.strip()
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
        try:
            receipt = self._blockchain.eth.get_transaction_receipt(tx_hash)
        except Exception:
            return NOT_VERIFIED
        if receipt is None or receipt.get("status") != 1:
            return NOT_VERIFIED
        try:
            parsed = self._contract.events.LLMChatResult().process_receipt(
                receipt, errors=DISCARD
            )
        except Exception:
            return NOT_VERIFIED
        return VERIFIED if (parsed and len(parsed) >= 1) else NOT_VERIFIED

    def verify_inference_tx_simulated(self, tx_hash: str) -> str:
        """
        Demo/simulation: return SIMULATED VALID without hitting the chain.
        Use when balance is zero and we are showing the full flow with a fake tx hash.
        """
        return SIMULATED_VERIFIED
