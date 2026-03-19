"""
Verifiable DeFi Risk Guard — Web Dashboard (Streamlit).

OpenGradient high-tech theme: deep dark, teal/cyan accents, Space Mono typography,
card-based layout, custom HTML table for Recent Scans.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

# ── Streamlit Cloud: inject secrets into os.environ ───────────────────────────
# Must run before any src.* import so that src/config.py (which reads os.environ)
# already sees the cloud secrets when it is first loaded.
def _bootstrap_cloud_secrets() -> None:
    _KEYS = (
        "OPENGRADIENT_PRIVATE_KEY",
        "OPENGRADIENT_RPC_URL",
        "OPENGRADIENT_CHAIN_ID",
        "MEMSYNC_API_KEY",
        "AGENT_ID",
        "DEFAULT_THREAD_ID",
    )
    try:
        for key in _KEYS:
            if key in st.secrets and not os.environ.get(key):
                os.environ[key] = str(st.secrets[key])
    except Exception:
        pass

_bootstrap_cloud_secrets()

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

# ─── Constants ────────────────────────────────────────────────────────────────
OG_EXPLORER_TX = "https://explorer.opengradient.ai/tx"

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DeFi Risk Guard · OpenGradient",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Logo ─────────────────────────────────────────────────────────────────────
# Load the real OG logo (image_12.png) and embed as base64 data URI so it works
# locally and on Streamlit Cloud without any static file serving.
def _load_logo_b64(size: int = 64) -> str:
    """Return an <img> tag with the OG logo embedded as a base64 data URI."""
    logo_path = PROJECT_ROOT / "image_12.png"
    if logo_path.exists():
        with open(logo_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        return (
            f'<img src="data:image/png;base64,{b64}" '
            f'width="{size}" height="{size}" '
            f'style="display:block;flex-shrink:0;'
            f'image-rendering:crisp-edges;" alt="OpenGradient logo">'
        )
    return ""  # graceful no-op if file is missing

_ICON_NET = """
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00E5FF"
     stroke-width="1.8" stroke-linecap="round" xmlns="http://www.w3.org/2000/svg">
  <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4"/>
  <line x1="12" y1="2" x2="12" y2="8"/><line x1="12" y1="16" x2="12" y2="22"/>
  <line x1="2" y1="12" x2="8" y2="12"/><line x1="16" y1="12" x2="22" y2="12"/>
</svg>"""

_ICON_SHIELD = """
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00E5FF"
     stroke-width="1.8" stroke-linecap="round" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
  <polyline points="9 12 11 14 15 10"/>
</svg>"""

_ICON_EYE = """
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
     stroke-width="1.8" stroke-linecap="round" xmlns="http://www.w3.org/2000/svg">
  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>"""

_ICON_SCAN = """
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00E5FF"
     stroke-width="1.8" stroke-linecap="round" xmlns="http://www.w3.org/2000/svg">
  <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
  <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
</svg>"""

# ─── Global CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500&display=swap');

/* ── Base ─────────────────────────────────────────────────────────────────── */
.stApp                   { background: #0A0E13 !important; }
[data-testid="stHeader"] {
    background: rgba(10, 14, 19, 0.98) !important;
    border-bottom: 1px solid rgba(0, 229, 255, 0.1);
}
[data-testid="stSidebar"] {
    background: #0C1017 !important;
    border-right: 1px solid rgba(0, 229, 255, 0.1);
}
[data-testid="stSidebar"] > div { padding-top: 1rem; }

/* Ensure the main content area is never clipped and has enough breathing room
   below Streamlit's fixed top bar (≈ 3.5 rem tall). */
.block-container {
    padding-top: 3.5rem !important;
    overflow: visible !important;
    max-width: 100% !important;
}
section[data-testid="stMain"]      { background: #0A0E13 !important; overflow: visible !important; }
[data-testid="stAppViewContainer"] { overflow: visible !important; }

/* ── Typography ───────────────────────────────────────────────────────────── */
h1, h2, h3, h4 {
    font-family: 'Space Mono', monospace !important;
    color: #00E5FF !important;
    letter-spacing: -0.01em;
}
p, label, span, li { font-family: 'Inter', sans-serif; color: #C9D1D9; }

/* ── Cards ────────────────────────────────────────────────────────────────── */
.og-card {
    background: rgba(13, 17, 23, 0.85);
    border: 1px solid rgba(0, 229, 255, 0.18);
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin: 0.5rem 0;
}
.og-card-hdr {
    font-family: 'Space Mono', monospace;
    font-size: 0.62rem;
    color: rgba(0, 229, 255, 0.6);
    text-transform: uppercase;
    letter-spacing: 0.18em;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.og-card-hdr-line {
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, rgba(0,229,255,0.25) 0%, transparent 100%);
}

/* ── Network status rows ──────────────────────────────────────────────────── */
.net-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.55rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    font-family: 'Space Mono', monospace;
    font-size: 0.72rem;
}
.net-row:last-child { border-bottom: none; }
.net-label  { color: #5A6470; }
.net-ok     { color: #00E5FF; display: flex; align-items: center; gap: 5px; }
.net-fail   { color: #FF6B6B; display: flex; align-items: center; gap: 5px; }
.dot        { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.dot-ok     { background: #00E5FF; box-shadow: 0 0 5px #00E5FF; }
.dot-fail   { background: #FF6B6B; }

/* ── Mode banners ─────────────────────────────────────────────────────────── */
.banner {
    font-family: 'Space Mono', monospace;
    font-size: 0.72rem;
    padding: 0.6rem 1rem;
    border-radius: 6px;
    letter-spacing: 0.05em;
    margin-bottom: 1.25rem;
}
.banner-demo    { background: rgba(255,180,0,.05);  border: 1px solid rgba(255,180,0,.3);  color: #FFB400; }
.banner-live    {
    background: rgba(0,229,255,.05);
    border: 1px solid rgba(0,229,255,.4);
    color: #00E5FF;
    box-shadow: 0 0 22px rgba(0,229,255,.08);
}
.banner-warn    { background: rgba(255,107,107,.05); border: 1px solid rgba(255,107,107,.3); color: #FF6B6B; }
.banner-fallback{
    background: rgba(130,80,255,.07);
    border: 1px solid rgba(130,80,255,.35);
    color: #A78BFA;
}

/* ── Proof card ───────────────────────────────────────────────────────────── */
.proof-card {
    background: rgba(10, 14, 19, 0.9);
    border: 1px solid rgba(0, 229, 255, 0.22);
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    font-family: 'Space Mono', monospace;
    box-shadow: 0 0 35px rgba(0, 229, 255, 0.04);
}
.proof-card-invalid { border-color: rgba(255,107,107,.28); box-shadow: 0 0 35px rgba(255,107,107,.05); }
.proof-card-fallback{ border-color: rgba(130,80,255,.28); box-shadow: 0 0 35px rgba(130,80,255,.05); }
.proof-lbl  {
    font-size: 0.6rem; color: #5A6470;
    text-transform: uppercase; letter-spacing: 0.18em;
    margin: 0.85rem 0 0.2rem;
}
.proof-lbl:first-of-type { margin-top: 0; }
.proof-val-ok  { font-size: 0.82rem; color: #00E5FF; word-break: break-all; }
.proof-val-err { font-size: 0.82rem; color: #FF6B6B; word-break: break-all; }
.proof-val-fb  { font-size: 0.82rem; color: #A78BFA; word-break: break-all; }
.tx-link {
    color: #00E5FF; text-decoration: none;
    font-size: 0.82rem; word-break: break-all;
}
.tx-link:hover { opacity: 0.75; text-decoration: underline; }
.tx-nolink { color: #5A6470; font-size: 0.82rem; font-style: italic; }

/* ── Scan button ──────────────────────────────────────────────────────────── */
.stButton > button {
    background: transparent !important;
    color: #E6EDF3 !important;
    border: 1px solid rgba(0, 229, 255, 0.45) !important;
    border-radius: 6px !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.07em !important;
    padding: 0.55rem 1.25rem !important;
    transition: all 0.18s ease !important;
    width: 100% !important;
}
.stButton > button:hover {
    background: rgba(0, 229, 255, 0.07) !important;
    border-color: #00E5FF !important;
    color: #00E5FF !important;
    box-shadow: 0 0 18px rgba(0, 229, 255, 0.2) !important;
}

/* ── Text input ───────────────────────────────────────────────────────────── */
.stTextInput input {
    background: rgba(12, 16, 23, 0.9) !important;
    border: 1px solid rgba(0, 229, 255, 0.2) !important;
    border-radius: 6px !important;
    color: #E6EDF3 !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.82rem !important;
}
.stTextInput input:focus {
    border-color: rgba(0, 229, 255, 0.5) !important;
    box-shadow: 0 0 12px rgba(0, 229, 255, 0.12) !important;
    outline: none !important;
}
.stTextInput label {
    font-family: 'Space Mono', monospace !important;
    font-size: 0.62rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.14em !important;
    color: rgba(0, 229, 255, 0.6) !important;
}

/* ── Recent Scans table ───────────────────────────────────────────────────── */
.scan-table {
    width: 100%; border-collapse: collapse;
    font-family: 'Space Mono', monospace; font-size: 0.76rem;
}
.scan-table th {
    color: rgba(0, 229, 255, 0.55);
    font-size: 0.6rem; letter-spacing: 0.16em; text-transform: uppercase;
    border-bottom: 1px solid rgba(0, 229, 255, 0.12);
    padding: 0.55rem 0.8rem; text-align: left; font-weight: 400;
}
.scan-table td {
    padding: 0.55rem 0.8rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    vertical-align: middle;
}
.scan-table tr:last-child td { border-bottom: none; }
.scan-table tr:hover td      { background: rgba(0,229,255,0.025); }
.s-ok   { color: #00E5FF; font-weight: 700; }
.s-mid  { color: #FFB800; font-weight: 700; }
.s-hi   { color: #FF4444; font-weight: 700; }
.v-ok   { color: #00E5FF; }
.v-fb   { color: #A78BFA; }
.v-inv  { color: #FF6B6B; }
.v-sim  { color: #6E7681; }
.addr-c { color: #6E7681; }
.mid-c  { color: #8B949E; }

/* ── Misc ─────────────────────────────────────────────────────────────────── */
hr { border-color: rgba(0, 229, 255, 0.08) !important; margin: 1.5rem 0 !important; }
.stSpinner > div { border-top-color: #00E5FF !important; }
.stAlert { border-radius: 8px !important; }
::-webkit-scrollbar       { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #0A0E13; }
::-webkit-scrollbar-thumb { background: rgba(0,229,255,0.18); border-radius: 2px; }
</style>
""", unsafe_allow_html=True)

# ─── Session state ────────────────────────────────────────────────────────────
if "recent_scans"      not in st.session_state: st.session_state.recent_scans = []
if "is_demo_mode"      not in st.session_state: st.session_state.is_demo_mode = None
if "guard"             not in st.session_state: st.session_state.guard = None
if "memsync"           not in st.session_state: st.session_state.memsync = None
if "inference_error"   not in st.session_state: st.session_state.inference_error = None
if "og_devnet_native_ok" not in st.session_state: st.session_state.og_devnet_native_ok = None


# ─── Business logic (unchanged) ───────────────────────────────────────────────
def ensure_guard():
    if st.session_state.guard is not None and st.session_state.is_demo_mode is not None:
        return
    client = _load_client()
    if client is None:
        st.session_state.is_demo_mode = True
        st.session_state.guard = None
        st.session_state.og_devnet_native_ok = False
        return
    wallet_addr = client._wallet_account.address
    balance = get_opg_token_balance(wallet_addr)
    st.session_state.is_demo_mode = balance == 0
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
    ensure_guard()
    guard = st.session_state.guard
    addr = (address or "").strip()
    if not addr.startswith("0x"):
        addr = "0x" + addr
    if len(addr) != 42:
        st.warning("Please enter a valid 0x-prefixed 40-hex address.")
        return None

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
                        "Account not yet registered on OpenGradient Devnet. "
                        "Request native OG gas from the faucet or a team member."
                    )
                    st.session_state.og_devnet_native_ok = False
                    return None
                import re
                exc_str = str(e)
                is_event_err = any(
                    kw in err_msg for kw in ("inferencere", "event not found", "transaction logs", "network fallback")
                )
                if is_event_err:
                    tx_match = re.search(r'0x[0-9a-fA-F]{64}', exc_str)
                    tx_hash = tx_match.group(0) if tx_match else ""
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

    row = {
        "Address": addr,
        "Risk Score": result.risk_score,
        "Verification": result.verification_status,
        "Model ID": result.model_id[:16] + "…" if len(result.model_id) > 16 else result.model_id,
        "_full_tx": result.transaction_hash,
        "_full_model": result.model_id,
        "_is_fallback": getattr(result, "is_local_fallback", False),
    }
    st.session_state.recent_scans.insert(0, row)
    if len(st.session_state.recent_scans) > 50:
        st.session_state.recent_scans = st.session_state.recent_scans[:50]
    return result


def get_memsync_recent() -> list[dict]:
    guard = st.session_state.guard
    memsync = st.session_state.memsync
    if guard is None or memsync is None or not getattr(memsync, "api_key", None):
        return []
    try:
        r = guard.cluster_risk_profiles(query="DeFi risk profile address verification transaction", limit=20)
        return r or []
    except Exception:
        return []


# ─── UI helpers ───────────────────────────────────────────────────────────────
def risk_gauge(score: float):
    """Speedometer gauge with teal/amber/red color scheme."""
    pct = max(0, min(1, score)) * 100
    if pct <= 33:
        bar_color, needle = "#00E5FF", "#00E5FF"
    elif pct <= 66:
        bar_color, needle = "#FFB800", "#FFB800"
    else:
        bar_color, needle = "#FF4444", "#FF4444"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pct,
        number={"suffix": "%", "font": {"size": 38, "family": "Space Mono, monospace"}, "valueformat": ".1f"},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#2A3040", "tickfont": {"color": "#5A6470"}},
            "bar": {"color": bar_color, "thickness": 0.72},
            "bgcolor": "#0C1017",
            "borderwidth": 1,
            "bordercolor": "#1E2530",
            "steps": [
                {"range": [0,  33], "color": "#061218"},
                {"range": [33, 66], "color": "#0F1208"},
                {"range": [66, 100], "color": "#130808"},
            ],
            "threshold": {
                "line": {"color": needle, "width": 2},
                "thickness": 0.82,
                "value": pct,
            },
        },
        title={"text": "RISK SCORE", "font": {"size": 11, "color": "#5A6470", "family": "Space Mono, monospace"}},
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=24, r=24, t=48, b=16),
        height=270,
        font={"color": "#C9D1D9", "family": "Space Mono, monospace"},
    )
    return fig


def _score_color_class(score: float) -> str:
    if score <= 0.33:
        return "s-ok"
    elif score <= 0.66:
        return "s-mid"
    return "s-hi"


def _verif_color_class(v: str) -> str:
    v = v.upper()
    if "FALLBACK" in v:  return "v-fb"
    if "SIMULATED" in v: return "v-sim"
    if "VALID" in v:     return "v-ok"
    return "v-inv"


def render_proof(result: RiskCheckResult):
    """High-tech proof card with teal/purple/red variants and clickable Tx Hash."""
    is_local = getattr(result, "is_local_fallback", False)
    is_valid = "VALID" in result.verification_status and not is_local

    if is_local:
        card_cls = "proof-card proof-card-fallback"
        val_cls  = "proof-val-fb"
        icon     = _ICON_EYE.replace("currentColor", "#A78BFA")
        icon_clr = "#A78BFA"
    elif is_valid:
        card_cls = "proof-card"
        val_cls  = "proof-val-ok"
        icon     = _ICON_EYE.replace("currentColor", "#00E5FF")
        icon_clr = "#00E5FF"
    else:
        card_cls = "proof-card proof-card-invalid"
        val_cls  = "proof-val-err"
        icon     = _ICON_EYE.replace("currentColor", "#FF6B6B")
        icon_clr = "#FF6B6B"

    # Tx Hash: link if we have a hash, plain text otherwise
    tx = result.transaction_hash or ""
    if tx and tx != "0x" and len(tx) >= 10:
        tx_display = tx[:10] + "…" + tx[-8:] if len(tx) > 22 else tx
        tx_html = f'<a class="tx-link" href="{OG_EXPLORER_TX}/{tx}" target="_blank" title="{tx}">{tx_display}</a>'
    elif tx:
        tx_html = f'<span class="{val_cls}">{tx}</span>'
    else:
        tx_html = '<span class="tx-nolink">— not available —</span>'

    hdr_label = "LOCAL FALLBACK" if is_local else ("VERIFIED" if is_valid else "UNVERIFIED")
    hdr_style = f"color:{icon_clr};"

    st.markdown(f"""
    <div class="{card_cls}">
      <div class="og-card-hdr" style="{hdr_style}">
        {icon} PROOF · {hdr_label}
        <div class="og-card-hdr-line"></div>
      </div>
      <div class="proof-lbl">Verification Status</div>
      <div class="{val_cls}">{result.verification_status}</div>
      <div class="proof-lbl">Model ID</div>
      <div class="{val_cls}" style="font-size:0.78rem;">{result.model_id}</div>
      <div class="proof-lbl">Transaction Hash</div>
      <div>{tx_html}</div>
    </div>
    """, unsafe_allow_html=True)

    if is_local:
        st.markdown(
            '<div class="banner banner-fallback">'
            '⚠&nbsp;&nbsp;Result: Local Inference (Network Fallback) — '
            'InferenceResult event was not confirmed on-chain within 10 s. '
            'Score computed locally via the downloaded .onnx model.'
            '</div>',
            unsafe_allow_html=True,
        )


def render_scans_table(scans: list[dict]) -> None:
    """Render Recent Scans as a custom HTML table."""
    rows = ""
    for s in scans:
        addr     = s.get("Address", "")
        score    = s.get("Risk Score", 0.0)
        verif    = s.get("Verification", "")
        model_id = s.get("Model ID", "")
        full_tx  = s.get("_full_tx", "")

        addr_short = addr[:6] + "…" + addr[-4:] if len(addr) > 13 else addr
        if full_tx and len(full_tx) >= 10:
            tx_short = full_tx[:8] + "…" + full_tx[-6:]
            tx_cell  = (
                f'<a class="tx-link" href="{OG_EXPLORER_TX}/{full_tx}" '
                f'target="_blank" title="{full_tx}">{tx_short}</a>'
            )
        else:
            tx_cell = '<span style="color:#5A6470;">—</span>'

        score_pct = f"{score * 100:.1f}%"
        s_cls = _score_color_class(score)
        v_cls = _verif_color_class(verif)

        rows += f"""
        <tr>
          <td><span class="addr-c">{addr_short}</span></td>
          <td><span class="{s_cls}">{score_pct}</span></td>
          <td><span class="{v_cls}">{verif}</span></td>
          <td><span class="mid-c" style="font-size:0.72rem;">{model_id}</span></td>
          <td>{tx_cell}</td>
        </tr>"""

    st.markdown(f"""
    <div class="og-card" style="padding:0;">
      <table class="scan-table">
        <thead>
          <tr>
            <th>Address</th><th>Score</th><th>Verification</th>
            <th>Model ID</th><th>Tx Hash</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """, unsafe_allow_html=True)


# ─── Sidebar ──────────────────────────────────────────────────────────────────
ensure_guard()
is_demo = st.session_state.is_demo_mode
og_ok   = st.session_state.og_devnet_native_ok

with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;padding:0 0.5rem 1.25rem;">'
        + _load_logo_b64(32)
        + '<span style="font-family:\'Space Mono\',monospace;font-size:0.72rem;'
          'color:#00E5FF;letter-spacing:0.06em;">OPENGRADIENT</span>'
          '</div>',
        unsafe_allow_html=True,
    )

    sepolia_ok = is_demo is False
    base_status = "Detected" if sepolia_ok else "Not detected"
    og_status   = "Detected" if og_ok else "Not initialized"

    st.markdown(f"""
    <div class="og-card" style="padding:1rem 1.1rem;">
      <div class="og-card-hdr">
        {_ICON_NET} Network Status
        <div class="og-card-hdr-line"></div>
      </div>
      <div class="net-row">
        <span class="net-label">Base Sepolia ($OPG)</span>
        <span class="{'net-ok' if sepolia_ok else 'net-fail'}">
          <span class="dot {'dot-ok' if sepolia_ok else 'dot-fail'}"></span>
          {base_status}
        </span>
      </div>
      <div class="net-row">
        <span class="net-label">OG Devnet (Native)</span>
        <span class="{'net-ok' if og_ok else 'net-fail'}">
          <span class="dot {'dot-ok' if og_ok else 'dot-fail'}"></span>
          {og_status}
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="og-card" style="padding:1rem 1.1rem;margin-top:0.75rem;">
      <div class="og-card-hdr">
        {_ICON_SCAN} Inference Mode
        <div class="og-card-hdr-line"></div>
      </div>
      <div class="net-row">
        <span class="net-label">Chain</span>
        <span style="font-family:'Space Mono',monospace;font-size:0.72rem;color:#8B949E;">OG Testnet 10740</span>
      </div>
      <div class="net-row" style="border-bottom:none;">
        <span class="net-label">Fallback</span>
        <span style="font-family:'Space Mono',monospace;font-size:0.72rem;color:#A78BFA;">Local ONNX</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ─── Main ─────────────────────────────────────────────────────────────────────

# Header — real OG logo + teal Space Mono title
_header_logo = _load_logo_b64(60)
st.markdown(
    '<div style="display:flex;align-items:center;gap:1.4rem;'
    'margin-bottom:1.75rem;padding-top:0.25rem;">'
    + _header_logo
    + '<div style="min-width:0;">'
      '<div style="font-family:\'Space Mono\',monospace;font-size:1.55rem;'
      'font-weight:700;color:#00E5FF;letter-spacing:-0.01em;'
      'line-height:1.25;white-space:nowrap;overflow:visible;">'
      'VERIFIABLE DEFI RISK GUARD'
      '</div>'
      '<div style="font-family:\'Inter\',sans-serif;font-size:0.8rem;'
      'color:#5A6470;margin-top:0.35rem;letter-spacing:0.01em;">'
      'On-chain proof verification&nbsp;&middot;&nbsp;'
      'Probabilistic risk assessment&nbsp;&middot;&nbsp;'
      'Decentralized MemSync analytics'
      '</div>'
      '</div>'
      '</div>',
    unsafe_allow_html=True,
)

# Inference error
if st.session_state.get("inference_error"):
    st.markdown(
        f'<div class="banner banner-warn">⚠&nbsp;&nbsp;{st.session_state.inference_error}</div>',
        unsafe_allow_html=True,
    )
    if st.button("↩ Retry", key="retry_inference_error"):
        st.session_state.inference_error = None
        st.rerun()

# Mode banner
if is_demo is True:
    st.markdown(
        f'<div class="banner banner-demo">'
        f'◈ DEMO MODE [{DEMO_MODE_REASON}] — Simulated inference, no chain calls. '
        f'Fund wallet for live on-chain verification.</div>',
        unsafe_allow_html=True,
    )
elif is_demo is False:
    st.markdown(
        '<div class="banner banner-live">'
        '◉ LIVE ON-CHAIN MODE — $OPG detected on Base Sepolia. '
        'Verifiable inference and cryptographic proof verification active.</div>',
        unsafe_allow_html=True,
    )

# Scan card
st.markdown(f"""
<div class="og-card" style="margin-bottom:0.25rem;">
  <div class="og-card-hdr">
    {_ICON_SHIELD} Address Scanner
    <div class="og-card-hdr-line"></div>
  </div>
</div>
""", unsafe_allow_html=True)

col_inp, col_btn = st.columns([5, 1])
with col_inp:
    address = st.text_input(
        "Wallet Address",
        value="0x4Fa0f435e736A04D7da547E681ce092a427D6205",
        placeholder="0x…",
        key="address",
        label_visibility="visible",
    )
with col_btn:
    st.write("")
    st.write("")
    scan_clicked = st.button("⬡ SCAN", key="scan_btn", width="stretch")

# Run scan
result = None
if scan_clicked and address:
    with st.spinner("Running risk assessment…"):
        result = run_scan(address)

# Results
if result is not None:
    st.markdown("<div style='margin-top:1.25rem;'></div>", unsafe_allow_html=True)
    col_gauge, col_proof = st.columns([1, 1], gap="large")
    with col_gauge:
        st.plotly_chart(risk_gauge(result.risk_score), width="stretch")
    with col_proof:
        render_proof(result)

# Recent Scans
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown(f"""
<div style="font-family:'Space Mono',monospace;font-size:0.62rem;
            color:rgba(0,229,255,0.6);text-transform:uppercase;
            letter-spacing:0.18em;margin-bottom:0.75rem;
            display:flex;align-items:center;gap:0.5rem;">
  {_ICON_SCAN} Recent Scans
  <div style="flex:1;height:1px;background:linear-gradient(90deg,rgba(0,229,255,0.2) 0%,transparent 100%);"></div>
</div>
""", unsafe_allow_html=True)

scans = st.session_state.recent_scans
if scans:
    render_scans_table(scans)
else:
    memsync_rows = get_memsync_recent()
    if memsync_rows:
        rows_data = []
        for m in memsync_rows:
            mem = m.get("memory", "") if isinstance(m, dict) else str(m)
            rows_data.append({"Memory": mem[:90] + "…" if len(mem) > 90 else mem})
        st.dataframe(rows_data, width="stretch", hide_index=True)
    else:
        st.markdown(
            '<div style="font-family:\'Space Mono\',monospace;font-size:0.78rem;'
            'color:#5A6470;padding:1.5rem 0;text-align:center;">'
            '— No scans yet. Enter a wallet address above and click SCAN. —</div>',
            unsafe_allow_html=True,
        )
