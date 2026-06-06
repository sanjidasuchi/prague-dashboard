import os, json
import pandas as pd
import folium
from folium.plugins import MarkerCluster, SideBySideLayers
import streamlit as st
from streamlit_folium import st_folium

BASE = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(page_title="Prague Mapped by People and Satellites",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .block-container { padding-top:0.8rem; padding-bottom:0rem; }
    h1 { text-align:center; font-size:1.6rem; color:#1a1a2e; margin-bottom:0.4rem; }
    .filter-label { font-size:11px; font-weight:600; color:#555; margin:3px 0 1px 0; }
    div[data-testid="stSelectbox"] > div > div { font-size:12px; padding:2px 8px; }
    div[data-testid="stRadio"] label { font-size:12px; }
</style>
""", unsafe_allow_html=True)

st.markdown("# Prague Mapped by People and Satellites")

# ── Constants ──────────────────────────────────────────────────────────────────
BIVAR_COLORS = {
    "1-1":"#e8e8e8","2-1":"#dfb0d6","3-1":"#be64ac",
    "1-2":"#ace4e4","2-2":"#a5b4c2","3-2":"#8c62aa",
    "1-3":"#5ac8c8","2-3":"#5698b9","3-3":"#3b4994",
}
BIVAR_LABELS = {
    "1-1":"Low activity / Low env","2-1":"Mid activity / Low env",
    "3-1":"High activity / Low env ⚠","1-2":"Low activity / Mid env",
    "2-2":"Mid / Mid","3-2":"High activity / Mid env",
    "1-3":"Low activity / High env","2-3":"Mid activity / High env",
    "3-3":"High activity / High env ✓",
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
        gid = feat["properties"].get("GRID_ID","")
        color = tdf.loc[gid,"color"] if gid in tdf.index else "#dddddd"
        return {"fillColor":color,"color":"#666","weight":0.5,"fillOpacity":0.75}
    return fn

def highlight_fn(feat):
    return {"weight":2,"color":"#222","fillOpacity":0.9}

def popup_html(gid, tdf, cbh):
    if gid not in tdf.index:
        return f"<b>{gid}</b><br>No data"
    row    = tdf.loc[gid]
    bv     = BIVAR_LABELS.get(str(row.get("bivar_class","")),"—")
    x_lbl  = row.get("x_label","Respondents")
    y_lbl  = row.get("y_label","Indicator")
    x_val  = row.get("x_val","—")
    y_val  = row.get("y_val","—")
    cx     = cbh.get(gid,[])
    c_html = "".join([
        f'<div style="font-size:11px;border-left:3px solid '
        f'{"#27AE60" if c["sentiment_label"]=="positive" else "#C0392B" if c["sentiment_label"]=="negative" else "#888"}'
        f';padding:2px 5px;margin:2px 0">{str(c["comment"])[:100]}</div>'
        for c in cx
    ]) or "<i style='font-size:10px;color:#888'>No comments</i>"
    return (f'<div style="font-family:sans-serif;min-width:210px">'
            f'<b style="font-size:13px">{gid}</b><hr style="margin:3px 0">'
            f'<table style="font-size:11px;width:100%">'
            f'<tr><td><b>Respondents</b></td><td>{x_val}</td></tr>'
            f'<tr><td><b>{x_lbl}</b></td><td>{x_val}</td></tr>'
            f'<tr><td><b>{y_lbl}</b></td><td>{y_val}</td></tr>'
            f'<tr><td><b>Bivariate class</b></td><td>{bv}</td></tr>'
            f'</table><hr style="margin:3px 0">'
            f'<b style="font-size:10px">Comments:</b>{c_html}</div>')

# Emotion legend — bottom-left inside map
EMOTION_LEG = """<div style="position:fixed;bottom:18px;left:12px;z-index:9999;
     background:rgba(255,255,255,0.93);padding:7px 10px;border-radius:8px;
     border:1px solid #ccc;font-size:11px;box-shadow:2px 2px 6px rgba(0,0,0,0.15)">
  <b>Emotions</b><br>""" + "".join([
    f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
    f'background:{c};margin-right:5px;vertical-align:middle"></span>{e}<br>'
    for e,c in EMOTION_COLORS.items()
]) + "</div>"

# Sentiment legend — bottom-right inside map
SENTIMENT_LEG = """<div style="position:fixed;bottom:18px;right:12px;z-index:9999;
     background:rgba(255,255,255,0.93);padding:7px 10px;border-radius:8px;
     border:1px solid #ccc;font-size:11px;box-shadow:2px 2px 6px rgba(0,0,0,0.15)">
  <b>Sentiment</b><br>
  <span style="color:#27AE60">● Positive</span><br>
  <span style="color:#888888">● Neutral</span><br>
  <span style="color:#C0392B">● Negative</span>
</div>"""

# ── COLUMNS ────────────────────────────────────────────────────────────────────
col_left, col_map, col_right = st.columns([1.2, 4.8, 1.6])

# ── RIGHT PANEL ────────────────────────────────────────────────────────────────
with col_right:
    st.markdown("""
    <div style="font-size:13px;font-weight:700;margin-bottom:4px">Bivariate Legend</div>
    <table style="border-collapse:collapse;font-size:11px">
    <tr>
      <td style="writing-mode:vertical-rl;transform:rotate(180deg);font-weight:600;
          padding-right:4px;font-size:11px">Activity ↑</td>
      <td>
        <table style="border-collapse:collapse">
          <tr>
            <td style="font-size:10px;padding:1px 3px"></td>
            <td style="font-size:10px;padding:1px 3px;text-align:center">Low</td>
            <td style="font-size:10px;padding:1px 3px;text-align:center">Mid</td>
            <td style="font-size:10px;padding:1px 3px;text-align:center">High</td>
          </tr><tr>
            <td style="font-size:10px;padding:1px 3px">High</td>
            <td style="background:#be64ac;width:28px;height:24px;border:1px solid #fff"></td>
            <td style="background:#8c62aa;width:28px;height:24px;border:1px solid #fff"></td>
            <td style="background:#3b4994;width:28px;height:24px;border:1px solid #fff"></td>
          </tr><tr>
            <td style="font-size:10px;padding:1px 3px">Mid</td>
            <td style="background:#dfb0d6;width:28px;height:24px;border:1px solid #fff"></td>
            <td style="background:#a5b4c2;width:28px;height:24px;border:1px solid #fff"></td>
            <td style="background:#5698b9;width:28px;height:24px;border:1px solid #fff"></td>
          </tr><tr>
            <td style="font-size:10px;padding:1px 3px">Low</td>
            <td style="background:#e8e8e8;width:28px;height:24px;border:1px solid #fff"></td>
            <td style="background:#ace4e4;width:28px;height:24px;border:1px solid #fff"></td>
            <td style="background:#5ac8c8;width:28px;height:24px;border:1px solid #fff"></td>
          </tr><tr>
            <td></td>
            <td colspan="3" style="font-size:10px;font-weight:600;
                text-align:center;padding-top:3px">Env. indicator →</td>
          </tr>
        </table>
      </td>
    </tr></table>
    <div style="font-size:10px;color:#555;margin-top:4px;line-height:1.6">
      <span style="color:#be64ac">■</span> High demand, Low env<br>
      <span style="color:#3b4994">■</span> Low demand, High env<br>
      <span style="color:#a5b4c2">■</span> Mid both
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<p style="font-size:13px;font-weight:700;margin-bottom:2px">Topic</p>',
                unsafe_allow_html=True)
    topics    = list(TOPIC_EMOTION.keys())
    sel_topic = st.radio("Topic", topics, label_visibility="collapsed")

    st.markdown('<p style="font-size:13px;font-weight:700;margin-bottom:2px">Compare with</p>',
                unsafe_allow_html=True)
    topics2    = [t for t in topics if t != sel_topic]
    sel_topic2 = st.radio("Topic2", topics2, label_visibility="collapsed", key="t2")

# ── FILTER comments ────────────────────────────────────────────────────────────
topic_df  = hex_topics[hex_topics["topic"] == sel_topic].set_index("GRID_ID")
topic_df2 = hex_topics[hex_topics["topic"] == sel_topic2].set_index("GRID_ID")

# ── LEFT PANEL ─────────────────────────────────────────────────────────────────
with col_left:
    st.markdown("""
    <div style="font-size:13px;font-weight:700;margin-bottom:6px">Welcome</div>
    <div style="font-size:12px;color:#333;line-height:1.6">
    This dashboard combines Prague residents' emotional mapping responses with
    Copernicus satellite data — NDVI, imperviousness, night lights, land surface
    temperature and NO₂ — to reveal where urban quality and lived experience
    align or conflict.
    <br><br>
    Select a <b>topic</b> on the right, explore the <b>bivariate hex map</b>,
    switch to <b>comments</b> to read what residents say, or use
    <b>compare</b> to see two topics side by side.
    </div>
    """, unsafe_allow_html=True)

# ── MAP SECTION ────────────────────────────────────────────────────────────────
with col_map:
    mode = st.radio("mode",
                    ["🗺 Bivariate", "💬 Comments", "⟺ Compare"],
                    horizontal=True, label_visibility="collapsed")

    if mode == "💬 Comments":
        fc1, fc2 = st.columns(2)
        with fc1:
            st.markdown('<p class="filter-label">Age Group</p>', unsafe_allow_html=True)
            ages   = ["All"] + ["0-19","20-29","30-39","40-49","50-59","60-69","70+"]
            sel_age = st.selectbox("Age", ages, label_visibility="collapsed", key="age_c")
        with fc2:
            st.markdown('<p class="filter-label">Gender</p>', unsafe_allow_html=True)
            genders    = ["All"] + sorted(comments["gender"].dropna().unique().tolist())
            sel_gender = st.selectbox("Gender", genders, label_visibility="collapsed", key="gen_c")
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

    # ── Bivariate mode ─────────────────────────────────────────────────────────
    if mode == "🗺 Bivariate":
        m = folium.Map(location=[50.075,14.437], zoom_start=11,
                       tiles="CartoDB positron")
        folium.GeoJson(
            geojson,
            style_function=make_style(topic_df),
            highlight_function=highlight_fn,
            tooltip=folium.GeoJsonTooltip(fields=["GRID_ID"], aliases=["Cell:"]),
        ).add_to(m)
        for feat in geojson["features"]:
            gid = feat["properties"].get("GRID_ID","")
            c   = shape_centroid(feat["geometry"])
            if c:
                folium.Marker(
                    location=c,
                    popup=folium.Popup(
                        popup_html(gid, topic_df, comments_by_hex), max_width=300),
                    icon=folium.DivIcon(html="", icon_size=(0,0))
                ).add_to(m)
        m.get_root().html.add_child(folium.Element(EMOTION_LEG))
        st_folium(m, width=None, height=470, returned_objects=[])

    # ── Comments mode ──────────────────────────────────────────────────────────
    elif mode == "💬 Comments":
        emotion_key = TOPIC_EMOTION.get(sel_topic, sel_topic)
        topic_filt  = filt[filt["emotion"] == emotion_key]
        m = folium.Map(location=[50.075,14.437], zoom_start=11,
                       tiles="CartoDB positron")
        cluster = MarkerCluster(max_cluster_radius=50).add_to(m)
        sample  = topic_filt.sample(min(len(topic_filt), 2000), random_state=42)
        for _, row in sample.iterrows():
            s_color = ("#27AE60" if row["sentiment_label"]=="positive"
                       else "#C0392B" if row["sentiment_label"]=="negative" else "#888")
            folium.CircleMarker(
                location=[row["y"], row["x"]], radius=7,
                color=s_color, fill=True, fill_color=s_color,
                fill_opacity=0.8, weight=1,
                popup=folium.Popup(
                    f'<b>{row["emotion"]}</b><br>{str(row["comment"])[:180]}<br>'
                    f'<small>Age: {row["age"]} | {row["gender"]} | '
                    f'<span style="color:{s_color}">{row["sentiment_label"]}</span></small>',
                    max_width=270),
                tooltip=row["sentiment_label"],
            ).add_to(cluster)
        # Filter badge inside map
        badge = (f'<div style="position:fixed;top:10px;left:50%;'
                 f'transform:translateX(-50%);z-index:9999;'
                 f'background:rgba(255,255,255,0.93);padding:4px 12px;'
                 f'border-radius:20px;font-size:11px;border:1px solid #ccc;">'
                 f'Age: <b>{sel_age}</b> &nbsp;|&nbsp; Gender: <b>{sel_gender}</b>'
                 f'</div>')
        m.get_root().html.add_child(folium.Element(EMOTION_LEG))
        m.get_root().html.add_child(folium.Element(SENTIMENT_LEG))
        m.get_root().html.add_child(folium.Element(badge))
        st_folium(m, width=None, height=450, returned_objects=[])

    # ── Compare mode — swipe on ONE map ────────────────────────────────────────
    elif mode == "⟺ Compare":
        m = folium.Map(location=[50.075,14.437], zoom_start=11,
                       tiles="CartoDB positron")

        left_layer  = folium.FeatureGroup(name=sel_topic,  overlay=True)
        right_layer = folium.FeatureGroup(name=sel_topic2, overlay=True)

        folium.GeoJson(
            geojson,
            style_function=make_style(topic_df),
            highlight_function=highlight_fn,
            tooltip=folium.GeoJsonTooltip(fields=["GRID_ID"], aliases=["Cell:"]),
        ).add_to(left_layer)

        folium.GeoJson(
            geojson,
            style_function=make_style(topic_df2),
            highlight_function=highlight_fn,
            tooltip=folium.GeoJsonTooltip(fields=["GRID_ID"], aliases=["Cell:"]),
        ).add_to(right_layer)

        left_layer.add_to(m)
        right_layer.add_to(m)
        SideBySideLayers(
            layer_left=left_layer,
            layer_right=right_layer
        ).add_to(m)

        # Labels inside map
        labels = (
            f'<div style="position:fixed;top:10px;left:60px;z-index:9999;'
            f'background:rgba(255,255,255,0.9);padding:4px 10px;border-radius:6px;'
            f'font-size:12px;font-weight:700;border:1px solid #ccc">'
            f'◀ {sel_topic}</div>'
            f'<div style="position:fixed;top:10px;right:20px;z-index:9999;'
            f'background:rgba(255,255,255,0.9);padding:4px 10px;border-radius:6px;'
            f'font-size:12px;font-weight:700;border:1px solid #ccc">'
            f'{sel_topic2} ▶</div>'
        )
        m.get_root().html.add_child(folium.Element(labels))
        st_folium(m, width=None, height=470, returned_objects=[])
