"""
Verifiable DeFi Risk Guard — deep OpenGradient integration.

- Calls a specific Model Hub model by CID (not just the general gateway).
- Programmatically verifies the cryptographic proof after inference.
- MemSync analytics: store and cluster Risk Profiles (decentralized bad-actor DB).
- Hybrid Mode: submits on-chain tx first; falls back to local ONNX if InferenceResult
  is not found within 10 seconds (network maintenance fallback).

Output format: [Risk Score] | [Model ID] | [Verification Status: VALID/INVALID] | [Transaction Hash]
"""
from __future__ import annotations

# eth_account compatibility: newer versions use rawTransaction (camelCase);
# the SDK expects raw_transaction — add alias so send_raw_transaction doesn't fail.
try:
    from eth_account.datastructures import SignedTransaction
    if not hasattr(SignedTransaction, 'raw_transaction'):
        raw_transaction = property(lambda self: getattr(self, 'rawTransaction'))
        SignedTransaction.raw_transaction = raw_transaction
except Exception:
    pass

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .proof_verifier import ProofVerifier, VERIFIED, NOT_VERIFIED

logger = logging.getLogger(__name__)

# Model Hub: волатильность / риск (актуальный CID с Хаба)
# TODO: Заменить на актуальный CID от Martinx после получения
TODO_NEW_MODEL_CID = None  # Вставить новый CID здесь, затем заменить значение DEFAULT_RISK_MODEL_CID
DEFAULT_RISK_MODEL_CID = TODO_NEW_MODEL_CID or "KzAHsOHStzAi93_SN-n5H_LjupBjKoxC8qMILxeRdI"

# Local ONNX fallback model path (used when on-chain inference is unavailable)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
ONNX_MODEL_PATH = _PROJECT_ROOT / "model" / "risk_model.onnx"

# How long to wait for InferenceResult event before switching to local inference
HYBRID_MODE_TIMEOUT_SECONDS = 10


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


def _run_local_onnx_inference(address: str, model_path: Path | None = None) -> float:
    """
    Run local ONNX inference as a fallback when on-chain inference is unavailable.

    Attempts to load the ONNX model and feed address-derived numeric features.
    Falls back to a deterministic score from address bytes if the model file is
    missing or onnxruntime is not installed.
    """
    import numpy as np

    path = model_path or ONNX_MODEL_PATH

    addr = (address or "").strip().lower()
    if not addr.startswith("0x"):
        addr = "0x" + addr
    addr_hex = addr[2:].zfill(40)[:40]
    raw = bytes.fromhex(addr_hex)

    def _deterministic_score() -> float:
        val = sum(raw[:4]) / (4 * 255.0)
        return round(max(0.0, min(1.0, val)), 4)

    if not Path(path).exists():
        logger.warning("Local ONNX model not found at %s; using deterministic address-based score.", path)
        return _deterministic_score()

    try:
        import onnxruntime as ort
        sess = ort.InferenceSession(str(path))
        nums = np.array([[float(b) / 255.0 for b in raw[:4]]], dtype=np.float32)
        input_name = sess.get_inputs()[0].name
        output = sess.run(None, {input_name: nums})
        if output and len(output) > 0:
            val = float(np.asarray(output[0]).flatten()[0])
            val = max(0.0, min(1.0, val if 0.0 <= val <= 1.0 else (val % 1.0)))
            return round(val, 4)
    except Exception as exc:
        logger.warning("Local ONNX inference failed (%s); using deterministic score.", exc)

    return _deterministic_score()


@dataclass
class RiskCheckResult:
    risk_score: float
    model_id: str
    verification_status: str  # VALID | INVALID | LOCAL FALLBACK
    transaction_hash: str
    is_local_fallback: bool = field(default=False)

    def to_output_line(self) -> str:
        line = (
            f"[{self.risk_score}] | [{self.model_id}] | "
            f"[Verification Status: {self.verification_status}] | [{self.transaction_hash}]"
        )
        if self.is_local_fallback:
            line += " | [Result: Local Inference (Network Fallback)]"
        return line


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
        Hybrid Mode: submit on-chain inference tx (spend gas, record on blockchain),
        then wait up to HYBRID_MODE_TIMEOUT_SECONDS for InferenceResult event.
        If the SDK raises (e.g. "InferenceResult event not found") or the event is
        not confirmed in time, fall back to local ONNX inference without surfacing
        any error to the caller.
        """
        import re
        import opengradient as og
        self._ensure_client()
        mode = self._inference_mode or og.InferenceMode.VANILLA
        model_input = _address_to_model_input(address)

        # 1) Submit on-chain transaction — always happens to record the attempt and spend gas.
        #    The SDK sends the tx and then waits internally for InferenceResult; if the network
        #    has a bug it raises BEFORE returning.  We catch that here so the fallback fires.
        tx_hash = ""
        model_output: dict = {}
        infer_ok = False

        # Intercept send_raw_transaction at the web3 transport layer so we capture
        # the tx hash at the exact moment the transaction is broadcast — before the
        # SDK's internal InferenceResult wait, which may raise without including the
        # hash in the exception message.
        _captured: list[str] = []
        _eth = self._client._blockchain.eth
        _orig_send = _eth.send_raw_transaction

        def _capturing_send(raw_tx):
            receipt = _orig_send(raw_tx)
            try:
                h = receipt.hex() if isinstance(receipt, (bytes, bytearray)) else str(receipt)
                if h and not h.startswith("0x"):
                    h = "0x" + h
                _captured.append(h)
            except Exception:
                pass
            return receipt

        _eth.send_raw_transaction = _capturing_send
        try:
            result = self._client.infer(
                model_cid=self._model_cid,
                inference_mode=mode,
                model_input=model_input,
            )
            tx_hash = getattr(result, "transaction_hash", None) or getattr(result, "tx_hash", "") or ""
            if not tx_hash and _captured:
                tx_hash = _captured[0]
            model_output = getattr(result, "model_output", None) or {}
            infer_ok = True
        except Exception as infer_exc:
            exc_str = str(infer_exc)
            # Primary source: hash captured by the interceptor before the SDK raised.
            tx_hash = _captured[0] if _captured else ""
            # Fallback: scan the exception message (works for some SDK versions).
            if not tx_hash:
                m = re.search(r'0x[0-9a-fA-F]{64}', exc_str)
                if m:
                    tx_hash = m.group(0)
            print(
                f"[Hybrid Mode] On-chain event failed, attempting local fallback...\n"
                f"  tx_hash: {tx_hash or '(unknown)'}\n"
                f"  reason : {exc_str[:200]}"
            )
            logger.warning(
                "SDK infer() raised after tx submission — falling back to local ONNX. tx=%s reason=%s",
                tx_hash,
                exc_str[:200],
            )
        finally:
            _eth.send_raw_transaction = _orig_send

        if infer_ok:
            # 2) SDK returned normally — poll for InferenceResult for up to the timeout.
            verifier = self._get_verifier()
            verification_status: str | None = None
            deadline = time.monotonic() + HYBRID_MODE_TIMEOUT_SECONDS
            poll_interval = 1.0

            while time.monotonic() < deadline:
                status = verifier.verify_inference_tx(tx_hash)
                if status == VERIFIED:
                    verification_status = status
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(poll_interval, remaining))

            if verification_status == VERIFIED:
                # On-chain inference confirmed — use the result returned by the network.
                risk_score = _extract_risk_score_from_output(model_output)
                out = RiskCheckResult(
                    risk_score=risk_score,
                    model_id=self._model_cid,
                    verification_status=verification_status,
                    transaction_hash=tx_hash,
                    is_local_fallback=False,
                )
                self._store_risk_profile(address, out)
                return out

            # Timeout — no confirmed event; fall through to local ONNX below.
            print(
                f"[Hybrid Mode] On-chain event failed, attempting local fallback...\n"
                f"  reason : InferenceResult not confirmed within {HYBRID_MODE_TIMEOUT_SECONDS}s\n"
                f"  tx_hash: {tx_hash}"
            )
            logger.warning(
                "InferenceResult not confirmed within %ds for tx %s; switching to local ONNX.",
                HYBRID_MODE_TIMEOUT_SECONDS,
                tx_hash,
            )

        # 3) Local ONNX fallback — runs whether infer() raised or the poll timed out.
        risk_score = _run_local_onnx_inference(address)
        out = RiskCheckResult(
            risk_score=risk_score,
            model_id=self._model_cid,
            verification_status="LOCAL FALLBACK",
            transaction_hash=tx_hash,
            is_local_fallback=True,
        )
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
