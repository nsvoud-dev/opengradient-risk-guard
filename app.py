"""
Verifiable DeFi Risk Guard — Web Dashboard (Streamlit).

Cybersecurity-style UI: risk gauge, technical proof panel, recent scans from MemSync.
Hybrid Mode: Demo when balance is 0, Live when funded.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import plotly.graph_objects as go

from run_risk_guard import (
    get_opg_token_balance,
    run_demo_mode,
    DEMO_MODE_REASON,
)
from src.defi_risk_guard import (
    DeFiRiskGuard,
    _load_client,
    _run_local_onnx_inference,
    DEFAULT_RISK_MODEL_CID,
    RiskCheckResult,
)
from src.memory import MemSyncClient

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Verifiable DeFi Risk Guard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Cybersecurity theme CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
    /* Base */
    .stApp { background: linear-gradient(180deg, #0a0e17 0%, #0d1117 50%, #0a0e17 100%); }
    [data-testid="stHeader"] { background: rgba(10, 14, 23, 0.9); }
    h1, h2, h3 { color: #00ff88 !important; font-family: 'JetBrains Mono', 'Consolas', monospace !important; }
    p, label, span { color: #c9d1d9 !important; }
    
    /* Glowing proof box */
    .proof-valid {
        padding: 1rem 1.25rem;
        border-radius: 8px;
        border: 1px solid #00ff8844;
        background: linear-gradient(135deg, #00ff8811 0%, #00ff8806 100%);
        box-shadow: 0 0 20px rgba(0, 255, 136, 0.25);
        margin: 0.5rem 0;
        font-family: 'JetBrains Mono', monospace;
    }
    .proof-invalid {
        padding: 1rem 1.25rem;
        border-radius: 8px;
        border: 1px solid #ff444444;
        background: linear-gradient(135deg, #ff444411 0%, #ff444406 100%);
        box-shadow: 0 0 20px rgba(255, 68, 68, 0.25);
        margin: 0.5rem 0;
        font-family: 'JetBrains Mono', monospace;
    }
    .proof-label { color: #8b949e; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .proof-value { color: #00ff88; font-size: 0.95rem; word-break: break-all; }
    .proof-value-invalid { color: #ff6b6b; }
    
    /* Demo mode banner */
    .demo-banner {
        padding: 0.6rem 1rem;
        border-radius: 6px;
        background: linear-gradient(90deg, #ffa50022 0%, #ff8c0022 100%);
        border: 1px solid #ffa50055;
        color: #ffa500;
        font-family: monospace;
        font-size: 0.9rem;
        margin-bottom: 1.5rem;
    }
    .live-banner {
        padding: 0.6rem 1rem;
        border-radius: 6px;
        background: linear-gradient(90deg, #00ff8844 0%, #00ff6644 100%);
        border: 2px solid #00ff88;
        color: #00ff88;
        font-family: monospace;
        font-size: 0.95rem;
        font-weight: 700;
        margin-bottom: 1.5rem;
        box-shadow: 0 0 16px rgba(0, 255, 136, 0.4);
    }
    
    /* Scan button */
    .stButton > button {
        background: linear-gradient(135deg, #00ff88 0%, #00cc6a 100%) !important;
        color: #0a0e17 !important;
        font-weight: 700 !important;
        border: none !important;
        padding: 0.6rem 2rem !important;
        border-radius: 6px !important;
        font-family: monospace !important;
    }
    .stButton > button:hover {
        box-shadow: 0 0 20px rgba(0, 255, 136, 0.5) !important;
    }
    
    /* Table container */
    [data-testid="stDataFrame"] { border: 1px solid #30363d; border-radius: 8px; }
    
    /* Input */
    .stTextInput input { background: #161b22 !important; border: 1px solid #30363d !important; color: #c9d1d9 !important; }
    
    /* Warning box (account init required) */
    .warning-box {
        padding: 1rem 1.25rem;
        border-radius: 8px;
        border: 1px solid #ffa50055;
        background: linear-gradient(135deg, #ffa50018 0%, #ff8c0012 100%);
        color: #ffa500;
        font-family: monospace;
        font-size: 0.9rem;
        margin: 1rem 0;
    }
    .status-ok { color: #00ff88; }
    .status-fail { color: #ff4444; }

    /* Local inference fallback banner */
    .fallback-banner {
        padding: 0.6rem 1rem;
        border-radius: 6px;
        background: linear-gradient(90deg, #7b2fff22 0%, #5500ff18 100%);
        border: 1px solid #7b2fff88;
        color: #b084ff;
        font-family: monospace;
        font-size: 0.9rem;
        margin: 0.75rem 0 0.25rem 0;
        letter-spacing: 0.02em;
    }
</style>
""", unsafe_allow_html=True)

# ─── Session state ───────────────────────────────────────────────────────────
if "recent_scans" not in st.session_state:
    st.session_state.recent_scans = []
if "is_demo_mode" not in st.session_state:
    st.session_state.is_demo_mode = None  # None = not yet detected
if "guard" not in st.session_state:
    st.session_state.guard = None
if "memsync" not in st.session_state:
    st.session_state.memsync = None
if "inference_error" not in st.session_state:
    st.session_state.inference_error = None  # Set to str message when "account does not exist" etc.
if "og_devnet_native_ok" not in st.session_state:
    st.session_state.og_devnet_native_ok = None  # True = has native OG on devnet


def ensure_guard():
    """Load client, detect demo/live from $OPG token balance (Base Sepolia), build guard and memsync once."""
    if st.session_state.guard is not None and st.session_state.is_demo_mode is not None:
        return
    client = _load_client()
    if client is None:
        st.session_state.is_demo_mode = True
        st.session_state.guard = None
        st.session_state.og_devnet_native_ok = False
        return
    # Use $OPG token balance on Base Sepolia to decide live vs demo
    wallet_addr = client._wallet_account.address
    balance = get_opg_token_balance(wallet_addr)
    st.session_state.is_demo_mode = balance == 0
    # OG Devnet native balance (needed for inference; separate from $OPG on Base Sepolia)
    try:
        native_balance = client._blockchain.eth.get_balance(wallet_addr)
        st.session_state.og_devnet_native_ok = native_balance > 0
    except Exception:
        st.session_state.og_devnet_native_ok = False
    memsync = None
    try:
        m = MemSyncClient()
        if m.api_key:
            memsync = m
    except Exception:
        pass
    st.session_state.memsync = memsync
    st.session_state.guard = DeFiRiskGuard(client=client, memsync=memsync)


def run_scan(address: str) -> RiskCheckResult | None:
    """Run risk guard logic (demo or live); return RiskCheckResult or None on error."""
    ensure_guard()
    guard = st.session_state.guard
    addr = (address or "").strip()
    if not addr.startswith("0x"):
        addr = "0x" + addr
    if len(addr) != 42:
        st.warning("Please enter a valid 0x-prefixed 40-hex address.")
        return None

    # No client: pure in-app demo (fake score + fake tx, SIMULATED VALID)
    if guard is None:
        raw = hashlib.sha256(addr.lower().encode()).digest()
        risk_score = round((raw[0] / 255.0) * 0.5 + (raw[1] / 255.0) * 0.5, 4)
        risk_score = max(0.0, min(1.0, risk_score))
        fake_tx = "0x" + hashlib.sha256(raw + addr.encode()).hexdigest()
        result = RiskCheckResult(
            risk_score=risk_score,
            model_id=DEFAULT_RISK_MODEL_CID,
            verification_status="SIMULATED VALID",
            transaction_hash=fake_tx,
        )
    else:
        is_demo = st.session_state.is_demo_mode
        if is_demo:
            result = run_demo_mode(addr, guard, DEFAULT_RISK_MODEL_CID)
        else:
            try:
                result = guard.check_address(addr)
            except Exception as e:
                err_msg = str(e).lower()
                if "does not exist" in err_msg and "inference" in err_msg:
                    st.session_state.inference_error = (
                        "Account Initialization Required: Your address is not yet registered on the OpenGradient Devnet. "
                        "Please request a small amount of native OG gas from the faucet or a team member."
                    )
                    st.session_state.og_devnet_native_ok = False
                    return None
                # Last-resort safety net: if the error is inference/event-related,
                # run local ONNX instead of showing a red error to the user.
                import re
                exc_str = str(e)
                is_inference_event_err = any(
                    kw in err_msg for kw in ("inferencere", "event not found", "transaction logs", "network fallback")
                )
                if is_inference_event_err:
                    tx_match = re.search(r'0x[0-9a-fA-F]{64}', exc_str)
                    tx_hash = tx_match.group(0) if tx_match else ""
                    print(
                        f"[app.py safety net] On-chain event failed, attempting local fallback...\n"
                        f"  reason : {exc_str[:200]}\n"
                        f"  tx_hash: {tx_hash or '(unknown)'}"
                    )
                    risk_score = _run_local_onnx_inference(addr)
                    result = RiskCheckResult(
                        risk_score=risk_score,
                        model_id=DEFAULT_RISK_MODEL_CID,
                        verification_status="LOCAL FALLBACK",
                        transaction_hash=tx_hash,
                        is_local_fallback=True,
                    )
                else:
                    st.error(exc_str)
                    return None

    # Append to recent scans
    row = {
        "Address": addr,
        "Risk Score": result.risk_score,
        "Verification": result.verification_status,
        "Model ID": result.model_id[:16] + "…" if len(result.model_id) > 16 else result.model_id,
        "Tx Hash": result.transaction_hash[:18] + "…" if len(result.transaction_hash) > 18 else result.transaction_hash,
        "_full_tx": result.transaction_hash,
        "_full_model": result.model_id,
    }
    st.session_state.recent_scans.insert(0, row)
    if len(st.session_state.recent_scans) > 50:
        st.session_state.recent_scans = st.session_state.recent_scans[:50]
    return result


def risk_gauge(score: float):
    """Speedometer-style gauge 0–100%. Uses 6-digit hex / rgba for Plotly compatibility."""
    pct = max(0, min(1, score)) * 100
    if pct <= 33:
        bar_color = "#00ff88"
    elif pct <= 66:
        bar_color = "#ffa500"
    else:
        bar_color = "#ff4444"
    # Step colors: 6-digit hex (Plotly gauge steps do not support 8-digit hex with alpha)
    step_low = "#0d3322"
    step_mid = "#332a00"
    step_high = "#331111"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pct,
        number={"suffix": "%", "font": {"size": 36}, "valueformat": ".1f"},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#30363d"},
            "bar": {"color": bar_color, "thickness": 0.75},
            "bgcolor": "#161b22",
            "borderwidth": 2,
            "bordercolor": "#30363d",
            "steps": [
                {"range": [0, 33], "color": step_low},
                {"range": [33, 66], "color": step_mid},
                {"range": [66, 100], "color": step_high},
            ],
            "threshold": {
                "line": {"color": "#c9d1d9", "width": 2},
                "thickness": 0.8,
                "value": pct,
            },
        },
        title={"text": "Risk Score", "font": {"size": 18, "color": "#8b949e"}},
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=50, b=20),
        height=280,
        font={"color": "#c9d1d9", "family": "Consolas, monospace"},
    )
    return fig


def render_proof(result: RiskCheckResult):
    """Technical Proof section with glowing green/red box."""
    is_local = getattr(result, "is_local_fallback", False)
    is_valid = "VALID" in result.verification_status and not is_local
    box_class = "proof-valid" if is_valid else "proof-invalid"
    value_class = "proof-value" if is_valid else "proof-value proof-value-invalid"
    st.markdown(f"""
    <div class="{box_class}">
        <div class="proof-label">Verification Status</div>
        <div class="{value_class}">{result.verification_status}</div>
        <div class="proof-label" style="margin-top: 0.75rem;">Model ID</div>
        <div class="{value_class}">{result.model_id}</div>
        <div class="proof-label" style="margin-top: 0.75rem;">Transaction Hash</div>
        <div class="{value_class}">{result.transaction_hash}</div>
    </div>
    """, unsafe_allow_html=True)
    if is_local:
        st.markdown(
            '<div class="fallback-banner">'
            '⚠ Result: Local Inference (Network Fallback) — '
            'InferenceResult event was not confirmed on-chain within 10 s. '
            'The risk score was computed locally using the downloaded .onnx model.'
            '</div>',
            unsafe_allow_html=True,
        )


def get_memsync_recent() -> list[dict]:
    """Fetch recent risk profiles from MemSync for the table."""
    guard = st.session_state.guard
    memsync = st.session_state.memsync
    if guard is None or memsync is None or not getattr(memsync, "api_key", None):
        return []
    try:
        r = guard.cluster_risk_profiles(query="DeFi risk profile address verification transaction", limit=20)
        return r or []
    except Exception:
        return []


# ─── Sidebar: Network Status ──────────────────────────────────────────────────
ensure_guard()
is_demo = st.session_state.is_demo_mode
og_ok = st.session_state.og_devnet_native_ok

with st.sidebar:
    st.sidebar.header("Network Status")
    base_sepolia_label = "Base Sepolia ($OPG):"
    base_sepolia_status = "Detected" if (is_demo is False) else "Not detected"
    base_color = "status-ok" if (is_demo is False) else "status-fail"
    st.markdown(f'<span class="{base_color}">{base_sepolia_label} {base_sepolia_status}</span>', unsafe_allow_html=True)
    og_devnet_label = "OG Devnet (Native):"
    og_devnet_status = "Detected" if og_ok else "Not Initialized"
    og_color = "status-ok" if og_ok else "status-fail"
    st.markdown(f'<span class="{og_color}">{og_devnet_label} {og_devnet_status}</span>', unsafe_allow_html=True)

# ─── Main UI ──────────────────────────────────────────────────────────────────
st.title("🛡️ Verifiable DeFi Risk Guard")
st.caption("On-chain proof verification · Probabilistic risk assessment · Decentralized MemSync analytics")

if st.session_state.get("inference_error"):
    st.markdown(
        f'<div class="warning-box">{st.session_state.inference_error}</div>',
        unsafe_allow_html=True,
    )
    if st.button("Retry", key="retry_inference_error"):
        st.session_state.inference_error = None
        st.rerun()

if is_demo is True:
    st.markdown(f'<div class="demo-banner">[DEMO MODE: REASON - {DEMO_MODE_REASON}] — Simulated inference; no chain calls. Fund wallet for live verification.</div>', unsafe_allow_html=True)
elif is_demo is False:
    st.markdown('<div class="live-banner">[LIVE ON-CHAIN MODE] — $OPG token detected on Base Sepolia. Verifiable inference and on-chain proof verification active.</div>', unsafe_allow_html=True)

col_inp, col_btn = st.columns([4, 1])
with col_inp:
    address = st.text_input(
        "Wallet Address",
        value="0x4Fa0f435e736A04D7da547E681ce092a427D6205",
        placeholder="0x...",
        key="address",
    )
with col_btn:
    st.write("")
    st.write("")
    scan_clicked = st.button("🔍 Scan", type="primary", use_container_width=True)

result = None
if scan_clicked and address:
    with st.spinner("Running risk assessment…"):
        result = run_scan(address)

if result is not None:
    st.markdown("---")
    col_gauge, col_proof = st.columns([1, 1])
    with col_gauge:
        st.plotly_chart(risk_gauge(result.risk_score), use_container_width=True)
    with col_proof:
        st.subheader("Technical Proof")
        render_proof(result)

st.markdown("---")
st.subheader("Recent Scans")

# Table: prefer session state rows; optionally merge MemSync rows for display
table_data = []
for row in st.session_state.recent_scans:
    table_data.append({
        "Address": row["Address"],
        "Risk Score": row["Risk Score"],
        "Verification": row["Verification"],
        "Model ID": row["Model ID"],
        "Tx Hash": row["Tx Hash"],
    })
if table_data:
    st.dataframe(table_data, use_container_width=True, hide_index=True)
else:
    # Try MemSync for any existing data
    memsync_rows = get_memsync_recent()
    if memsync_rows:
        rows = []
        for m in memsync_rows:
            mem = m.get("memory", "") if isinstance(m, dict) else str(m)
            rows.append({"Memory": mem[:80] + "…" if len(mem) > 80 else mem})
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No scans yet. Enter an address and click **Scan** to run a risk check (demo or live).")
