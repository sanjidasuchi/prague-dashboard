import os, json
import pandas as pd
import folium
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

BASE = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(
    page_title="Prague Mapped by People and Satellites",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    h1 { text-align: center; font-size: 1.8rem; color: #1a1a2e; margin-bottom: 0.5rem; }
    .filter-label { font-size: 11px; font-weight: 600; color: #555;
                    margin-bottom: 1px; margin-top: 4px; }
    div[data-testid="stSelectbox"] > div > div { font-size: 12px; padding: 2px 8px; }
</style>
""", unsafe_allow_html=True)

st.markdown("# Prague Mapped by People and Satellites")

# ── Constants ──────────────────────────────────────────────────────────────────
EMOTION_COLORS = {
    "Safety":            "#1B3A5C",
    "Proudness":         "#E87D1E",
    "Free Time":         "#1A878A",
    "Traffic Hazard":    "#C0392B",
    "Green Space":       "#27AE60",
    "Need for Change":   "#8E44AD",
    "Waste/Cleanliness": "#7F8C8D",
}

BIVAR_COLORS = {
    "1-1": "#e8e8e8", "2-1": "#dfb0d6", "3-1": "#be64ac",
    "1-2": "#ace4e4", "2-2": "#a5b4c2", "3-2": "#8c62aa",
    "1-3": "#5ac8c8", "2-3": "#5698b9", "3-3": "#3b4994",
}

BIVAR_LABELS = {
    "1-1": "Low / Low",   "2-1": "Mid activity / Low env",  "3-1": "High activity / Low env ⚠",
    "1-2": "Low / Mid",   "2-2": "Mid / Mid",               "3-2": "High activity / Mid env",
    "1-3": "Low / High",  "2-3": "Mid activity / High env", "3-3": "High / High ✓",
}

TOPIC_COLORS = {
    "Safety": "#1B3A5C", "Proudness": "#E87D1E", "Free Time": "#1A878A",
    "Green Space": "#27AE60", "Need to Change": "#8E44AD",
    "Traffic Hazard": "#C0392B", "Waste Bin": "#7F8C8D",
}

SPEARMAN_IMGS = {
    "Safety":          "safety/safety_spearman_bar.png",
    "Proudness":       "proudness/proudness_spearman_bar.png",
    "Free Time":       "Free_time/freetime_spearman_bar.png",
    "Green Space":     "green_space/greenspace_spearman_bar.png",
    "Need to Change":  "need_to_change/needchange_spearman_bar.png",
    "Traffic Hazard":  "traffic/traffic_spearman_bar_final.png",
    "Waste Bin":       "waste_bin/wastebin_spearman_bar.png",
}

FACTOR_DATA = {
    "Safety":         {"bar": "safety/safety_spearman_bar.png",            "map": "maps/safety_bivariate.png"},
    "Proudness":      {"bar": "proudness/proudness_spearman_bar.png",       "map": "maps/proudness_bivariate.jpg"},
    "Free Time":      {"bar": "Free_time/freetime_spearman_bar.png",        "map": "maps/freetime_bivariate.jpg"},
    "Green Space":    {"bar": "green_space/greenspace_spearman_bar.png",    "map": "maps/greenspace_bivariate.jpg"},
    "Need to Change": {"bar": "need_to_change/needchange_spearman_bar.png", "map": "maps/needchange_bivariate.jpg"},
    "Traffic Hazard": {"bar": "traffic/traffic_spearman_bar_final.png",     "map": "maps/traffic_bivariate.jpg"},
    "Waste Bin":      {"bar": "waste_bin/wastebin_spearman_bar.png",        "map": "maps/wastebin_bivariate.jpg"},
}

# ── Load data ──────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    comments = pd.read_csv(
        os.path.join(BASE, "data", "comments_with_grid.csv"), encoding="utf-8-sig"
    )
    comments.columns = comments.columns.str.strip()
    hex_topics = pd.read_csv(
        os.path.join(BASE, "data", "hex_all_topics.csv"), encoding="utf-8-sig"
    )
    hex_topics.columns = hex_topics.columns.str.strip()
    with open(os.path.join(BASE, "hex_grid.geojson"), encoding="utf-8") as f:
        geojson = json.load(f)
    # Normalise GRID_ID field name in geojson
    for feat in geojson["features"]:
        props = feat["properties"]
        for k in list(props.keys()):
            if "GRID_ID" in k and k != "GRID_ID":
                props["GRID_ID"] = props.pop(k)
                break
    return comments, hex_topics, geojson

comments, hex_topics, geojson = load_data()

# ── Layout ─────────────────────────────────────────────────────────────────────
col_left, col_map, col_right = st.columns([1, 5, 1.4])

# ── Right: topic selector + filters ───────────────────────────────────────────
with col_right:
    st.markdown('<p style="font-size:13px;font-weight:700;margin-bottom:4px;">Topic</p>', unsafe_allow_html=True)
    topics     = list(TOPIC_COLORS.keys())
    sel_topic  = st.radio("Topic", topics, label_visibility="collapsed")

    st.markdown("---")
    st.markdown('<p style="font-size:13px;font-weight:700;margin-bottom:4px;">Filters</p>', unsafe_allow_html=True)
    ages    = ["All"] + ["0-19","20-29","30-39","40-49","50-59","60-69","70+"]
    genders = ["All"] + sorted(comments["gender"].dropna().unique().tolist())
    st.markdown('<p class="filter-label">Age Group</p>', unsafe_allow_html=True)
    sel_age    = st.selectbox("Age",    ages,    label_visibility="collapsed")
    st.markdown('<p class="filter-label">Gender</p>', unsafe_allow_html=True)
    sel_gender = st.selectbox("Gender", genders, label_visibility="collapsed")

# ── Filter comments ────────────────────────────────────────────────────────────
filt_comments = comments.copy()
if sel_age    != "All": filt_comments = filt_comments[filt_comments["age"]    == sel_age]
if sel_gender != "All": filt_comments = filt_comments[filt_comments["gender"] == sel_gender]

# Comments grouped by GRID_ID for popup use
comments_by_hex = (
    filt_comments.dropna(subset=["GRID_ID"])
    .groupby("GRID_ID")
    .apply(lambda g: g.head(3)[["comment","sentiment_label"]].to_dict("records"))
    .to_dict()
)

# ── Left panel ─────────────────────────────────────────────────────────────────
with col_left:
    st.markdown("### Welcome")
    st.caption(
        "Participatory emotional mapping combined with Copernicus satellite "
        "indicators to identify priority zones for urban improvement in Prague."
    )
    st.markdown("---")
    st.markdown("**Emotion Legend**")
    legend_html = "".join([
        f'<div style="display:flex;align-items:center;gap:7px;margin:3px 0;font-size:12px;">'
        f'<span style="width:10px;height:10px;border-radius:50%;background:{color};'
        f'flex-shrink:0;display:inline-block;"></span>{emotion}</div>'
        for emotion, color in EMOTION_COLORS.items()
    ])
    st.markdown(legend_html, unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Bivariate Legend**")
    bivar_legend = """
    <table style="border-collapse:collapse;font-size:10px;width:100%">
    <tr><td></td><td style="text-align:center;font-weight:600" colspan="3">Environmental →</td></tr>
    <tr><td style="font-weight:600;writing-mode:vertical-lr;transform:rotate(180deg);font-size:10px">Activity ↑</td>
    <td style="background:#be64ac;width:28px;height:24px;border:1px solid #fff"></td>
    <td style="background:#8c62aa;width:28px;height:24px;border:1px solid #fff"></td>
    <td style="background:#3b4994;width:28px;height:24px;border:1px solid #fff"></td></tr>
    <tr><td></td>
    <td style="background:#dfb0d6;width:28px;height:24px;border:1px solid #fff"></td>
    <td style="background:#a5b4c2;width:28px;height:24px;border:1px solid #fff"></td>
    <td style="background:#5698b9;width:28px;height:24px;border:1px solid #fff"></td></tr>
    <tr><td></td>
    <td style="background:#e8e8e8;width:28px;height:24px;border:1px solid #fff"></td>
    <td style="background:#ace4e4;width:28px;height:24px;border:1px solid #fff"></td>
    <td style="background:#5ac8c8;width:28px;height:24px;border:1px solid #fff"></td></tr>
    </table>"""
    st.markdown(bivar_legend, unsafe_allow_html=True)
    st.caption("Pink = High activity\nBlue = High env. indicator")

# ── Map ────────────────────────────────────────────────────────────────────────
with col_map:
    topic_data = hex_topics[hex_topics["topic"] == sel_topic].set_index("GRID_ID")

    m = folium.Map(location=[50.075, 14.437], zoom_start=11, tiles="CartoDB positron")

    def style_fn(feature):
        gid   = feature["properties"].get("GRID_ID", "")
        color = topic_data.loc[gid, "color"] if gid in topic_data.index else "#dddddd"
        return {"fillColor": color, "color": "#555", "weight": 0.5,
                "fillOpacity": 0.75}

    def highlight_fn(feature):
        return {"weight": 2, "color": "#333", "fillOpacity": 0.9}

    def make_popup(feature):
        gid = feature["properties"].get("GRID_ID", "")
        if gid not in topic_data.index:
            return folium.Popup(f"<b>{gid}</b><br>No data", max_width=260)
        row      = topic_data.loc[gid]
        bv_label = BIVAR_LABELS.get(str(row.get("bivar_class","")),"—")
        x_label  = row.get("x_label","Value")
        y_label  = row.get("y_label","Indicator")
        x_val    = row.get("x_val","—")
        y_val    = row.get("y_val","—")
        hex_comments = comments_by_hex.get(gid, [])
        c_html = "".join([
            f'<div style="font-size:11px;border-left:3px solid '
            f'{"#27AE60" if c["sentiment_label"]=="positive" else "#C0392B" if c["sentiment_label"]=="negative" else "#888"}'
            f';padding:2px 6px;margin:3px 0;">{str(c["comment"])[:100]}</div>'
            for c in hex_comments
        ]) or "<i style='font-size:11px;color:#888'>No comments</i>"
        html = f"""
        <div style="font-family:sans-serif;min-width:220px">
          <b style="font-size:13px">{gid} — {sel_topic}</b><hr style="margin:4px 0">
          <table style="font-size:12px;width:100%">
            <tr><td><b>{x_label}</b></td><td>{x_val}</td></tr>
            <tr><td><b>{y_label}</b></td><td>{y_val}</td></tr>
            <tr><td><b>Bivariate</b></td><td>{bv_label}</td></tr>
          </table>
          <hr style="margin:4px 0">
          <b style="font-size:11px">Comments:</b><br>{c_html}
        </div>"""
        return folium.Popup(html, max_width=300)

    folium.GeoJson(
        geojson,
        style_function=style_fn,
        highlight_function=highlight_fn,
        popup=folium.GeoJsonPopup(fields=["GRID_ID"], labels=False,
                                   localize=True, max_width=300),
        tooltip=folium.GeoJsonTooltip(fields=["GRID_ID"], aliases=["Cell:"],
                                       style="font-size:12px"),
    ).add_to(m)

    # Re-add popups manually with comment data
    for feat in geojson["features"]:
        gid = feat["properties"].get("GRID_ID","")
        if gid not in topic_data.index:
            continue
        row      = topic_data.loc[gid]
        bv_label = BIVAR_LABELS.get(str(row.get("bivar_class","")),"—")
        x_val    = row.get("x_val","—")
        y_val    = row.get("y_val","—")
        x_label  = row.get("x_label","Value")
        y_label  = row.get("y_label","Indicator")
        hex_comments = comments_by_hex.get(gid, [])
        c_html = "".join([
            f'<div style="font-size:11px;border-left:3px solid '
            f'{"#27AE60" if c["sentiment_label"]=="positive" else "#C0392B" if c["sentiment_label"]=="negative" else "#888"}'
            f';padding:2px 6px;margin:3px 0;">{str(c["comment"])[:100]}</div>'
            for c in hex_comments
        ]) or "<i style='font-size:11px;color:#888'>No comments for this filter</i>"
        html = f"""<div style="font-family:sans-serif;min-width:220px">
          <b style="font-size:13px">{gid} — {sel_topic}</b><hr style="margin:4px 0">
          <table style="font-size:12px;width:100%">
            <tr><td><b>{x_label}</b></td><td>{x_val}</td></tr>
            <tr><td><b>{y_label}</b></td><td>{y_val}</td></tr>
            <tr><td><b>Bivariate</b></td><td>{bv_label}</td></tr>
          </table>
          <hr style="margin:4px 0">
          <b style="font-size:11px">Comments:</b><br>{c_html}
        </div>"""
        # centroid for marker (invisible, just for popup)
        centroid = shape_centroid(feat["geometry"])
        if centroid:
            folium.Marker(
                location=[centroid[1], centroid[0]],
                popup=folium.Popup(html, max_width=300),
                icon=folium.DivIcon(html="", icon_size=(0,0))
            ).add_to(m)

    st_folium(m, width=None, height=450, returned_objects=[])

def shape_centroid(geometry):
    try:
        coords = geometry["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return [sum(lons)/len(lons), sum(lats)/len(lats)]
    except:
        return None

# ── Right: sentiment donut ─────────────────────────────────────────────────────
with col_right:
    st.markdown("---")
    topic_emotion_map = {
        "Safety": "Safety", "Proudness": "Proudness", "Free Time": "Free Time",
        "Green Space": "Green Space", "Need to Change": "Need for Change",
        "Traffic Hazard": "Traffic Hazard", "Waste Bin": "Waste/Cleanliness",
    }
    emotion_key = topic_emotion_map.get(sel_topic, sel_topic)
    sent_df = filt_comments[filt_comments["emotion"] == emotion_key]
    st.markdown(f"**{len(sent_df):,} comments**")
    st.markdown("**Sentiment**")
    if len(sent_df) > 0:
        sent = sent_df["sentiment_label"].value_counts()
        label_order = ["positive", "neutral", "negative"]
        color_map   = {"positive": "#27AE60", "neutral": "#95A5A6", "negative": "#C0392B"}
        labels = [l for l in label_order if l in sent.index]
        values = [sent[l] for l in labels]
        colors = [color_map[l] for l in labels]
        fig = go.Figure(go.Pie(
            labels=labels, values=values, hole=0.55,
            marker_colors=colors, textinfo="percent", textfont_size=11,
        ))
        fig.update_layout(margin=dict(t=0,b=0,l=0,r=0), height=190,
                          legend=dict(font=dict(size=10)))
        st.plotly_chart(fig, use_container_width=True)

# ── Factor analysis tabs ───────────────────────────────────────────────────────
st.divider()
st.markdown("### Factor Analysis — Spearman Correlations & Bivariate Maps")

tabs = st.tabs(list(FACTOR_DATA.keys()))
for tab, (factor, paths) in zip(tabs, FACTOR_DATA.items()):
    with tab:
        col_bar, col_map2 = st.columns(2)
        with col_bar:
            st.markdown(f"**Spearman Correlation — {factor}**")
            bar_path = os.path.join(BASE, paths["bar"])
            if os.path.exists(bar_path):
                st.image(bar_path, use_container_width=True)
        with col_map2:
            st.markdown(f"**Bivariate Map — {factor}**")
            map_path = os.path.join(BASE, paths["map"])
            if os.path.exists(map_path):
                st.image(map_path, use_container_width=True)

# ── Comment sentiment analysis ─────────────────────────────────────────────────
st.divider()
st.markdown("### Comment Sentiment Analysis")
col_b1, col_b2, col_b3 = st.columns(3)

with col_b1:
    st.markdown("**Negativity by Emotion**")
    p = os.path.join(BASE, "comment_analysis", "cross_emotion_negativity.png")
    if os.path.exists(p): st.image(p, use_container_width=True)

with col_b2:
    st.markdown("**Sentiment by Age Group**")
    p = os.path.join(BASE, "comment_analysis", "sentiment_by_age.png")
    if os.path.exists(p): st.image(p, use_container_width=True)

with col_b3:
    st.markdown("**Word Clouds per Emotion**")
    p = os.path.join(BASE, "comment_analysis", "wordclouds_all_emotions.png")
    if os.path.exists(p): st.image(p, use_container_width=True)
