"""
DETA Pipeline — Palantir Dark UI Theme
========================================
Black & white, monochrome, mission-control aesthetic.
All pages import and call apply_theme() for consistent styling.
"""

import streamlit as st

# ── Color Palette ──
# BG:    #0A0A0A (pure black)  #111111 (container)  #1A1A1A (card)
# BORDER: #222222 (subtle)  #333333 (visible)  #444444 (active)
# TEXT:   #FFFFFF (primary)  #CCCCCC (secondary)  #888888 (muted)  #555555 (caption)

PALANTIR_CSS = """
<style>
    /* ══════════════════════════════════════════
       GLOBAL
    ══════════════════════════════════════════ */
    .stApp {
        background-color: #0A0A0A;
    }
    .stApp > header {
        background-color: #0A0A0A !important;
    }

    /* Hide default streamlit branding */
    #MainMenu, footer, [data-testid="stDecoration"] { display: none !important; }

    /* ══════════════════════════════════════════
       SIDEBAR
    ══════════════════════════════════════════ */
    [data-testid="stSidebar"] {
        background-color: #0E0E0E;
        border-right: 1px solid #1A1A1A;
    }
    [data-testid="stSidebar"] * {
        color: #888888;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #FFFFFF !important;
    }

    /* Sidebar nav links */
    [data-testid="stSidebarNavItems"] a {
        color: #888888 !important;
        font-weight: 500;
        letter-spacing: 0.5px;
    }
    [data-testid="stSidebarNavItems"] a:hover {
        color: #FFFFFF !important;
    }
    [data-testid="stSidebarNavItems"] a[aria-current="page"] {
        color: #FFFFFF !important;
        background-color: #1A1A1A !important;
        border-left: 2px solid #FFFFFF;
    }

    /* Rename "streamlit app" nav label to "newsletter" */
    [data-testid="stSidebarNavItems"] li:first-child a span {
        visibility: hidden;
        position: relative;
    }
    [data-testid="stSidebarNavItems"] li:first-child a span::after {
        content: "newsletter";
        visibility: visible;
        position: absolute;
        left: 0;
        top: 0;
    }

    /* ══════════════════════════════════════════
       TYPOGRAPHY
    ══════════════════════════════════════════ */
    h1, h2 {
        color: #FFFFFF !important;
        letter-spacing: -0.3px;
        font-weight: 700;
    }
    h3 {
        color: #CCCCCC !important;
        font-weight: 600;
    }
    p, li, span, label {
        color: #AAAAAA;
    }
    .stCaption, caption {
        color: #555555 !important;
    }
    a { color: #888888 !important; }
    a:hover { color: #FFFFFF !important; }
    hr { border-color: #222222 !important; }

    /* ══════════════════════════════════════════
       INPUT FIELDS
    ══════════════════════════════════════════ */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div > div,
    .stNumberInput > div > div > input {
        background-color: #111111 !important;
        border: 1px solid #333333 !important;
        color: #E0E0E0 !important;
        border-radius: 2px !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #FFFFFF !important;
        box-shadow: 0 0 0 1px #FFFFFF !important;
    }
    .stTextInput label, .stTextArea label,
    .stSelectbox label, .stFileUploader label,
    .stNumberInput label {
        color: #888888 !important;
        font-weight: 500 !important;
        font-size: 11px !important;
        letter-spacing: 1px !important;
        text-transform: uppercase !important;
    }

    /* ══════════════════════════════════════════
       BUTTONS
    ══════════════════════════════════════════ */
    .stButton > button {
        background-color: transparent !important;
        color: #CCCCCC !important;
        border: 1px solid #333333 !important;
        border-radius: 2px !important;
        font-weight: 500 !important;
        letter-spacing: 0.5px !important;
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        background-color: #1A1A1A !important;
        border-color: #FFFFFF !important;
        color: #FFFFFF !important;
    }
    /* Primary button — white on black */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background-color: #FFFFFF !important;
        color: #0A0A0A !important;
        border: none !important;
        font-weight: 600 !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="stBaseButton-primary"]:hover {
        background-color: #CCCCCC !important;
    }

    /* ══════════════════════════════════════════
       TABS
    ══════════════════════════════════════════ */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent;
        border-bottom: 1px solid #222222;
        gap: 0px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent !important;
        color: #666666 !important;
        border-radius: 0 !important;
        border-bottom: 2px solid transparent !important;
        font-weight: 500;
        font-size: 12px;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        padding: 8px 16px !important;
    }
    .stTabs [aria-selected="true"] {
        color: #FFFFFF !important;
        border-bottom: 2px solid #FFFFFF !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #CCCCCC !important;
    }
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 16px;
    }

    /* ══════════════════════════════════════════
       ALERTS
    ══════════════════════════════════════════ */
    .stAlert > div {
        border-radius: 2px !important;
        border-width: 1px !important;
    }
    [data-testid="stAlert"][data-type="info"] > div {
        background-color: #111111 !important;
        border-color: #222222 !important;
    }

    /* ══════════════════════════════════════════
       CHECKBOXES
    ══════════════════════════════════════════ */
    .stCheckbox label span { color: #AAAAAA !important; }

    /* ══════════════════════════════════════════
       METRICS
    ══════════════════════════════════════════ */
    [data-testid="stMetric"] {
        background-color: #111111;
        border: 1px solid #222222;
        border-radius: 2px;
        padding: 20px;
    }
    [data-testid="stMetricLabel"] {
        color: #555555 !important;
        font-size: 11px !important;
        letter-spacing: 1.5px !important;
        text-transform: uppercase !important;
    }
    [data-testid="stMetricValue"] {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }

    /* ══════════════════════════════════════════
       DATAFRAME
    ══════════════════════════════════════════ */
    .stDataFrame {
        border: 1px solid #222222;
        border-radius: 2px;
    }

    /* ══════════════════════════════════════════
       FILE UPLOADER
    ══════════════════════════════════════════ */
    [data-testid="stFileUploader"] > div {
        background-color: #0E0E0E !important;
        border: 1px dashed #333333 !important;
        border-radius: 2px !important;
    }

    /* ══════════════════════════════════════════
       DOWNLOAD BUTTON
    ══════════════════════════════════════════ */
    .stDownloadButton > button {
        background-color: transparent !important;
        color: #CCCCCC !important;
        border: 1px solid #333333 !important;
    }
    .stDownloadButton > button:hover {
        border-color: #FFFFFF !important;
        color: #FFFFFF !important;
    }

    /* ══════════════════════════════════════════
       CODE BLOCK
    ══════════════════════════════════════════ */
    .stCodeBlock, code {
        background-color: #0E0E0E !important;
    }

    /* ══════════════════════════════════════════
       EXPANDER
    ══════════════════════════════════════════ */
    .streamlit-expanderHeader {
        background-color: #111111 !important;
        border: 1px solid #222222 !important;
        border-radius: 2px !important;
        color: #888888 !important;
    }
    .streamlit-expanderContent {
        background-color: #0E0E0E !important;
        border: 1px solid #222222 !important;
        border-top: none !important;
    }

    /* ══════════════════════════════════════════
       SPINNER
    ══════════════════════════════════════════ */
    .stSpinner > div { color: #555555 !important; }

    /* ══════════════════════════════════════════
       FORM
    ══════════════════════════════════════════ */
    [data-testid="stForm"] {
        background-color: #111111 !important;
        border: 1px solid #222222 !important;
        border-radius: 2px !important;
        padding: 20px !important;
    }

    /* ══════════════════════════════════════════
       PALANTIR TYPOGRAPHY CLASSES
    ══════════════════════════════════════════ */
    .palantir-header {
        font-size: 11px;
        letter-spacing: 2.5px;
        color: #555555;
        font-weight: 600;
        text-transform: uppercase;
        font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    }
    .palantir-title {
        font-size: 28px;
        font-weight: 700;
        color: #FFFFFF;
        letter-spacing: -0.5px;
        margin: 6px 0 0;
    }
    .palantir-sub {
        font-size: 13px;
        color: #666666;
        margin-top: 4px;
        letter-spacing: 0.2px;
    }

    /* ══════════════════════════════════════════
       STEP CARDS
    ══════════════════════════════════════════ */
    .step-card {
        background: #111111;
        border: 1px solid #222222;
        border-radius: 2px;
        padding: 16px 20px;
        margin: 6px 0;
    }
    .step-active {
        border-left: 2px solid #FFFFFF;
    }
    .step-done {
        border-left: 2px solid #333333;
        opacity: 0.5;
    }

    /* ══════════════════════════════════════════
       NEWS ROW
    ══════════════════════════════════════════ */
    .news-row {
        background: #0E0E0E;
        border: 1px solid #1A1A1A;
        border-radius: 2px;
        padding: 12px 16px;
        margin: 4px 0;
    }

    /* ══════════════════════════════════════════
       AGENT PIPELINE CARDS (Mission Control style)
    ══════════════════════════════════════════ */
    .agent-card {
        background: #111111;
        border: 1px solid #222222;
        border-radius: 2px;
        padding: 24px;
        text-align: center;
    }
    .agent-card:hover {
        border-color: #444444;
    }
    .agent-label {
        font-size: 11px;
        letter-spacing: 2px;
        color: #555555;
        text-transform: uppercase;
        font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    }
    .agent-value {
        font-size: 32px;
        font-weight: 700;
        color: #FFFFFF;
        margin: 4px 0;
    }

    /* ══════════════════════════════════════════
       STATUS BADGES
    ══════════════════════════════════════════ */
    .status-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 2px;
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
        font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    }
    .status-idle {
        background: #1A1A1A;
        color: #555555;
        border: 1px solid #333333;
    }
    .status-active {
        background: #1A1A1A;
        color: #FFFFFF;
        border: 1px solid #FFFFFF;
    }
    .status-done {
        background: #111111;
        color: #444444;
        border: 1px solid #222222;
    }

    /* ══════════════════════════════════════════
       PROGRESS BAR (monochrome)
    ══════════════════════════════════════════ */
    .stProgress > div > div > div {
        background-color: #FFFFFF !important;
    }
    .stProgress > div > div {
        background-color: #222222 !important;
    }

    /* ══════════════════════════════════════════
       MULTISELECT / SELECT
    ══════════════════════════════════════════ */
    .stMultiSelect > div > div {
        background-color: #111111 !important;
        border-color: #333333 !important;
    }

    /* ══════════════════════════════════════════
       DIVIDER LINE
    ══════════════════════════════════════════ */
    .divider-line {
        border-top: 1px solid #222222;
        margin: 24px 0;
    }

    /* ══════════════════════════════════════════
       SCROLLBAR (minimal)
    ══════════════════════════════════════════ */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: #0A0A0A;
    }
    ::-webkit-scrollbar-thumb {
        background: #333333;
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #555555;
    }
</style>
"""


def apply_theme():
    """Call at the top of every page to apply consistent Palantir dark theme."""
    st.markdown(PALANTIR_CSS, unsafe_allow_html=True)
