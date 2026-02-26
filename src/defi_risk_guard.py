"""
Verifiable DeFi Risk Guard — deep OpenGradient integration.

- Calls a specific Model Hub model by CID (not just the general gateway).
- Programmatically verifies the cryptographic proof after inference.
- MemSync analytics: store and cluster Risk Profiles (decentralized bad-actor DB).

Output format: [Risk Score] | [Model ID] | [Verification Status: VALID/INVALID] | [Transaction Hash]
"""
from __future__ import annotations

# Совместимость eth_account: в новых версиях только rawTransaction (camelCase);
# SDK ожидает raw_transaction — добавляем алиас, чтобы send_raw_transaction не падал.
try:
    from eth_account.datastructures import SignedTransaction
    if not hasattr(SignedTransaction, 'raw_transaction'):
        raw_transaction = property(lambda self: getattr(self, 'rawTransaction'))
        SignedTransaction.raw_transaction = raw_transaction
except Exception:
    pass

import json
import logging
from dataclasses import dataclass
from typing import Any

from .proof_verifier import ProofVerifier, VERIFIED, NOT_VERIFIED

logger = logging.getLogger(__name__)

# Model Hub: модель волатильности (актуальный CID с Хаба)
DEFAULT_RISK_MODEL_CID = "KzAHsOHStzAi93_SN-n5H_LjupBjKoxC8qMILxeRdI"


def _address_to_model_input(address: str) -> dict[str, Any]:
    """Derive deterministic model input from address for the demo Model Hub model."""
    address = (address or "").strip().lower()
    if not address.startswith("0x"):
        address = "0x" + address
    # Use address bytes for reproducible numeric inputs
    raw = bytes.fromhex(address[2:].zfill(40)[:40])
    nums = [float((b % 100) / 100.0) for b in raw[:4]]
    return {
        "num_input1": nums if nums else [0.0, 0.0, 0.0],
        "num_input2": sum(nums) * 25 if nums else 10,
        "str_input1": [address[:10], "risk"],
        "str_input2": " defi",
    }


def _extract_risk_score_from_output(model_output: dict[str, Any]) -> float:
    """
    Extract a 0–1 risk score from the model's output dict (name -> np.ndarray).
    Uses first numeric value found; if none, returns 0.5.
    """
    import numpy as np
    for _name, arr in (model_output or {}).items():
        if hasattr(arr, "flatten"):
            flat = np.asarray(arr).flatten()
            if flat.size > 0:
                val = float(np.asarray(flat.flat[0]))
                # Clamp to [0, 1]; if model returns larger range, normalize
                if val < 0 or val > 1:
                    val = max(0.0, min(1.0, (val % 1.0)))
                return round(val, 4)
    return 0.5


@dataclass
class RiskCheckResult:
    risk_score: float
    model_id: str
    verification_status: str  # VALID | INVALID
    transaction_hash: str

    def to_output_line(self) -> str:
        return f"[{self.risk_score}] | [{self.model_id}] | [Verification Status: {self.verification_status}] | [{self.transaction_hash}]"


class DeFiRiskGuard:
    """
    Verifiable DeFi Risk Guard: Model Hub inference + proof verification + MemSync analytics.
    """

    def __init__(
        self,
        client=None,
        model_cid: str | None = None,
        memsync=None,
        inference_mode=None,
    ):
        self._client = client
        self._model_cid = (model_cid or DEFAULT_RISK_MODEL_CID).strip()
        self._memory = memsync
        self._inference_mode = inference_mode
        self._verifier: ProofVerifier | None = None

    def _ensure_client(self):
        if self._client is not None:
            return
        self._client = _load_client()
        if self._client is None:
            raise RuntimeError(
                "OpenGradient client not available. Run opengradient config init or set OPENGRADIENT_PRIVATE_KEY."
            )

    def _get_verifier(self) -> ProofVerifier:
        self._ensure_client()
        if self._verifier is None:
            self._verifier = ProofVerifier(
                self._client._blockchain,
                self._client._inference_hub_contract_address,
                self._client._inference_abi,
            )
        return self._verifier

    def check_address(self, address: str) -> RiskCheckResult:
        """
        Run Model Hub inference for the address, verify proof, return formatted result.
        """
        import opengradient as og
        self._ensure_client()
        mode = self._inference_mode or og.InferenceMode.VANILLA
        model_input = _address_to_model_input(address)

        # 1) Low-level SDK call: specific Model Hub model by CID
        result = self._client.infer(
            model_cid=self._model_cid,
            inference_mode=mode,
            model_input=model_input,
        )
        tx_hash = getattr(result, "transaction_hash", None) or getattr(result, "tx_hash", "")
        model_output = getattr(result, "model_output", None) or {}
        if isinstance(model_output, dict) and not model_output:
            model_output = {}

        risk_score = _extract_risk_score_from_output(model_output)

        # 2) Programmatic proof verification (on-chain receipt + InferenceResult event)
        verifier = self._get_verifier()
        verification_status = verifier.verify_inference_tx(tx_hash)

        out = RiskCheckResult(
            risk_score=risk_score,
            model_id=self._model_cid,
            verification_status=verification_status,
            transaction_hash=tx_hash,
        )
        # 3) MemSync analytics: store risk profile for clustering / bad-actor DB
        self._store_risk_profile(address, out)
        return out

    def _store_risk_profile(self, address: str, result: RiskCheckResult) -> None:
        """Store risk profile in MemSync for analytics and clustering."""
        if self._memory is None or not getattr(self._memory, "api_key", None):
            return
        try:
            profile_text = (
                f"DeFi Risk Profile: address {address} risk_score {result.risk_score} "
                f"model_id {result.model_id} verification {result.verification_status} tx_hash {result.transaction_hash}"
            )
            self._memory.store_messages(
                messages=[
                    {"role": "user", "content": profile_text},
                    {"role": "assistant", "content": f"Stored risk profile for {address}; verification {result.verification_status}."},
                ],
                thread_id="risk_profiles",
                source="risk_guard",
            )
        except Exception as e:
            logger.warning("MemSync store_risk_profile failed: %s", e)

    def get_risk_profiles_for_address(self, address: str, limit: int = 5) -> list[dict]:
        """Retrieve stored risk profiles (MemSync search) for an address."""
        if self._memory is None or not getattr(self._memory, "api_key", None):
            return []
        try:
            r = self._memory.search(query=f"risk profile address {address}", limit=limit, rerank=True)
            return (r.get("memories") or [])
        except Exception as e:
            logger.warning("MemSync search risk profiles failed: %s", e)
            return []

    def cluster_risk_profiles(self, query: str = "risk profile high risk score", limit: int = 10) -> list[dict]:
        """Cluster-style retrieval: e.g. high-risk addresses."""
        if self._memory is None or not getattr(self._memory, "api_key", None):
            return []
        try:
            r = self._memory.search(query=query, limit=limit, rerank=True)
            return (r.get("memories") or [])
        except Exception:
            return []


def _load_client():
    """Load OpenGradient client from local config or env. Uses .env OPENGRADIENT_RPC_URL (Testnet)."""
    import os
    from .config import get_rpc_url
    config_path = os.path.expanduser("~/.opengradient_config.json")
    private_key = os.environ.get("OPENGRADIENT_PRIVATE_KEY") or os.environ.get("OG_PRIVATE_KEY")
    if not private_key and os.path.isfile(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            private_key = config.get("private_key")
        except Exception:
            pass
    if not private_key:
        return None
    try:
        import opengradient as og
        from opengradient.defaults import (
            DEFAULT_RPC_URL,
            DEFAULT_API_URL,
            DEFAULT_INFERENCE_CONTRACT_ADDRESS,
        )
        rpc_url = get_rpc_url() or os.environ.get("OPENGRADIENT_RPC_URL") or DEFAULT_RPC_URL
        return og.Client(
            private_key=private_key,
            rpc_url=rpc_url,
            api_url=DEFAULT_API_URL,
            contract_address=DEFAULT_INFERENCE_CONTRACT_ADDRESS,
            email=None,
            password=None,
        )
    except Exception:
        return None
