# Verifiable DeFi Risk Guard  
## Technical Whitepaper

**OpenGradient ALPHA OG — Verifiable Inference & Decentralized Risk Analytics**

---

### Abstract

This document describes the **Verifiable DeFi Risk Guard**: a system that combines **cryptographic attestation** of AI inference with **probabilistic risk assessment** and a **decentralized**, **vectorized semantic memory** layer for risk analytics. The Guard executes inference on OpenGradient’s Model Hub, performs programmatic **mathematical verification** of on-chain proofs, and persists risk profiles in MemSync’s long-term, semantically searchable store. The design emphasizes verifiability, decentralization, and reproducible risk scoring.

---

## 1. Introduction

The Verifiable DeFi Risk Guard addresses the need for **trustworthy, auditable** risk scoring in decentralized finance. It does so by:

1. **Verifiable inference** — Running a designated risk model on OpenGradient’s infrastructure and obtaining an on-chain commitment of the execution.
2. **Proof verification** — Programmatically validating that the inference result is backed by a successful transaction and the appropriate contract event (**InferenceResult**), providing **cryptographic attestation** of the computation.
3. **Probabilistic risk assessment** — Deriving a normalized risk score from the model’s output and exposing it in a fixed, auditable format.
4. **Decentralized risk memory** — Storing and querying risk profiles via MemSync, which uses **vectorized semantic memory** for retrieval and clustering, forming a shared, non-custodial view of address risk.

The output of each check is a single canonical line:

`[Risk Score] | [Model ID] | [Verification Status: VALID / INVALID / SIMULATED VALID] | [Transaction Hash]`

enabling downstream systems to trust or reject results based on **verification status** and **transaction hash**.

---

## 2. Mathematical Verification of AI Proofs

Verification is implemented at the **protocol level**, not as a high-level API convenience. The system treats the blockchain as the source of truth.

### 2.1 On-Chain Commitment

Inference is executed via the OpenGradient inference contract. A successful run:

1. Emits an **InferenceResult** event (or, for LLM paths, **LLMCompletionResult** / **LLMChatResult**) containing the inference identifier and output commitment.
2. Produces a **transaction receipt** with `status = 1` (success).

The **transaction hash** uniquely identifies the execution and allows anyone to recompute the verification steps off-chain.

### 2.2 Verification Algorithm

The **ProofVerifier** implements the following deterministic procedure:

1. **Fetch receipt:**  
   `receipt ← get_transaction_receipt(tx_hash)`

2. **Existence and success:**  
   Reject if `receipt = ⊥` or `receipt.status ≠ 1`.

3. **Event consistency:**  
   Parse the contract logs for the relevant event (e.g. **InferenceResult**).  
   Reject if no such event is present.

4. **Outcome:**  
   Return **VALID** if and only if all checks pass; otherwise **INVALID**.

This gives a **mathematical guarantee**: a **VALID** status implies that the chain records a successful inference for the given `tx_hash`. No reliance is placed on off-chain APIs for the verification result; only the chain and the contract ABI are used.

### 2.3 Cryptographic Attestation

OpenGradient’s infrastructure can provide **cryptographic attestation** (e.g. TEE-based) of inference execution. The Guard’s on-chain verification is **compliant** with that model: the emitted event and receipt form a verifiable commitment that can be correlated with attestation evidence. Thus, the Guard supports a **verifiable pipeline** from model invocation to risk score and proof status.

---

## 3. Probabilistic Risk Assessment

Risk is expressed as a **normalized score** in the interval [0, 1], suitable for **probabilistic risk assessment** and policy thresholds.

- **Model invocation:** A specific Model Hub model (by **content identifier**, CID) is invoked with inputs derived from the target address. The Guard uses the OpenGradient SDK’s `infer(model_cid, inference_mode, model_input)` path—not the generic LLM gateway—ensuring a fixed, auditable model and execution environment.

- **Score extraction:** The model’s output is a structured tensor map. The Guard derives a scalar **risk score** by taking the first available numeric output, normalizing and clamping it to [0, 1], and rounding to a fixed precision. This yields a **deterministic** score for a given model and input.

- **Interpretation:** The score can be interpreted as a **probability or severity** in downstream logic (e.g. thresholds for flagging, tiering, or circuit breakers). The same line format ensures that **Model ID** and **Transaction Hash** are always available for audit and reproducibility.

---

## 4. Decentralized Storage and Vectorized Semantic Memory

Risk profiles are persisted and retrieved through **MemSync**, which provides a **decentralized**, long-term memory layer built on OpenGradient’s verifiable inference and embeddings infrastructure.

### 4.1 Decentralized Nature of MemSync

MemSync is not a single centralized database. It is designed to leverage OpenGradient’s decentralized network for:

- **Verifiable embeddings** — Semantic representations used for search are produced by infrastructure that can be attested.
- **Censorship resistance** — No single operator can unilaterally erase or alter the shared memory.
- **Transparency** — Memory operations can be tied to verifiable inference and on-chain or attestation records where applicable.

The Guard treats MemSync as the **canonical store** for risk profiles and cluster-level analytics, contributing to a **decentralized database of risk-relevant signals** (e.g. address risk history, clustering of high-risk entities).

### 4.2 Vectorized Semantic Memory

MemSync organizes stored content in a **vectorized semantic memory**:

- **Embedding:** Ingested messages (e.g. risk profile summaries) are embedded into a vector space.
- **Retrieval:** Queries are embedded in the same space; retrieval is by **semantic similarity** (e.g. nearest-neighbor search), not only exact key lookup.
- **Clustering:** Profiles can be retrieved by conceptual queries (e.g. “high risk score”, “address X”) and grouped by similarity, enabling **cluster-based analytics** and trend analysis.

The Guard **stores** each risk check as a structured profile (address, risk score, model ID, verification status, transaction hash) and **queries** by address or by risk semantics (e.g. high-risk cluster), demonstrating the use of **vectorized semantic memory** for a decentralized risk database.

---

## 5. System Architecture and Implementation

### 5.1 Output Specification

Every risk check produces exactly one line:

```
[Risk Score] | [Model ID] | [Verification Status: VALID|INVALID|SIMULATED VALID] | [Transaction Hash]
```

- **Risk Score:** Normalized value in [0, 1].  
- **Model ID:** Content identifier (CID) of the Model Hub model used.  
- **Verification Status:** **VALID** (on-chain verification passed), **INVALID** (verification failed), or **SIMULATED VALID** (demo mode, no chain).  
- **Transaction Hash:** On-chain tx hash, or a deterministic placeholder in demo mode.

### 5.2 Component Overview

| Component | Role |
|-----------|------|
| **ProofVerifier** | Low-level proof verification: receipt fetch, status check, **InferenceResult** (and LLM) event parsing. Returns VALID / INVALID / SIMULATED VALID. |
| **DeFiRiskGuard** | Orchestration: Model Hub `infer()` by CID, risk score extraction, proof verification, MemSync store and semantic search/cluster. |
| **MemSync client** | Store risk profiles; query by address or semantic query for **vectorized semantic memory** analytics. |

### 5.3 Module Layout

- `src/proof_verifier.py` — On-chain proof verification (receipt + event validation).  
- `src/defi_risk_guard.py` — DeFi Risk Guard (Model Hub inference, verification, MemSync analytics).  
- `src/memory.py` — MemSync client (store and semantic search).  
- `src/config.py` — Environment and defaults.  
- `src/llm.py` — OpenGradient LLM (x402) for auxiliary agents.  
- `src/agent.py` — OGChronosAgent (think, remember, retrieve_context).  
- `src/cli.py` — CLI for chat agent.  
- `src/errors.py` — Structured errors (e.g. insufficient funds, memory, LLM).

---

## 6. Operational Modes

### 6.1 Live Mode

When the configured wallet has a non-zero balance:

1. Client connects to OpenGradient (local config or `OPENGRADIENT_PRIVATE_KEY`).  
2. **Model Hub** inference is executed for the given address; **transaction hash** and **model output** are obtained.  
3. **ProofVerifier** runs the verification algorithm; status is **VALID** or **INVALID**.  
4. Risk profile is written to MemSync (when **MEMSYNC_API_KEY** is set).

### 6.2 Demo Mode (Zero Balance)

When the wallet balance is zero, the Guard runs a **full simulation**:

1. Console prints: **`[DEMO MODE: REASON - ZERO BALANCE]`**.  
2. Inference is **simulated** (no chain call); a deterministic fake risk score and fake transaction hash are produced.  
3. **ProofVerifier.verify_inference_tx_simulated()** returns **SIMULATED VALID**.  
4. The same output line format is used, with **Verification Status: SIMULATED VALID**.

This allows demonstration of the UI and logic without testnet tokens.

---

## 7. Setup and Usage

### 7.1 Environment

```bash
cp .env.example .env
# Set MEMSYNC_API_KEY (https://app.memsync.ai/dashboard/api-keys)
# Optional: OPENGRADIENT_PRIVATE_KEY or use opengradient config
```

### 7.2 Wallet and Dependencies

- **$OPG** testnet tokens on **Base Sepolia** (Chain ID 84532); faucet: https://faucet.opengradient.ai/  
- Set `OPENGRADIENT_PRIVATE_KEY` in `.env` or run:

  ```bash
  pip install opengradient
  opengradient config init
  ```

- Install project dependencies:

  ```bash
  pip install -r requirements.txt
  ```

### 7.3 Running the Risk Guard

```bash
python run_risk_guard.py [address]
python run_risk_guard.py 0x4Fa0f435e736A04D7da547E681ce092a427D6205
```

### 7.4 Optional: Persistent Chat Agent

```bash
python -m src.cli          # with MemSync
python -m src.cli --no-memory
```

Commands: `/quit`, `/thread <id>`, `/clear`.

### 7.5 Web Dashboard (Streamlit)

Cybersecurity-style UI: risk gauge, technical proof panel, recent scans. Hybrid mode (demo when balance is 0).

**Libraries to install:**

```bash
pip install streamlit plotly
# or install all project deps (includes streamlit, plotly):
pip install -r requirements.txt
```

**Launch the web app:**

```bash
streamlit run app.py
```

Then open the URL shown in the terminal (e.g. http://localhost:8501). Works in **Demo Mode** without tokens or MemSync.

---

## 8. References

- [OpenGradient SDK](https://docs.opengradient.ai/developers/sdk/)  
- [Verifiable LLM Execution](https://docs.opengradient.ai/learn/onchain_inference/llm_execution.html)  
- [MemSync — Long-Term Memory Layer](https://docs.opengradient.ai/developers/memsync/)  
- [x402 Gateway](https://docs.opengradient.ai/developers/x402/)  
- [LangChain OpenGradient Integration](https://python.langchain.com/docs/integrations/providers/opengradient/)

---

*Verifiable DeFi Risk Guard — OpenGradient ALPHA OG. Mathematical verification of AI proofs; decentralized, vectorized semantic memory for risk analytics.*
