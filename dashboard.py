import os, json, tempfile
import pandas as pd
from scipy import stats
import plotly.graph_objects as go
import folium
from folium.plugins import MarkerCluster, SideBySideLayers
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium

BASE = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(page_title="Prague Mapped by People and Satellites",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    header[data-testid="stHeader"] { display:none !important; }
    [data-testid="stToolbar"]      { display:none !important; }
    [data-testid="stDecoration"]   { display:none !important; }
    #MainMenu                      { display:none !important; }
    footer                         { display:none !important; }

    html, body { overflow:hidden !important; margin:0 !important; }
    .block-container { padding:0 !important; max-width:100% !important; }

    /* Fixed header: always 74px at top */
    #app-header {
        position:fixed !important; top:0 !important;
        left:0 !important; right:0 !important;
        height:74px !important; z-index:999 !important;
        overflow:hidden !important;
    }

    /* KPI strip */
    #kpi-bar {
        position:fixed !important; top:74px !important;
        left:0 !important; right:0 !important;
        height:36px !important; z-index:998 !important;
        overflow:hidden !important;
    }

    /* Main block: fixed from 110px (header 74 + kpi 36) to bottom */
    [data-testid="stHorizontalBlock"] {
        position:fixed !important;
        top:110px !important; bottom:0 !important;
        left:0 !important; right:0 !important;
        width:100% !important; height:auto !important;
        align-items:stretch !important;
        overflow:hidden !important;
        z-index:1 !important;
    }
    [data-testid="stColumn"]:first-child {
        background:#fff !important; border-right:1px solid #dde !important;
        padding:12px 12px !important;
        overflow-y:auto !important; height:100% !important;
    }
    [data-testid="stColumn"]:last-child {
        background:#fff !important; border-left:1px solid #dde !important;
        padding:8px 10px !important;
        overflow-y:auto !important; height:100% !important;
    }
    [data-testid="stColumn"]:nth-child(2) {
        padding:0 !important; overflow:hidden !important; height:100% !important;
    }
    [data-testid="stColumn"]:nth-child(2) iframe {
        height:100% !important; min-height:380px !important;
        width:100% !important; display:block !important;
    }
    [data-testid="stColumn"]:nth-child(2) > div,
    [data-testid="stColumn"]:nth-child(2) > div > div,
    [data-testid="stColumn"]:nth-child(2) > div > div > div {
        height:100% !important; min-height:0 !important;
    }

    div[data-testid="stRadio"] > label { display:none !important; }
    div[data-testid="stSelectbox"]       { margin-bottom:2px !important; }
    div[data-testid="stSelectbox"] label { font-size:11px !important; }
    p { margin:0; }
    #sp-toggle:checked ~ #sp-info-box { display:block !important; }
</style>
""", unsafe_allow_html=True)

# ── Header: position:fixed so it never shifts; spacer pushes doc flow below it ──
st.markdown(
    '<div id="app-header" style="background:#d6eaf8;border-bottom:3px solid #85b8d4;'
    'display:flex;align-items:center;padding:0">'
    '<table style="width:100%;height:74px;border-collapse:collapse;table-layout:fixed">'
    '<tr>'
    '<td style="padding:10px 30px;vertical-align:middle;width:100%">'
    '<div style="font-size:1.5rem;font-weight:800;color:#1a1a2e;line-height:1.2">'
    'Prague Mapped by People and Satellites</div>'
    '<div style="font-size:0.78rem;color:#2c5f7a;margin-top:3px">'
    'Participatory emotional mapping meets Copernicus satellite indicators: '
    'NDVI, night lights, land surface temperature and NO&#8322;</div>'
    '</td>'
    '</tr></table>'
    '</div>'
    '<div style="height:74px"></div>',
    unsafe_allow_html=True
)

def _kpi(value, label):
    return (f'<div style="display:flex;align-items:baseline;gap:5px">'
            f'<span style="font-size:15px;font-weight:800;color:#fff;letter-spacing:-.3px">{value}</span>'
            f'<span style="font-size:10px;color:#9dbdd4;text-transform:uppercase;letter-spacing:.5px">{label}</span>'
            f'</div>')

_MODES = ["🗺 Bivariate", "💬 Comments", "⟺ Compare"]

# ── Constants ──────────────────────────────────────────────────────────────────
BIVAR_COLORS = {
    "1-1":"#e8e8e8","2-1":"#dfb0d6","3-1":"#be64ac",
    "1-2":"#ace4e4","2-2":"#a5b4c2","3-2":"#8c62aa",
    "1-3":"#5ac8c8","2-3":"#5698b9","3-3":"#3b4994",
}
BIVAR_LABELS = {
    "1-1":"Low / Low","2-1":"Mid activity / Low env",
    "3-1":"High activity / Low env ⚠","1-2":"Low / Mid",
    "2-2":"Mid / Mid","3-2":"High activity / Mid env",
    "1-3":"Low / High","2-3":"Mid activity / High env",
    "3-3":"High / High ✓",
}
EMOTION_COLORS = {
    "Safety":"#1B3A5C","Proudness":"#E87D1E","Free Time":"#1A878A",
    "Traffic Hazard":"#C0392B","Green Space":"#27AE60",
    "Need for Change":"#8E44AD","Waste/Cleanliness":"#7F8C8D",
}
TOPIC_EMOTION = {
    "Safety":"Safety","Proudness":"Proudness","Free Time":"Free Time",
    "Green Space":"Green Space","Need to Change":"Need for Change",
    "Traffic Hazard":"Traffic Hazard","Waste Bin":"Waste/Cleanliness",
}

# ── Load data ──────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    c = pd.read_csv(os.path.join(BASE,"data","comments_with_grid.csv"),
                    encoding="utf-8-sig")
    c.columns = c.columns.str.strip()
    h = pd.read_csv(os.path.join(BASE,"data","hex_all_topics.csv"),
                    encoding="utf-8-sig")
    h.columns = h.columns.str.strip()
    with open(os.path.join(BASE,"hex_grid.geojson"), encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj["features"]:
        p = feat["properties"]
        for k in list(p.keys()):
            if "GRID_ID" in k and k != "GRID_ID":
                p["GRID_ID"] = p.pop(k); break
    return c, h, gj

comments, hex_topics, geojson = load_data()

# ── Pre-compute KPI numbers ────────────────────────────────────────────────────
_total_marks    = int(pd.to_numeric(hex_topics["respondents"], errors="coerce").fillna(0).sum())
_total_hexes    = len(geojson["features"])
_hexes_with_data = int(hex_topics.groupby("GRID_ID")["respondents"]
                       .apply(lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum() > 0)
                       .sum())
_n_respondents  = int(comments["user_id"].nunique()) if "user_id" in comments.columns else "—"

# ── Pre-compute Spearman r per topic ──────────────────────────────────────────
@st.cache_data
def compute_spearman(_hex_topics):
    out = {}
    for topic, tdf in _hex_topics.groupby("topic"):
        x = pd.to_numeric(tdf["x_val"], errors="coerce")
        y = pd.to_numeric(tdf["y_val"], errors="coerce")
        mask = x.notna() & y.notna()
        if mask.sum() >= 5:
            r, p = stats.spearmanr(x[mask], y[mask])
            out[topic] = {"r": float(r), "p": float(p), "n": int(mask.sum())}
        else:
            out[topic] = {"r": None, "p": None, "n": 0}
    return out

_spearman = compute_spearman(hex_topics)

@st.cache_data
def compute_spearman_multi(_hex_topics):
    out = {}
    for topic, tdf in _hex_topics.groupby("topic"):
        out[topic] = {}
        for ylbl, ydf in tdf.groupby("y_label"):
            x = pd.to_numeric(ydf["x_val"], errors="coerce")
            y = pd.to_numeric(ydf["y_val"], errors="coerce")
            mask = x.notna() & y.notna()
            if mask.sum() >= 5:
                r, p = stats.spearmanr(x[mask], y[mask])
                out[topic][str(ylbl)] = {"r": float(r), "p": float(p)}
    return out

_spearman_multi = compute_spearman_multi(hex_topics)

def _r_interpret(r, topic, indicator):
    if r is None:
        return ""
    strength = "strong" if abs(r) >= 0.5 else "moderate" if abs(r) >= 0.3 else "weak"
    _topic_desc = {
        "Safety":          "higher safety concern",
        "Proudness":       "stronger place pride",
        "Free Time":       "more free time activity",
        "Green Space":     "greater green space demand",
        "Need to Change":  "higher need for change",
        "Traffic Hazard":  "higher traffic hazard perception",
        "Waste Bin":       "more waste/cleanliness concern",
    }
    _ind_pos = {
        "ndvi":        "more vegetation",
        "night":       "more artificial light at night",
        "light":       "more artificial light at night",
        "lst":         "higher surface temperature",
        "temp":        "higher surface temperature",
        "heat":        "higher surface temperature",
        "no2":         "higher air pollution (NO₂)",
        "nitrogen":    "higher air pollution (NO₂)",
        "water":       "greater distance from water",
        "distance":    "greater distance from water",
    }
    _ind_neg = {
        "ndvi":        "less vegetation",
        "night":       "less artificial light",
        "light":       "less artificial light",
        "lst":         "lower surface temperature",
        "temp":        "lower surface temperature",
        "heat":        "lower surface temperature",
        "no2":         "lower air pollution (NO₂)",
        "nitrogen":    "lower air pollution (NO₂)",
        "water":       "closer proximity to water",
        "distance":    "closer proximity to water",
    }
    t_desc = _topic_desc.get(topic, f"higher {topic.lower()} activity")
    ind_lower = indicator.lower()
    env_desc = None
    for k in (_ind_pos if r > 0 else _ind_neg):
        if k in ind_lower:
            env_desc = (_ind_pos if r > 0 else _ind_neg)[k]
            break
    if env_desc:
        return f"{strength.capitalize()} link: hexagons with {t_desc} tend to have {env_desc}."
    return f"{strength.capitalize()} {'positive' if r > 0 else 'negative'} correlation between {topic} and {indicator}."

# ── Pre-compute hex bounds for fit_bounds ─────────────────────────────────────
_all_coords = []
for _feat in geojson["features"]:
    _g = _feat["geometry"]
    if _g["type"] == "Polygon":
        _all_coords.extend(_g["coordinates"][0])
    elif _g["type"] == "MultiPolygon":
        for _poly in _g["coordinates"]:
            _all_coords.extend(_poly[0])
_MAP_BOUNDS = [[min(c[1] for c in _all_coords), min(c[0] for c in _all_coords)],
               [max(c[1] for c in _all_coords), max(c[0] for c in _all_coords)]]
_MAP_CENTER = [(_MAP_BOUNDS[0][0] + _MAP_BOUNDS[1][0]) / 2,
               (_MAP_BOUNDS[0][1] + _MAP_BOUNDS[1][1]) / 2]

# ── KPI strip (position:fixed so render order doesn't affect visual placement) ─
st.markdown(
    '<div id="kpi-bar" style="background:#1a1a2e;display:flex;align-items:center;'
    'padding:0 28px;gap:36px;height:36px">'
    + _kpi(f"{_total_marks:,}", "total marks")
    + _kpi(f"{_total_hexes}", "hexagons · ~1 km² each")
    + _kpi(f"{_n_respondents:,}" if isinstance(_n_respondents, int) else _n_respondents, "respondents")
    + _kpi("7", "topics")
    + _kpi("2021", "survey year")
    + '</div>'
    '<div style="height:36px"></div>',
    unsafe_allow_html=True
)

def shape_centroid(geom):
    try:
        coords = geom["coordinates"][0]
        return [sum(c[1] for c in coords)/len(coords),
                sum(c[0] for c in coords)/len(coords)]
    except: return None

def make_style(tdf):
    def fn(feat):
        gid   = feat["properties"].get("GRID_ID","")
        color = tdf.loc[gid,"color"] if gid in tdf.index else "#dddddd"
        return {"fillColor":color,"color":"#666","weight":0.5,"fillOpacity":0.75}
    return fn

TOPIC_BASE_COLORS = {
    "Safety":"#1B3A5C","Proudness":"#E87D1E","Free Time":"#1A878A",
    "Green Space":"#27AE60","Need to Change":"#8E44AD",
    "Traffic Hazard":"#C0392B","Waste Bin":"#7F8C8D",
}

def topic_gradient(topic_name, n=5):
    """Return n shades from light → topic signature color."""
    base = TOPIC_BASE_COLORS.get(topic_name, "#888888")
    r,g,b = int(base[1:3],16), int(base[3:5],16), int(base[5:7],16)
    return [f"#{int(255+(r-255)*(i+1)/n):02x}"
            f"{int(255+(g-255)*(i+1)/n):02x}"
            f"{int(255+(b-255)*(i+1)/n):02x}" for i in range(n)]

def make_choropleth_style(tdf, topic_name):
    """Color hexagons with topic's signature color; vary opacity by activity quintile."""
    base  = TOPIC_BASE_COLORS.get(topic_name, "#888888")
    opacs = [0.15, 0.30, 0.50, 0.70, 0.90]
    vals  = pd.to_numeric(tdf["x_val"], errors="coerce").fillna(0)
    try:
        qs = pd.qcut(vals.rank(method="first"), q=5,
                     labels=[0,1,2,3,4], duplicates="drop")
    except Exception:
        qs = pd.Series(2, index=tdf.index)
    op_map = {gid: opacs[int(q)] for gid, q in qs.items()}
    def fn(feat):
        gid = feat["properties"].get("GRID_ID","")
        return {"fillColor": base,
                "fillOpacity": op_map.get(gid, 0.3),
                "color":"#555","weight":0.4}
    return fn

def choropleth_hex_colors(tdf, topic_name):
    """Returns {GRID_ID: actual_hex_color} blending white → topic base color by activity quintile."""
    base = TOPIC_BASE_COLORS.get(topic_name, "#888888")
    r0,g0,b0 = int(base[1:3],16), int(base[3:5],16), int(base[5:7],16)
    weights = [0.12, 0.28, 0.50, 0.72, 0.92]
    shades = [f"#{int(255+(r0-255)*w):02x}{int(255+(g0-255)*w):02x}{int(255+(b0-255)*w):02x}"
              for w in weights]
    vals = pd.to_numeric(tdf["x_val"], errors="coerce").fillna(0)
    try:
        qs = pd.qcut(vals.rank(method="first"), q=5, labels=[0,1,2,3,4], duplicates="drop")
    except Exception:
        qs = pd.Series(2, index=tdf.index)
    return {gid: shades[int(q)] for gid, q in qs.items()}

def highlight_fn(feat):
    return {"weight":2,"color":"#222","fillOpacity":0.9}

def _pct_label(p):
    if p is None: return ""
    if p >= 80:   return "Top 20%"
    if p >= 60:   return "Above avg"
    if p >= 40:   return "Average"
    if p >= 20:   return "Below avg"
    return "Bottom 20%"

def popup_html(gid, tdf, cbh, pct_data=None):
    if gid not in tdf.index:
        return f"<b>{gid}</b><br>No data"
    row   = tdf.loc[gid]
    bv    = BIVAR_LABELS.get(str(row.get("bivar_class", "")), "—")
    y_lbl = row.get("y_label", "Indicator")
    y_val = row.get("y_val", "—")
    cx    = cbh.get(gid, [])

    pct       = (pct_data or {}).get(gid, {})
    x_pct     = pct.get("x_pct")
    y_pct     = pct.get("y_pct")
    resp_pct  = pct.get("resp_pct", 0)
    resp      = pct.get("resp", row.get("respondents", "—"))

    # one-line interpretation
    interp = ""
    if x_pct is not None:
        act = _pct_label(x_pct).lower()
        env = _pct_label(y_pct).lower() if y_pct is not None else "unknown"
        interp = f"{act} activity &nbsp;·&nbsp; {env} {str(y_lbl).lower()}"

    # respondent mini-bar
    resp_bar = (
        f'<div style="display:flex;align-items:center;gap:5px;margin:3px 0 5px">'
        f'<div style="flex:1;background:#e8e8e8;border-radius:3px;height:6px">'
        f'<div style="background:#1B3A5C;width:{resp_pct}%;height:6px;'
        f'border-radius:3px;min-width:2px"></div></div>'
        f'<span style="font-size:11px;font-weight:700;color:#1a1a2e;'
        f'white-space:nowrap">{resp}</span></div>'
    )

    # percentile rank pills
    def pill(label, val, color):
        if val is None: return ""
        return (f'<span style="display:inline-block;background:{color};color:#fff;'
                f'font-size:9px;font-weight:700;padding:2px 7px;border-radius:10px;'
                f'margin-right:4px;margin-bottom:3px">{label}: {_pct_label(val)}</span>')

    pills = pill("Activity", x_pct, "#1B3A5C") + pill(y_lbl, y_pct, "#3b4994")

    c_html = "".join([
        f'<div style="font-size:11px;border-left:3px solid '
        f'{"#27AE60" if c["sentiment_label"]=="positive" else "#C0392B" if c["sentiment_label"]=="negative" else "#888"}'
        f';padding:2px 6px;margin:2px 0;line-height:1.4">{str(c["comment"])[:100]}</div>'
        for c in cx
    ]) or "<i style='font-size:10px;color:#aaa'>No comments</i>"

    return (
        f'<div style="font-family:sans-serif;min-width:230px;max-width:310px">'
        f'<b style="font-size:13px;color:#1a1a2e">{gid}</b>'
        f'<hr style="margin:4px 0;border-color:#eee">'
        + (f'<div style="font-size:11px;color:#2c5f7a;background:#eef6fb;'
           f'padding:5px 8px;border-radius:5px;margin-bottom:6px;line-height:1.5">'
           f'&#128204;&nbsp;{interp}</div>' if interp else "")
        + f'<div style="font-size:10px;font-weight:700;color:#555;text-transform:uppercase;'
          f'letter-spacing:.4px;margin-bottom:1px">Respondents</div>'
        + resp_bar
        + f'<div style="margin:4px 0 6px">{pills}</div>'
        + f'<table style="font-size:11px;width:100%;border-collapse:collapse">'
        + f'<tr><td style="color:#888;padding:2px 0">{y_lbl}</td>'
          f'<td style="color:#333;font-weight:600">{y_val}</td></tr>'
        + f'<tr><td style="color:#888;padding:2px 0">Bivariate class</td>'
          f'<td style="color:#333">{bv}</td></tr>'
        + f'</table>'
        + f'<hr style="margin:5px 0;border-color:#eee">'
        + f'<b style="font-size:10px;color:#666">Comments:</b>'
        + c_html
        + f'</div>'
    )

# Emotion legend — bottom-left, Comments mode only
EMOTION_LEG = (
    '<div style="position:fixed;bottom:30px;left:10px;z-index:9999;'
    'background:rgba(255,255,255,0.93);padding:6px 9px;border-radius:8px;'
    'border:1px solid #ccc;font-size:11px;box-shadow:2px 2px 5px rgba(0,0,0,0.15)">'
    '<b>Emotions</b><br>'
    + "".join([f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
               f'background:{c};margin-right:5px;vertical-align:middle"></span>{e}<br>'
               for e,c in EMOTION_COLORS.items()])
    + '</div>'
)

# Sentiment legend — bottom-right inside map
SENTIMENT_LEG = (
    '<div style="position:fixed;bottom:30px;right:10px;z-index:9999;'
    'background:rgba(255,255,255,0.93);padding:6px 9px;border-radius:8px;'
    'border:1px solid #ccc;font-size:11px;box-shadow:2px 2px 5px rgba(0,0,0,0.15)">'
    '<b>Sentiment</b><br>'
    '<span style="color:#27AE60">&#9679; Positive</span><br>'
    '<span style="color:#888888">&#9679; Neutral</span><br>'
    '<span style="color:#C0392B">&#9679; Negative</span>'
    '</div>'
)

# ── LAYOUT ─────────────────────────────────────────────────────────────────────
col_left, col_map, col_right = st.columns([2, 6, 2])

# ── LEFT PANEL ────────────────────────────────────────────────────────────────
with col_left:
    st.markdown(
        '<div style="font-size:14px;font-weight:800;color:#1a1a2e;margin-bottom:2px">Welcome!</div>'
        '<div style="font-size:11px;color:#2c5f7a;line-height:1.6;margin-bottom:8px">'
        'Explore how Prague residents emotionally map their city alongside '
        'Copernicus satellite data to reveal where urban quality and lived experience align or conflict.'
        '</div>'
        '<hr style="margin:6px 0;border-color:#e0e0e0">'
        '<div style="font-size:13px;font-weight:700;margin-bottom:4px">View Mode</div>',
        unsafe_allow_html=True)
    mode = st.selectbox("View Mode", _MODES, label_visibility="collapsed", key="mode_radio")
    st.markdown(
        '<hr style="margin:8px 0;border-color:#e0e0e0">'
        '<div style="font-size:13px;font-weight:700;margin-bottom:6px">How to Use</div>'
        '<div style="font-size:11px;color:#444;line-height:1.8">'
        '<b>🗺 Bivariate</b> — hex map per topic<br>'
        '<b>💬 Comments</b> — residents&#39; comments<br>'
        '<b>⟺ Compare</b> — swipe two topics side by side<br>'
        'Click any hexagon for details.'
        '</div>'
        '<hr style="margin:10px 0;border-color:#e0e0e0">'
        '<div style="font-size:13px;font-weight:700;margin-bottom:4px">Data Sources</div>'
        '<div style="font-size:11px;color:#555;line-height:1.8">'
        'Emotional Map: emotionalmap.eu<br>'
        'P&#225;nek et al., 2021<br>'
        'Copernicus / Sentinel-2 2023<br>'
        'Google Earth Engine 2023<br>'
        'GHSL Population 2020'
        '</div>',
        unsafe_allow_html=True
    )

    sel_age, sel_gender, sel_topic_comment = "All", "All", "All"

# ── RIGHT PANEL ────────────────────────────────────────────────────────────────
topics = list(TOPIC_EMOTION.keys())
with col_right:
    if mode == "💬 Comments":
        # ── Filters for Comments mode ──────────────────────────────────────────
        sel_topic  = topics[0]
        sel_topic2 = topics[1]
        st.markdown(
            '<div style="font-size:14px;font-weight:700;margin-bottom:8px">Filters</div>',
            unsafe_allow_html=True)
        st.markdown('<span style="font-size:11px;font-weight:600">Age Group</span>',
                    unsafe_allow_html=True)
        sel_age = st.selectbox("Age",
                               ["All"]+["0-19","20-29","30-39","40-49","50-59","60-69","70+"],
                               label_visibility="collapsed", key="age_c")
        st.markdown('<span style="font-size:11px;font-weight:600">Sex</span>',
                    unsafe_allow_html=True)
        sel_gender = st.selectbox("Gender",
                                  ["All"]+sorted(comments["gender"].dropna().unique().tolist()),
                                  label_visibility="collapsed", key="gen_c")
        st.markdown(
            '<div style="font-size:11px;font-weight:600;margin-top:6px;margin-bottom:2px">Topic</div>',
            unsafe_allow_html=True)
        sel_topic_comment = st.radio(
            "Topic", ["All"] + list(EMOTION_COLORS.keys()),
            label_visibility="collapsed", key="topic_c")
    else:
        # ── Bivariate legend + Topic for Bivariate / Compare modes ────────────
        _cur_topic = st.session_state.get("topic_bv", topics[0])
        _ylbl_rows = hex_topics[hex_topics["topic"] == _cur_topic]["y_label"]
        _ind_lbl   = str(_ylbl_rows.iloc[0]) if len(_ylbl_rows) > 0 else "Env"
        st.markdown(
            '<div style="font-size:14px;font-weight:700;margin-bottom:6px">'
            'Bivariate Legend</div>'
            '<table style="border-collapse:collapse;font-size:12px">'
            '<tr>'
            '<td style="padding-right:4px">'
            '<div style="writing-mode:vertical-rl;transform:rotate(180deg);'
            'font-weight:600;font-size:11px;height:110px;'
            'display:flex;align-items:center;justify-content:center">Activity ↑</div></td>'
            '<td><table style="border-collapse:collapse">'
            '<tr>'
            '<td style="font-size:11px;padding:2px 4px;font-weight:600"></td>'
            '<td style="font-size:11px;padding:2px 4px;text-align:center">Low</td>'
            '<td style="font-size:11px;padding:2px 4px;text-align:center">Mid</td>'
            '<td style="font-size:11px;padding:2px 4px;text-align:center">High</td>'
            '</tr><tr>'
            '<td style="font-size:11px;padding:2px 4px;font-weight:600">High</td>'
            '<td style="background:#be64ac;width:30px;height:26px;border:1px solid #fff"></td>'
            '<td style="background:#8c62aa;width:30px;height:26px;border:1px solid #fff"></td>'
            '<td style="background:#3b4994;width:30px;height:26px;border:1px solid #fff"></td>'
            '</tr><tr>'
            '<td style="font-size:11px;padding:2px 4px;font-weight:600">Mid</td>'
            '<td style="background:#dfb0d6;width:30px;height:26px;border:1px solid #fff"></td>'
            '<td style="background:#a5b4c2;width:30px;height:26px;border:1px solid #fff"></td>'
            '<td style="background:#5698b9;width:30px;height:26px;border:1px solid #fff"></td>'
            '</tr><tr>'
            '<td style="font-size:11px;padding:2px 4px;font-weight:600">Low</td>'
            '<td style="background:#e8e8e8;width:30px;height:26px;border:1px solid #fff"></td>'
            '<td style="background:#ace4e4;width:30px;height:26px;border:1px solid #fff"></td>'
            '<td style="background:#5ac8c8;width:30px;height:26px;border:1px solid #fff"></td>'
            '</tr><tr>'
            '<td></td>'
            f'<td colspan="3" style="font-size:11px;font-weight:600;text-align:center;'
            f'padding-top:4px">{_ind_lbl} &#8594;</td>'
            '</tr></table></td></tr></table>'
            f'<div style="font-size:11px;color:#555;margin-top:6px;line-height:1.7">'
            f'<span style="color:#be64ac;font-size:14px">&#9632;</span> High demand, Low {_ind_lbl}<br>'
            f'<span style="color:#3b4994;font-size:14px">&#9632;</span> Low demand, High {_ind_lbl}<br>'
            '<span style="color:#a5b4c2;font-size:14px">&#9632;</span> Average both'
            '</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<div style="font-size:13px;font-weight:700;margin-top:10px;margin-bottom:4px">Topic</div>',
            unsafe_allow_html=True)
        sel_topic  = st.selectbox("Topic", topics, label_visibility="collapsed", key="topic_bv")
        sel_topic2 = [t for t in topics if t != sel_topic][0]
        if mode == "⟺ Compare":
            st.markdown(
                '<div style="font-size:13px;font-weight:700;margin-top:8px;margin-bottom:4px">'
                'Compare with</div>', unsafe_allow_html=True)
            sel_topic2 = st.selectbox("Compare with",
                                      [t for t in topics if t != sel_topic],
                                      label_visibility="collapsed", key="t2")

        # ── Spearman correlation card ──────────────────────────────────────────
        sp = _spearman.get(sel_topic, {})
        if sp.get("r") is not None:
            r_val = sp["r"]
            p_val = sp["p"]
            sig   = p_val < 0.05
            sig_color  = "#27AE60" if sig else "#888"
            sig_label  = "significant ✓" if sig else "not significant"
            p_str      = "< 0.001" if p_val < 0.001 else f"= {p_val:.3f}"
            bar_w      = int(abs(r_val) * 100)
            bar_color  = "#3b4994" if r_val >= 0 else "#be64ac"
            st.markdown(
                '<hr style="margin:8px 0;border-color:#eee">'
                '<input type="checkbox" id="sp-toggle" style="display:none">'
                '<div style="font-size:11px;font-weight:700;color:#555;'
                'text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;'
                'display:flex;align-items:center;gap:5px">'
                'Spearman Correlation'
                '<label for="sp-toggle" '
                'style="display:inline-flex;align-items:center;justify-content:center;'
                'width:14px;height:14px;border-radius:50%;background:#85b8d4;color:#fff;'
                'font-size:9px;font-weight:800;cursor:pointer;flex-shrink:0;'
                'line-height:1;user-select:none">i</label>'
                '</div>'
                '<div id="sp-info-box" style="display:none;font-size:10px;color:#333;'
                'line-height:1.7;border:1px solid #85b8d4;border-radius:4px;'
                'padding:8px 10px;margin-bottom:6px;background:#f0f7fb">'
                '<b>What is Spearman r?</b><br>'
                'Measures how consistently one variable increases as the other does, '
                'using ranks rather than raw values.<br><br>'
                '<b>r ranges from −1 to +1:</b><br>'
                '&nbsp;0.0 – 0.3 &nbsp;= weak<br>'
                '&nbsp;0.3 – 0.5 &nbsp;= moderate<br>'
                '&nbsp;&gt;0.5 &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= strong<br><br>'
                '<b>Negative r</b> means as one variable rises the other falls.<br>'
                '<b>p &lt; 0.05</b> means the result is statistically significant.'
                '</div>',
                unsafe_allow_html=True)
            st.markdown(
                f'<div style="font-size:22px;font-weight:800;color:#1a1a2e;line-height:1">'
                f'r = {r_val:+.3f}</div>'
                f'<div style="background:#eee;border-radius:3px;height:5px;margin:4px 0">'
                f'<div style="background:{bar_color};width:{bar_w}%;height:5px;border-radius:3px"></div></div>'
                f'<div style="font-size:11px;color:#555">p {p_str} &nbsp;·&nbsp; '
                f'<span style="color:{sig_color};font-weight:600">{sig_label}</span></div>'
                f'<div style="font-size:10px;color:#888;margin-top:2px">n = {sp["n"]} hexagons</div>'
                f'<div style="font-size:10px;color:#2c5f7a;margin-top:5px;line-height:1.4;'
                f'background:#f0f7fb;border-left:3px solid #85b8d4;padding:4px 6px;border-radius:0 4px 4px 0">'
                f'{_r_interpret(r_val, sel_topic, _ind_lbl)}</div>',
                unsafe_allow_html=True)
        if mode == "⟺ Compare":
            sp2 = _spearman.get(sel_topic2, {})
            if sp2.get("r") is not None:
                r2 = sp2["r"]; p2 = sp2["p"]
                p2_str = "< 0.001" if p2 < 0.001 else f"= {p2:.3f}"
                st.markdown(
                    f'<div style="font-size:11px;color:#555;margin-top:4px">'
                    f'<b>{sel_topic2}:</b> r = {r2:+.3f}, p {p2_str}</div>',
                    unsafe_allow_html=True)

        # ── Per-indicator bar chart ────────────────────────────────────────────
        def _ind_bar_chart(topic):
            sp_multi = _spearman_multi.get(topic, {})
            if not sp_multi:
                return
            lbls   = list(sp_multi.keys())
            rs     = [sp_multi[l]["r"] for l in lbls]
            ps     = [sp_multi[l]["p"] for l in lbls]
            colors  = ["#27AE60" if r >= 0 else "#E74C3C" for r in rs]
            stars   = ["***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns" for p in ps]
            texts   = [f"r={r:+.3f}<br>{s}" for r, s in zip(rs, stars)]
            hovers  = [_r_interpret(r, topic, lbl) for r, lbl in zip(rs, lbls)]
            ypad    = 0.12
            ymin    = min(min(rs) - ypad, -0.25)
            ymax    = max(max(rs) + ypad,  0.25)
            fig = go.Figure(go.Bar(
                x=lbls, y=rs,
                width=0.35,
                marker_color=colors,
                marker_line_width=0,
                text=texts, textposition="outside",
                textfont_size=8,
                cliponaxis=False,
                customdata=hovers,
                hovertemplate="<b>%{x}</b><br>r = %{y:+.3f}<br><br>%{customdata}<extra></extra>",
            ))
            fig.update_layout(
                title_text=topic,
                title_font_size=10,
                title_x=0.5,
                yaxis_title="r",
                yaxis_tickfont_size=8,
                yaxis_zeroline=True,
                yaxis_zerolinecolor="#333",
                yaxis_zerolinewidth=1.5,
                yaxis_range=[ymin, ymax],
                xaxis_tickfont_size=8,
                margin=dict(l=28, r=6, t=26, b=4),
                height=185,
                plot_bgcolor="white",
                paper_bgcolor="white",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})

        _ind_bar_chart(sel_topic)
        if mode == "⟺ Compare":
            _ind_bar_chart(sel_topic2)

# ── MAP SECTION ────────────────────────────────────────────────────────────────
with col_map:
    topic_df  = hex_topics[hex_topics["topic"] == sel_topic].set_index("GRID_ID")
    topic_df2 = hex_topics[hex_topics["topic"] == sel_topic2].set_index("GRID_ID")

    filt = comments.copy()
    if sel_age    != "All": filt = filt[filt["age"]    == sel_age]
    if sel_gender != "All": filt = filt[filt["gender"] == sel_gender]
    if sel_topic_comment != "All": filt = filt[filt["emotion"] == sel_topic_comment]

    comments_by_hex = (
        filt.dropna(subset=["GRID_ID"])
        .groupby("GRID_ID")
        .apply(lambda g: g.head(3)[["comment","sentiment_label"]].to_dict("records"))
        .to_dict()
    )

    # ── BIVARIATE MAP ──────────────────────────────────────────────────────────
    if mode == "🗺 Bivariate":
        # Pre-compute percentile ranks for popup enrichment
        _px = pd.to_numeric(topic_df["x_val"], errors="coerce")
        _py = pd.to_numeric(topic_df["y_val"], errors="coerce")
        _pr = pd.to_numeric(topic_df["respondents"], errors="coerce").fillna(0)
        _max_r = max(_pr.max(), 1)
        _xpct = _px.rank(pct=True, na_option="keep") * 100
        _ypct = _py.rank(pct=True, na_option="keep") * 100
        _pct_data = {
            gid: {
                "x_pct":    round(_xpct[gid]) if pd.notna(_xpct.get(gid, float("nan"))) else None,
                "y_pct":    round(_ypct[gid]) if pd.notna(_ypct.get(gid, float("nan"))) else None,
                "resp_pct": int(_pr.get(gid, 0) / _max_r * 100),
                "resp":     int(_pr.get(gid, 0)),
            }
            for gid in topic_df.index
        }

        m = folium.Map(location=[50.075, 14.437], zoom_start=11, tiles="CartoDB positron")
        # Add each hex individually so popup triggers on click anywhere on the polygon
        for feat in geojson["features"]:
            gid   = feat["properties"].get("GRID_ID", "")
            color = topic_df.loc[gid, "color"] if gid in topic_df.index else "#dddddd"
            folium.GeoJson(
                feat,
                style_function=lambda x, c=color: {
                    "fillColor": c, "color": "#666",
                    "weight": 0.5, "fillOpacity": 0.75
                },
                highlight_function=highlight_fn,
                tooltip=gid,
                popup=folium.Popup(
                    popup_html(gid, topic_df, comments_by_hex, _pct_data),
                    max_width=320),
            ).add_to(m)
        m.get_root().html.add_child(folium.Element(
            '<script>setTimeout(function(){'
            'Object.values(window).filter(function(v){'
            'return v&&v._leaflet_id;}).forEach(function(mp){'
            'try{mp.invalidateSize();}catch(e){}});},400);</script>'))
        st_folium(m, width=None, height=900, returned_objects=[])

    # ── COMMENTS MAP ──────────────────────────────────────────────────────────
    elif mode == "💬 Comments":
        m = folium.Map(location=[50.075, 14.437], zoom_start=11, tiles="CartoDB positron")
        cluster = MarkerCluster(max_cluster_radius=50).add_to(m)
        sample  = filt.sample(min(len(filt), 3000), random_state=42)
        for _, row in sample.iterrows():
            ec = EMOTION_COLORS.get(str(row.get("emotion","")), "#888")
            sc = ("#27AE60" if row["sentiment_label"]=="positive"
                  else "#C0392B" if row["sentiment_label"]=="negative" else "#888")
            folium.CircleMarker(
                location=[row["y"], row["x"]], radius=7,
                color=ec, fill=True, fill_color=ec,
                fill_opacity=0.8, weight=1,
                popup=folium.Popup(
                    f'<b style="color:{ec}">{row["emotion"]}</b><br>'
                    f'{str(row["comment"])[:180]}<br>'
                    f'<small>Age: {row["age"]} | {row["gender"]} | '
                    f'<span style="color:{sc}">{row["sentiment_label"]}</span></small>',
                    max_width=270),
                tooltip=str(row["comment"])[:120],
            ).add_to(cluster)
        m.get_root().html.add_child(folium.Element(EMOTION_LEG))
        m.get_root().html.add_child(folium.Element(SENTIMENT_LEG))
        m.get_root().html.add_child(folium.Element(
            '<script>setTimeout(function(){'
            'Object.values(window).filter(function(v){'
            'return v&&v._leaflet_id;}).forEach(function(mp){'
            'try{mp.invalidateSize();}catch(e){}});},400);</script>'))
        st_folium(m, width=None, height=900, returned_objects=[])

    # ── COMPARE MAP — custom swipe, no SideBySideLayers plugin ───────────────────
    elif mode == "⟺ Compare":
        # Build per-hexagon color dicts for both topics
        lc_map = {feat["properties"].get("GRID_ID",""):
                  (topic_df.loc[feat["properties"]["GRID_ID"], "color"]
                   if feat["properties"].get("GRID_ID","") in topic_df.index else "#dddddd")
                  for feat in geojson["features"]}
        rc_map = {feat["properties"].get("GRID_ID",""):
                  (topic_df2.loc[feat["properties"]["GRID_ID"], "color"]
                   if feat["properties"].get("GRID_ID","") in topic_df2.index else "#dddddd")
                  for feat in geojson["features"]}

        lc_js  = json.dumps(lc_map)
        rc_js  = json.dumps(rc_map)
        gj_js  = json.dumps(geojson)
        lbl_l  = sel_topic
        lbl_r  = sel_topic2
        col_l  = TOPIC_BASE_COLORS.get(sel_topic,  "#555")
        col_r  = TOPIC_BASE_COLORS.get(sel_topic2, "#555")

        html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html,body{{margin:0;padding:0;height:100%;overflow:hidden;}}
#map{{height:100%;width:100%;position:relative;}}
#divider{{position:absolute;top:0;bottom:0;width:4px;
          left:calc(50% - 2px);
          background:#fff;box-shadow:0 0 8px rgba(0,0,0,.6);
          z-index:1000;cursor:ew-resize;}}
#handle{{position:absolute;
         left:50%;top:50%;
         transform:translate(-50%,-50%);
         width:46px;height:46px;background:#fff;border-radius:50%;
         box-shadow:0 2px 10px rgba(0,0,0,.4);
         display:flex;align-items:center;justify-content:center;
         font-size:22px;font-weight:900;cursor:ew-resize;user-select:none;
         z-index:1001;}}
#lbl-l{{position:absolute;top:12px;left:60px;z-index:1001;
        background:{col_l};color:#fff;padding:4px 14px;
        border-radius:20px;font-size:12px;font-weight:700;font-family:sans-serif;pointer-events:none;}}
#lbl-r{{position:absolute;top:12px;right:12px;z-index:1001;
        background:{col_r};color:#fff;padding:4px 14px;
        border-radius:20px;font-size:12px;font-weight:700;font-family:sans-serif;pointer-events:none;}}
</style>
</head>
<body style="height:100%">
<div id="map">
  <div id="divider"></div>
  <div id="handle">&#8596;</div>
  <div id="lbl-l">&#9664; {lbl_l}</div>
  <div id="lbl-r">{lbl_r} &#9654;</div>
</div>
<script>
var GJ = {gj_js};
var LC = {lc_js};
var RC = {rc_js};

/* Position divider + handle at true center immediately, before Leaflet loads */
(function(){{
  var visH;
  try {{ visH = window.frameElement ? window.frameElement.offsetHeight : window.innerHeight; }}
  catch(e) {{ visH = window.innerHeight; }}
  var w2 = Math.round(window.innerWidth / 2);
  var h2 = Math.round(visH / 2);
  var d  = document.getElementById('divider');
  var h  = document.getElementById('handle');
  d.style.left = (w2-2)+'px';
  h.style.left = w2+'px';
  h.style.top  = h2+'px';
}})();

var map = L.map('map',{{zoomControl:true}}).setView([50.075,14.437],11);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',
  {{attribution:'&copy; CartoDB',maxZoom:19}}).addTo(map);

/* Each layer MUST have its own SVG renderer so they get separate <svg> elements */
var rL = L.svg();
var rR = L.svg();

var leftLayer = L.geoJSON(GJ,{{
  renderer: rL,
  style:function(f){{
    return {{fillColor:LC[f.properties.GRID_ID]||'#ddd',fillOpacity:.8,color:'#555',weight:.5}};
  }}
}}).addTo(map);

var rightLayer = L.geoJSON(GJ,{{
  renderer: rR,
  style:function(f){{
    return {{fillColor:RC[f.properties.GRID_ID]||'#ddd',fillOpacity:.8,color:'#555',weight:.5}};
  }}
}}).addTo(map);

var divEl    = document.getElementById('divider');
var handleEl = document.getElementById('handle');
var mapEl    = document.getElementById('map');

/* Read the ACTUAL rendered height of the iframe element in the parent page.
   window.innerHeight inside an iframe returns the iframe's height= attribute (900),
   not the CSS-overridden visible height. frameElement.offsetHeight is the truth. */
function getVisH(){{
  try {{
    if(window.frameElement) return window.frameElement.offsetHeight;
  }} catch(e) {{}}
  return window.innerHeight;
}}

function clip(x){{
  var w = mapEl.offsetWidth;
  x = Math.max(2, Math.min(x, w-2));
  /* Use the renderer containers directly so we know which SVG is left vs right */
  var lSvg = rL._container;
  var rSvg = rR._container;
  if(lSvg && rSvg){{
    /* getBoundingClientRect gives the true rendered position of the SVG,
       accounting for Leaflet's padding offset. Convert map-relative x
       to SVG-relative x by subtracting the SVG's left edge. */
    var mapRect = mapEl.getBoundingClientRect();
    var svgRect = lSvg.getBoundingClientRect();
    var svgW    = svgRect.width;
    var svgX    = (x + mapRect.left - svgRect.left);
    var pctL    = (svgX / svgW * 100).toFixed(2);
    var pctR    = (100 - parseFloat(pctL)).toFixed(2);
    lSvg.style.clipPath = 'inset(0 '+pctR+'% 0 0)';
    rSvg.style.clipPath = 'inset(0 0 0 '+pctL+'%)';
  }}
  divEl.style.left = (x-2)+'px';
  handleEl.style.left = x+'px';
  handleEl.style.top  = Math.round(getVisH()/2)+'px';
}}

/* Init clip as soon as map is ready, and again after a short delay */
map.whenReady(function(){{ clip(mapEl.offsetWidth/2); }});
setTimeout(function(){{ clip(mapEl.offsetWidth/2); }}, 150);
setTimeout(function(){{ clip(mapEl.offsetWidth/2); }}, 400);
map.on('move zoom', function(){{
  var x = parseFloat(divEl.style.left)+2 || mapEl.offsetWidth/2;
  clip(x);
}});

/* Drag — both divider line and handle are draggable */
var drag = false;
function startDrag(e){{ drag=true; map.dragging.disable(); e.preventDefault(); e.stopPropagation(); }}
divEl.addEventListener('mousedown', startDrag);
handleEl.addEventListener('mousedown', startDrag);
document.addEventListener('mousemove',function(e){{
  if(!drag) return;
  clip(e.clientX - mapEl.getBoundingClientRect().left);
}});
document.addEventListener('mouseup',function(){{ drag=false; map.dragging.enable(); }});
function startDragTouch(e){{ drag=true; map.dragging.disable(); e.preventDefault(); }}
divEl.addEventListener('touchstart', startDragTouch,{{passive:false}});
handleEl.addEventListener('touchstart', startDragTouch,{{passive:false}});
document.addEventListener('touchmove',function(e){{
  if(!drag) return;
  clip(e.touches[0].clientX - mapEl.getBoundingClientRect().left);
}},{{passive:false}});
document.addEventListener('touchend',function(){{ drag=false; map.dragging.enable(); }});
</script>
</body></html>"""
        components.html(html_content, height=900, scrolling=False)
