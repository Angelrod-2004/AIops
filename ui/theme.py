"""Visual layer: the futuristic dark/neon theme injected into Streamlit."""

from __future__ import annotations

import html

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root{
  --bg:#05060f;
  --panel:rgba(17,20,40,.62);
  --stroke:rgba(130,150,255,.16);
  --text:#e9ecff;
  --muted:#8c93b8;
  --brand:#7c6cff;
  --cyan:#22d3ee;
  --green:#3ddc84;
  --rose:#ff5f7e;
}

html, body, [data-testid="stAppViewContainer"], .stMarkdown, .stText, p, span, div{font-family:'Inter',system-ui,sans-serif;}
.stApp{color:var(--text);background:
  radial-gradient(900px 620px at 10% -12%, rgba(124,108,255,.30), transparent 62%),
  radial-gradient(820px 540px at 94% 4%, rgba(34,211,238,.18), transparent 58%),
  radial-gradient(760px 760px at 55% 118%, rgba(61,220,132,.12), transparent 60%),
  #05060f;}
.stApp::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background-image:linear-gradient(rgba(255,255,255,.032) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.032) 1px,transparent 1px);
  background-size:64px 64px;
  -webkit-mask-image:radial-gradient(circle at 50% 18%,#000,transparent 78%);
  mask-image:radial-gradient(circle at 50% 18%,#000,transparent 78%);
  animation:nx-grid 26s linear infinite;}
@keyframes nx-grid{from{background-position:0 0,0 0}to{background-position:64px 64px,64px 64px}}
@keyframes nx-float{0%,100%{transform:translate3d(0,0,0)}50%{transform:translate3d(0,-8px,0)}}
@keyframes nx-pulse{0%,100%{opacity:.55;transform:scale(1)}50%{opacity:1;transform:scale(1.35)}}

header[data-testid="stHeader"]{background:transparent;}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"]{visibility:hidden;height:0;}
.block-container{padding-top:2.2rem;padding-bottom:4rem;max-width:1320px;position:relative;z-index:1;}

[data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(10,12,26,.98),rgba(6,7,17,.99));border-right:1px solid var(--stroke);}
[data-testid="stSidebar"] *{color:var(--text);}
[data-testid="stSidebar"] .nx-side-title{font-family:'Space Grotesk';letter-spacing:.28em;font-size:.66rem;color:var(--muted);text-transform:uppercase;}

/* ---------------- brand / hero ---------------- */
.nx-brand{display:flex;align-items:center;gap:10px;font-family:'Space Grotesk';font-weight:700;letter-spacing:.14em;font-size:.92rem;text-transform:uppercase;}
.nx-mark{width:30px;height:30px;border-radius:10px;display:grid;place-items:center;font-size:15px;
  background:linear-gradient(140deg,#7c6cff,#22d3ee);color:#05060f;box-shadow:0 0 26px rgba(124,108,255,.65);}
.nx-hero{position:relative;padding:34px 34px 30px;border-radius:26px;overflow:hidden;
  border:1px solid rgba(124,108,255,.26);
  background:linear-gradient(140deg,rgba(26,30,60,.85),rgba(9,11,24,.78));
  box-shadow:0 40px 120px -50px rgba(124,108,255,.75), inset 0 1px 0 rgba(255,255,255,.07);}
.nx-hero::after{content:"";position:absolute;width:420px;height:420px;right:-120px;top:-190px;border-radius:50%;
  background:radial-gradient(circle,rgba(34,211,238,.45),transparent 62%);filter:blur(14px);animation:nx-float 9s ease-in-out infinite;}
.nx-hero::before{content:"";position:absolute;width:320px;height:320px;left:-120px;bottom:-200px;border-radius:50%;
  background:radial-gradient(circle,rgba(124,108,255,.45),transparent 62%);filter:blur(16px);}
.nx-eyebrow{font-family:'JetBrains Mono';font-size:.68rem;letter-spacing:.34em;text-transform:uppercase;color:#8ee7ff;position:relative;}
.nx-title{font-family:'Space Grotesk';font-weight:700;font-size:2.9rem;line-height:1.02;margin:.5rem 0 .6rem;position:relative;
  background:linear-gradient(100deg,#ffffff 8%,#c9c2ff 38%,#7ce9ff 68%,#8bffc4 96%);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;}
.nx-sub{max-width:760px;color:#a7aecf;font-size:.98rem;line-height:1.6;position:relative;}
.nx-steps{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px;position:relative;}
.nx-step{display:flex;align-items:center;gap:9px;padding:9px 14px;border-radius:12px;font-size:.8rem;
  background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.09);color:#c8cdec;}
.nx-step b{font-family:'JetBrains Mono';color:#8ee7ff;font-weight:500;}

/* ---------------- cards ---------------- */
.nx-card{position:relative;border-radius:20px;padding:18px 18px 16px;overflow:hidden;
  background:linear-gradient(160deg,rgba(24,28,54,.80),rgba(11,13,29,.74));
  border:1px solid var(--stroke);backdrop-filter:blur(16px);
  box-shadow:0 26px 70px -38px rgba(0,0,0,.95), inset 0 1px 0 rgba(255,255,255,.055);
  transition:transform .22s ease,border-color .22s ease,box-shadow .22s ease;}
.nx-card:hover{transform:translateY(-3px);border-color:rgba(124,108,255,.5);box-shadow:0 34px 80px -34px rgba(124,108,255,.55), inset 0 1px 0 rgba(255,255,255,.08);}
.nx-card::before{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(360px 120px at 0% 0%,var(--glow,rgba(124,108,255,.20)),transparent 72%);}
.nx-app-top{display:flex;align-items:center;gap:12px;position:relative;}
.nx-app-icon{width:42px;height:42px;border-radius:13px;display:grid;place-items:center;font-size:19px;
  background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.10);color:var(--accent,#7c6cff);
  box-shadow:0 0 26px -6px var(--accent,#7c6cff);}
.nx-app-name{font-family:'Space Grotesk';font-weight:600;font-size:1.02rem;letter-spacing:.01em;}
.nx-app-sub{font-size:.74rem;color:var(--muted);margin-top:1px;}
.nx-app-foot{display:flex;justify-content:space-between;align-items:center;margin-top:14px;font-family:'JetBrains Mono';font-size:.68rem;color:var(--muted);position:relative;}

.nx-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-family:'JetBrains Mono';
  font-size:.63rem;letter-spacing:.10em;text-transform:uppercase;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.05);}
.nx-pill.live{color:#8bffc4;border-color:rgba(61,220,132,.45);background:rgba(61,220,132,.10);}
.nx-pill.sim{color:#ffd88a;border-color:rgba(255,196,84,.40);background:rgba(255,196,84,.10);}
.nx-pill.err{color:#ffb1c1;border-color:rgba(255,95,126,.42);background:rgba(255,95,126,.10);}
.nx-dot{width:6px;height:6px;border-radius:50%;background:currentColor;animation:nx-pulse 1.8s ease-in-out infinite;}

.nx-section{display:flex;align-items:center;gap:12px;margin:30px 0 14px;}
.nx-section h3{font-family:'Space Grotesk';font-size:.86rem;letter-spacing:.30em;text-transform:uppercase;color:#c3c9ef;margin:0;font-weight:600;}
.nx-section .nx-rule{flex:1;height:1px;background:linear-gradient(90deg,rgba(124,108,255,.45),rgba(124,108,255,0));}
.nx-hint{font-size:.78rem;color:var(--muted);margin:-4px 0 12px;}

/* ---------------- queue ---------------- */
.nx-q{display:flex;align-items:flex-start;gap:12px;padding:12px 14px;border-radius:14px;margin-bottom:9px;
  background:linear-gradient(120deg,rgba(22,26,50,.85),rgba(11,13,28,.8));border:1px solid var(--stroke);}
.nx-q .nx-app-icon{width:32px;height:32px;font-size:15px;border-radius:10px;}
.nx-q-title{font-size:.86rem;font-weight:600;color:#e6e9ff;}
.nx-q-meta{font-family:'JetBrains Mono';font-size:.68rem;color:var(--muted);margin-top:3px;word-break:break-all;}
.nx-empty{border:1px dashed rgba(130,150,255,.28);border-radius:16px;padding:26px;text-align:center;color:var(--muted);font-size:.82rem;}

/* ---------------- results ---------------- */
.nx-res{position:relative;border-radius:18px;padding:16px 18px;margin-bottom:12px;overflow:hidden;
  background:linear-gradient(150deg,rgba(20,24,46,.86),rgba(10,12,26,.82));border:1px solid var(--stroke);}
.nx-res.ok{box-shadow:inset 3px 0 0 0 rgba(61,220,132,.85);}
.nx-res.fail{box-shadow:inset 3px 0 0 0 rgba(255,95,126,.85);}
.nx-res-top{display:flex;align-items:center;justify-content:space-between;gap:12px;}
.nx-res-title{font-family:'Space Grotesk';font-size:.95rem;font-weight:600;}
.nx-res-sub{font-size:.78rem;color:#9aa2c6;margin-top:5px;line-height:1.5;}
.nx-mono{font-family:'JetBrains Mono';font-size:.68rem;color:var(--muted);}
.nx-report{border-radius:18px;padding:18px 20px;border:1px solid rgba(34,211,238,.26);
  background:linear-gradient(140deg,rgba(18,24,46,.9),rgba(9,12,26,.86));
  box-shadow:0 30px 80px -46px rgba(34,211,238,.7);}

.nx-arch{display:grid;grid-template-columns:1fr 1.2fr 1fr;gap:14px;align-items:center;}
.nx-arch-col{display:flex;flex-direction:column;gap:10px;}
.nx-node{border-radius:14px;padding:12px 14px;border:1px solid var(--stroke);background:rgba(255,255,255,.035);
  font-size:.78rem;color:#cfd4f2;text-align:center;}
.nx-node.hub{border-color:rgba(124,108,255,.55);background:linear-gradient(135deg,rgba(124,108,255,.24),rgba(34,211,238,.16));
  box-shadow:0 0 40px -14px rgba(124,108,255,.8);font-family:'Space Grotesk';font-weight:600;}
.nx-arrow{text-align:center;color:#5f6790;font-family:'JetBrains Mono';font-size:.72rem;}

/* ---------------- widgets ---------------- */
label, .stWidgetLabel label, [data-testid="stWidgetLabel"] p{color:#a9b0d4 !important;font-size:.72rem !important;
  letter-spacing:.10em;text-transform:uppercase;font-weight:600 !important;}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stTextArea"] textarea,
[data-baseweb="select"] > div, [data-baseweb="base-input"]{
  background:rgba(8,10,22,.88) !important;border:1px solid rgba(130,150,255,.20) !important;border-radius:12px !important;
  color:var(--text) !important;font-family:'JetBrains Mono',monospace !important;font-size:.82rem !important;}
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus{border-color:rgba(34,211,238,.65) !important;
  box-shadow:0 0 0 3px rgba(34,211,238,.12) !important;}
[data-baseweb="popover"] li{background:#0c0f22 !important;color:var(--text) !important;font-size:.82rem !important;}
::placeholder{color:#5b6288 !important;}

.stButton > button, .stDownloadButton > button{border-radius:13px;border:1px solid rgba(124,108,255,.35);
  background:linear-gradient(135deg,rgba(124,108,255,.20),rgba(34,211,238,.12));color:#eef1ff;font-weight:600;font-size:.82rem;
  padding:.52rem 1rem;transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease;}
.stButton > button:hover, .stDownloadButton > button:hover{transform:translateY(-1px);border-color:rgba(34,211,238,.72);
  box-shadow:0 16px 36px -18px rgba(34,211,238,.85);color:#fff;}
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"]{border:none !important;color:#06070f !important;
  background:linear-gradient(120deg,#8f7dff,#3ee0f0 55%,#5cf2a5) !important;
  box-shadow:0 18px 40px -18px rgba(94,214,255,.9) !important;font-weight:700 !important;}
.stButton > button[kind="primary"]:hover{filter:brightness(1.08);}

.stTabs [data-baseweb="tab-list"]{gap:6px;background:rgba(12,14,30,.66);padding:6px;border-radius:16px;
  border:1px solid var(--stroke);width:fit-content;}
.stTabs [data-baseweb="tab"]{border-radius:12px;padding:8px 18px;color:var(--muted);background:transparent;font-size:.85rem;font-weight:600;}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,rgba(124,108,255,.38),rgba(34,211,238,.24)) !important;color:#fff !important;}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"]{display:none;}

[data-testid="stExpander"]{border:1px solid var(--stroke) !important;border-radius:14px !important;background:rgba(10,12,26,.62) !important;}
[data-testid="stExpander"] summary{font-size:.8rem;color:#b9c0e4;}
[data-testid="stStatusWidget"]{background:transparent;}

div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:18px !important;border-color:var(--stroke) !important;
  background:linear-gradient(160deg,rgba(18,22,44,.72),rgba(9,11,24,.66)) !important;}
[data-testid="stMetric"]{background:rgba(255,255,255,.03);border:1px solid var(--stroke);border-radius:14px;padding:12px 14px;}
[data-testid="stMetricValue"]{font-family:'Space Grotesk';font-size:1.4rem;}
[data-testid="stMetricLabel"]{color:var(--muted) !important;text-transform:uppercase;font-size:.66rem !important;letter-spacing:.14em;}

.stAlert{border-radius:14px;border:1px solid rgba(255,255,255,.08);}
hr{border-color:rgba(130,150,255,.14);}
code{font-family:'JetBrains Mono' !important;font-size:.78rem;color:#9fe8ff;background:rgba(34,211,238,.08);padding:1px 5px;border-radius:5px;}
.nx-foot{text-align:center;color:#5b6288;font-size:.7rem;letter-spacing:.24em;text-transform:uppercase;font-family:'JetBrains Mono';margin-top:36px;}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(124,108,255,.35);border-radius:999px}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def section(title: str, hint: str = "") -> None:
    st.markdown(
        f'<div class="nx-section"><h3>{esc(title)}</h3><div class="nx-rule"></div></div>'
        + (f'<div class="nx-hint">{esc(hint)}</div>' if hint else ""),
        unsafe_allow_html=True,
    )


def pill(text: str, tone: str = "") -> str:
    return f'<span class="nx-pill {tone}"><span class="nx-dot"></span>{esc(text)}</span>'


def footer() -> None:
    st.markdown('<div class="nx-foot">Nexus Ops Grid · LangGraph multi-agent surface</div>', unsafe_allow_html=True)
