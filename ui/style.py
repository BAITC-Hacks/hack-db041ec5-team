"""Local visual system for the analyst workspace."""
import streamlit as st


def apply_style():
    st.markdown('''<style>
    .stApp{background:#F4F6F9;color:#172B3A}
    .block-container{padding-top:3.5rem;padding-bottom:3rem;max-width:1480px}
    h1,h2,h3{letter-spacing:-.035em;color:#172B3A}
    h3{font-size:1.25rem!important}
    [data-testid="stSidebar"]{background:#FFFFFF;border-right:1px solid #E4E9EF}
    [data-testid="stSidebar"] .block-container{padding-top:1rem}
    [data-testid="stMetric"]{background:#fff;padding:18px;border-radius:12px;border:1px solid #E3E8EF}
    [data-testid="stMetricValue"]{font-size:1.5rem;letter-spacing:-.04em}
    [data-testid="stTabs"] [role="tablist"]{gap:6px;border-bottom:1px solid #DFE5EC;margin:5px 0 22px;padding-bottom:8px}
    [data-testid="stTabs"] [role="tab"]{padding:8px 14px;font-weight:600;border-radius:8px;font-size:13px}
    [data-testid="stTabs"] [role="tab"][aria-selected="true"]{background:#E1F2EC;color:#087F68}
    [data-testid="stTabs"] [data-baseweb="tab-highlight"]{display:none}
    [data-testid="stDataFrame"]{border-radius:12px;overflow:hidden;border:1px solid #E3E8EF}
    [data-testid="stButton"] button,[data-testid="stDownloadButton"] button{border-radius:8px;font-weight:600}
    [data-testid="stExpander"]{background:#fff;border-radius:12px}
    .brand{display:flex;align-items:center;gap:10px;margin:0 0 20px;font-size:20px;font-weight:800;letter-spacing:-.5px}
    .brand-icon{background:#147D68;color:white;border-radius:10px;padding:5px 10px;font-size:23px}
    .workspace-hero{background:#152D3B;border-radius:18px;padding:27px 30px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;gap:16px;color:white}
    .workspace-hero h1{color:white!important;font-size:29px!important;line-height:1.2;margin:7px 0 9px;padding:0;letter-spacing:-1px}
    .workspace-hero p{margin:0;color:#B8CBD5;font-size:14px;line-height:1.55}
    .eyebrow{font-size:10px;letter-spacing:.16em;font-weight:700;color:#85CFB9}
    .status-pill{white-space:nowrap;border:1px solid #385962;padding:7px 11px;border-radius:30px;color:#B8EBD9;font-size:11px}
    .demo-note{padding:9px 13px;background:#FFF7E6;border:1px solid #F4E6C4;border-radius:8px;color:#806329;font-size:12px;margin-bottom:14px}
    .section-heading{display:flex;align-items:end;justify-content:space-between;gap:15px;margin:4px 0 16px}
    .section-heading h2{font-size:22px;margin:0;letter-spacing:-.6px}
    .section-heading span{font-size:12px;color:#788996}
    .kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:0 0 24px}
    .kpi{background:#fff;border:1px solid #E2E8EE;border-radius:13px;padding:18px 20px;min-width:0}
    .kpi .kpi-label{font-size:12px;font-weight:600;color:#71818F;margin-bottom:13px}
    .kpi .kpi-value{font-size:28px;font-weight:750;letter-spacing:-1px;line-height:1.15;color:#172B3A}
    .kpi .kpi-note{font-size:11px;color:#8A98A4;margin-top:10px}
    .kpi.attention{border-top:3px solid #D58B47;padding-top:16px}
    .kpi.attention .kpi-value{color:#AF622D}
    .panel-title{font-size:15px;font-weight:750;margin:0 0 4px;color:#1B3443}
    .panel-note{font-size:12px;color:#8493A0;margin:0 0 17px}
    .priority-list{background:#fff;border:1px solid #E3E8EF;border-radius:13px;overflow:hidden;margin-bottom:8px}
    .priority-row{display:grid;grid-template-columns:28px 1fr 58px;gap:10px;align-items:center;padding:12px 15px;border-bottom:1px solid #EEF1F5}
    .priority-row:last-child{border-bottom:0}
    .priority-rank{color:#A6B0B9;font-size:12px}
    .priority-name{font-size:13px;font-weight:700;color:#183647}
    .priority-role{font-size:11px;margin-top:3px;color:#6B7F8C}
    .priority-score{font-size:13px;font-weight:700;text-align:right;color:#A56234}
    .microbar{height:3px;background:#F1E8DE;margin-top:5px;border-radius:3px;overflow:hidden}
    .microbar i{display:block;height:3px;background:#CB905F}
    .legend-item{display:inline-flex;align-items:center;margin:6px 12px 5px 0;font-size:11px;color:#647B8A}
    .legend-item i{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:5px}
    .node-heading{margin:16px 0 18px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
    .node-heading span{font-size:11px;letter-spacing:.14em;color:#6C8093}
    .node-heading h2{margin:0;padding:0;font-size:28px}
    .node-heading b{font-size:12px;border:1px solid;padding:5px 12px;border-radius:20px}
    @media(max-width:950px){.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.workspace-hero{padding:22px}.workspace-hero h1{font-size:25px!important}.status-pill{display:none}}
    @media(max-width:600px){.block-container{padding-left:16px;padding-right:16px}.kpi{padding:15px}.kpi .kpi-value{font-size:24px}.section-heading span{display:none}}
    </style>''', unsafe_allow_html=True)
