import os, json, tempfile
import pandas as pd
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
    .block-container { padding: 0 !important; max-width: 100% !important; }

    /* Left panel */
    [data-testid="stColumn"]:first-child {
        border-right: 1px solid #e0e0e0;
        background: #fff;
        padding: 10px 10px !important;
        overflow-y: auto;
    }
    /* Right panel */
    [data-testid="stColumn"]:last-child {
        border-left: 1px solid #e0e0e0;
        background: #fff;
        padding: 6px 8px !important;
        overflow-y: auto;
    }
    /* Map column */
    [data-testid="stColumn"]:nth-child(2) { padding: 0 !important; }

    /* Mode strip radio (outside columns) */
    div[data-testid="stRadio"] {
        background: #f0f2f6;
        padding: 4px 16px !important;
        margin: 0 !important;
        border-bottom: 1px solid #d0d0d0;
    }
    /* Topic / compare radio inside right column — override to plain */
    [data-testid="stColumn"]:last-child div[data-testid="stRadio"] {
        background: transparent !important;
        padding: 0 !important;
        margin: 0 !important;
        border-bottom: none !important;
        box-shadow: none !important;
    }

    div[data-testid="stRadio"] > label { display: none !important; }
    div[data-testid="stRadio"] label   { font-size: 12px !important; }
    div[data-testid="stSelectbox"]       { margin-bottom: 2px !important; }
    div[data-testid="stSelectbox"] label { font-size: 11px !important; }
    p { margin: 0; }
</style>
""", unsafe_allow_html=True)

# ── Header bar ────────────────────────────────────────────────────────────────
st.markdown(
    '<table style="width:100%;background:#d6eaf8;padding:10px 20px;'
    'border-collapse:collapse;border-bottom:2px solid #aac9e0">'
    '<tr>'
    '<td style="width:60%;vertical-align:middle;padding:6px 12px 6px 4px">'
    '<div style="font-size:1.35rem;font-weight:700;color:#1a1a2e">'
    'Prague Mapped by People and Satellites</div>'
    '<div style="font-size:0.78rem;color:#2c5f7a;margin-top:3px">'
    'Participatory emotional mapping meets Copernicus satellite indicators — '
    'NDVI, night lights, land surface temperature and NO&#8322;</div>'
    '</td>'
    '<td style="width:40%;vertical-align:middle;text-align:right;'
    'padding:6px 4px 6px 12px;border-left:1px solid #aac9e0">'
    '<div style="font-size:0.85rem;font-weight:700;color:#1a1a2e;margin-bottom:3px">'
    'Welcome!</div>'
    '<div style="font-size:0.72rem;color:#2c5f7a;line-height:1.55">'
    'Explore how Prague residents emotionally map their city alongside Copernicus '
    'satellite data to reveal where urban quality and lived experience align or conflict.'
    '</div>'
    '</td>'
    '</tr>'
    '</table>',
    unsafe_allow_html=True
)

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
    """Color by respondent count quantile using topic's own color gradient."""
    shades = topic_gradient(topic_name)
    vals   = pd.to_numeric(tdf["x_val"], errors="coerce").fillna(0)
    try:
        qs = pd.qcut(vals.rank(method="first"), q=5,
                     labels=[0,1,2,3,4], duplicates="drop")
    except Exception:
        qs = pd.Series(2, index=tdf.index)
    color_map = {gid: shades[int(q)] for gid, q in qs.items()}
    def fn(feat):
        gid = feat["properties"].get("GRID_ID","")
        return {"fillColor": color_map.get(gid,"#eeeeee"),
                "color":"#666","weight":0.5,"fillOpacity":0.8}
    return fn

def highlight_fn(feat):
    return {"weight":2,"color":"#222","fillOpacity":0.9}

def popup_html(gid, tdf, cbh):
    if gid not in tdf.index:
        return f"<b>{gid}</b><br>No data"
    row        = tdf.loc[gid]
    bv         = BIVAR_LABELS.get(str(row.get("bivar_class","")),"—")
    respondents= row.get("respondents","—")
    y_lbl      = row.get("y_label","Indicator")
    y_val      = row.get("y_val","—")
    cx         = cbh.get(gid,[])
    c_html = "".join([
        f'<div style="font-size:11px;border-left:3px solid '
        f'{"#27AE60" if c["sentiment_label"]=="positive" else "#C0392B" if c["sentiment_label"]=="negative" else "#888"}'
        f';padding:2px 5px;margin:2px 0">{str(c["comment"])[:100]}</div>'
        for c in cx
    ]) or "<i style='font-size:10px;color:#888'>No comments</i>"
    return (f'<div style="font-family:sans-serif;min-width:220px">'
            f'<b style="font-size:13px">{gid}</b><hr style="margin:3px 0">'
            f'<table style="font-size:12px;width:100%">'
            f'<tr style="background:#f5f5f5"><td><b>&#128100; Respondents</b></td>'
            f'<td><b>{respondents}</b></td></tr>'
            f'<tr><td><b>{y_lbl}</b></td><td>{y_val}</td></tr>'
            f'<tr><td><b>Bivariate class</b></td><td>{bv}</td></tr>'
            f'</table><hr style="margin:3px 0">'
            f'<b style="font-size:10px">Comments:</b>{c_html}</div>')

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

# ── Mode strip (above columns; defines `mode` before col_right runs) ──────────
_MODES = ["🗺 Bivariate", "💬 Comments", "⟺ Compare"]
mode = st.radio("mode", _MODES, horizontal=True,
                label_visibility="collapsed", key="mode_radio")

# ── LAYOUT ─────────────────────────────────────────────────────────────────────
col_left, col_map, col_right = st.columns([1.2, 4.6, 1.8])

# ── RIGHT PANEL ────────────────────────────────────────────────────────────────
with col_right:
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
        '<td colspan="3" style="font-size:11px;font-weight:600;text-align:center;'
        'padding-top:4px">Env. indicator &#8594;</td>'
        '</tr></table></td></tr></table>'
        '<div style="font-size:11px;color:#555;margin-top:6px;line-height:1.7">'
        '<span style="color:#be64ac;font-size:14px">&#9632;</span> High demand, Low env<br>'
        '<span style="color:#3b4994;font-size:14px">&#9632;</span> Low demand, High env<br>'
        '<span style="color:#a5b4c2;font-size:14px">&#9632;</span> Average both'
        '</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div style="font-size:13px;font-weight:700;margin-top:10px;margin-bottom:4px">Topic</div>',
        unsafe_allow_html=True)
    topics    = list(TOPIC_EMOTION.keys())
    sel_topic = st.radio("Topic", topics, label_visibility="collapsed")
    sel_topic2 = [t for t in topics if t != sel_topic][0]
    if mode == "⟺ Compare":
        st.markdown(
            '<div style="font-size:13px;font-weight:700;margin-top:8px;margin-bottom:4px">'
            'Compare with</div>', unsafe_allow_html=True)
        sel_topic2 = st.selectbox("Compare with",
                                  [t for t in topics if t != sel_topic],
                                  label_visibility="collapsed", key="t2")

# ── LEFT PANEL ─────────────────────────────────────────────────────────────────
with col_left:
    st.markdown(
        '<div style="font-size:13px;font-weight:700;margin-bottom:6px">How to Use</div>'
        '<div style="font-size:11px;color:#444;line-height:1.8">'
        '<b>🗺 Bivariate</b> — select a topic to see the hex map<br>'
        '<b>💬 Comments</b> — read residents&#39; comments by location<br>'
        '<b>⟺ Compare</b> — swipe to compare two topics side by side<br>'
        'Click any hexagon for details and comments.'
        '</div>'

        '<hr style="margin:12px 0;border-color:#e0e0e0">'
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

# ── MAP SECTION ────────────────────────────────────────────────────────────────
with col_map:
    topic_df  = hex_topics[hex_topics["topic"] == sel_topic].set_index("GRID_ID")
    topic_df2 = hex_topics[hex_topics["topic"] == sel_topic2].set_index("GRID_ID")

    # Age/gender filters — shown inside map column only in Comments mode
    if mode == "💬 Comments":
        fa, fb = st.columns(2)
        with fa:
            st.markdown('<span style="font-size:11px;font-weight:600">Age Group</span>',
                        unsafe_allow_html=True)
            sel_age = st.selectbox("Age",
                                   ["All"]+["0-19","20-29","30-39","40-49","50-59","60-69","70+"],
                                   label_visibility="collapsed", key="age_c")
        with fb:
            st.markdown('<span style="font-size:11px;font-weight:600">Gender</span>',
                        unsafe_allow_html=True)
            sel_gender = st.selectbox("Gender",
                                      ["All"]+sorted(comments["gender"].dropna().unique().tolist()),
                                      label_visibility="collapsed", key="gen_c")
    else:
        sel_age, sel_gender = "All", "All"

    filt = comments.copy()
    if sel_age    != "All": filt = filt[filt["age"]    == sel_age]
    if sel_gender != "All": filt = filt[filt["gender"] == sel_gender]

    comments_by_hex = (
        filt.dropna(subset=["GRID_ID"])
        .groupby("GRID_ID")
        .apply(lambda g: g.head(3)[["comment","sentiment_label"]].to_dict("records"))
        .to_dict()
    )

    # ── BIVARIATE MAP ──────────────────────────────────────────────────────────
    if mode == "🗺 Bivariate":
        m = folium.Map(location=[50.075,14.437], zoom_start=11,
                       tiles="CartoDB positron")
        folium.GeoJson(
            geojson,
            style_function=make_style(topic_df),
            highlight_function=highlight_fn,
            tooltip=folium.GeoJsonTooltip(
                fields=["GRID_ID"], aliases=["Cell:"]),
        ).add_to(m)
        for feat in geojson["features"]:
            gid = feat["properties"].get("GRID_ID","")
            c   = shape_centroid(feat["geometry"])
            if c:
                folium.Marker(
                    location=c,
                    popup=folium.Popup(
                        popup_html(gid, topic_df, comments_by_hex),
                        max_width=300),
                    icon=folium.DivIcon(html="", icon_size=(0,0))
                ).add_to(m)
        st_folium(m, width=None, height=660, returned_objects=[])

    # ── COMMENTS MAP ──────────────────────────────────────────────────────────
    elif mode == "💬 Comments":
        m = folium.Map(location=[50.075,14.437], zoom_start=11,
                       tiles="CartoDB positron")
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
        st_folium(m, width=None, height=660, returned_objects=[])

    # ── COMPARE MAP — swipe on one map via HTML ────────────────────────────────
    elif mode == "⟺ Compare":
        topic_df2 = hex_topics[hex_topics["topic"] == sel_topic2].set_index("GRID_ID")

        m = folium.Map(location=[50.075,14.437], zoom_start=11,
                       tiles="CartoDB positron")

        left_layer  = folium.FeatureGroup(name=sel_topic,  overlay=True)
        right_layer = folium.FeatureGroup(name=sel_topic2, overlay=True)

        folium.GeoJson(
            geojson,
            style_function=make_choropleth_style(topic_df, sel_topic),
            tooltip=folium.GeoJsonTooltip(
                fields=["GRID_ID"], aliases=["Cell:"]),
        ).add_to(left_layer)
        folium.GeoJson(
            geojson,
            style_function=make_choropleth_style(topic_df2, sel_topic2),
            tooltip=folium.GeoJsonTooltip(
                fields=["GRID_ID"], aliases=["Cell:"]),
        ).add_to(right_layer)

        left_layer.add_to(m)
        right_layer.add_to(m)
        SideBySideLayers(layer_left=left_layer,
                         layer_right=right_layer).add_to(m)

        # Topic labels inside map
        m.get_root().html.add_child(folium.Element(
            f'<div style="position:fixed;top:12px;left:60px;z-index:9999;'
            f'background:rgba(255,255,255,0.92);padding:4px 12px;'
            f'border-radius:20px;font-size:12px;font-weight:700;'
            f'border:1px solid #ccc">&#9664; {sel_topic}</div>'
            f'<div style="position:fixed;top:12px;right:12px;z-index:9999;'
            f'background:rgba(255,255,255,0.92);padding:4px 12px;'
            f'border-radius:20px;font-size:12px;font-weight:700;'
            f'border:1px solid #ccc">{sel_topic2} &#9654;</div>'
        ))

        # Render via components.html so JS swipe works fully
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False,
                                         mode="w", encoding="utf-8") as f:
            m.save(f.name)
            tmp_path = f.name
        with open(tmp_path, encoding="utf-8") as f:
            html_content = f.read()
        os.unlink(tmp_path)
        components.html(html_content, height=660, scrolling=False)
