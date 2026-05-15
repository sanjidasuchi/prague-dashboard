import os
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import plotly.express as px
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
    h3 { font-size: 1rem; margin-bottom: 0.3rem; }
    .filter-label { font-size: 11px; font-weight: 600; color: #555;
                    margin-bottom: 1px; margin-top: 4px; }
    div[data-testid="stSelectbox"] > div { min-height: 32px; }
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

SPEARMAN_IMGS = {
    "Safety":          "safety/safety_spearman_bar.png",
    "Proudness":       "proudness/proudness_spearman_bar.png",
    "Free Time":       "Free_time/freetime_spearman_bar.png",
    "Green Space":     "green_space/greenspace_spearman_bar.png",
    "Need to Change":  "need_to_change/needchange_spearman_bar.png",
    "Traffic Hazard":  "traffic/traffic_spearman_bar_final.png",
    "Waste Bin":       "waste_bin/wastebin_spearman_bar.png",
}

# ── Load data ──────────────────────────────────────────────────────────────────
@st.cache_data
def load_comments():
    path = os.path.join(BASE, "comment_analysis", "comments_sentiment_all.csv")
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()          # strip any BOM/whitespace from column names
    df = df.dropna(subset=["x", "y", "comment"])
    # English only: keep comments with mostly ASCII characters
    df = df[df["comment"].astype(str).str.len() > 8]
    df = df[df["comment"].astype(str).str.encode("ascii", errors="ignore").str.len()
            / df["comment"].astype(str).str.len() > 0.8]
    # Remove duplicate comment text
    df = df.drop_duplicates(subset=["comment"])
    return df

df = load_comments()

# ── TOP ROW: Left | Map | Right ────────────────────────────────────────────────
col_left, col_map, col_right = st.columns([1, 5, 1.4])

# ── Right: filters (read first so filtered df is available for map) ────────────
with col_right:
    st.markdown('<p style="font-size:13px;font-weight:700;margin-bottom:4px;">Filters</p>', unsafe_allow_html=True)
    emotions = ["All"] + sorted(df["emotion"].unique().tolist())
    ages     = ["All"] + ["0-19","20-29","30-39","40-49","50-59","60-69","70+"]
    genders  = ["All"] + sorted(df["gender"].dropna().unique().tolist())

    st.markdown('<p class="filter-label">Emotion</p>', unsafe_allow_html=True)
    sel_emotion = st.selectbox("Emotion", emotions, label_visibility="collapsed")
    st.markdown('<p class="filter-label">Age Group</p>', unsafe_allow_html=True)
    sel_age     = st.selectbox("Age Group", ages, label_visibility="collapsed")
    st.markdown('<p class="filter-label">Gender</p>', unsafe_allow_html=True)
    sel_gender  = st.selectbox("Gender", genders, label_visibility="collapsed")

# ── Filter data ────────────────────────────────────────────────────────────────
filtered = df.copy()
if sel_emotion != "All":
    filtered = filtered[filtered["emotion"] == sel_emotion]
if sel_age != "All":
    filtered = filtered[filtered["age"] == sel_age]
if sel_gender != "All":
    filtered = filtered[filtered["gender"] == sel_gender]

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

# ── Map ────────────────────────────────────────────────────────────────────────
with col_map:
    m = folium.Map(
        location=[50.075, 14.437],
        zoom_start=11,
        tiles="CartoDB positron",
    )
    cluster = MarkerCluster(max_cluster_radius=60).add_to(m)

    # Sample max 3000 points for fast rendering
    MAX_POINTS = 3000
    if len(filtered) > MAX_POINTS:
        map_data = filtered.sample(MAX_POINTS, random_state=42).reset_index(drop=True)
    else:
        map_data = filtered.reset_index(drop=True)

    for _, row in map_data.iterrows():
        color = EMOTION_COLORS.get(row["emotion"], "#888888")
        s_icon = ("😊" if row["sentiment_label"] == "positive"
                  else "😟" if row["sentiment_label"] == "negative" else "😐")
        popup_html = (
            f"<b style='color:{color}'>{row['emotion']}</b><br>"
            f"{str(row['comment'])[:200]}<br><br>"
            f"<small>Age: {row['age']} | {row['gender']} | {s_icon} {row['sentiment_label']}</small>"
        )
        folium.CircleMarker(
            location=[row["y"], row["x"]],
            radius=8,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            weight=1.5,
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=f"{row['emotion']} — click for comment",
        ).add_to(cluster)

    st_folium(m, width=None, height=430, returned_objects=[])

# ── Right: sentiment donut only (no comment boxes) ────────────────────────────
with col_right:
    st.markdown("---")
    st.markdown(f"**{len(filtered):,} comments**")
    st.markdown("### Sentiment")
    sent = filtered["sentiment_label"].value_counts()
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

# ── BOTTOM 1: Factor analysis tabs ────────────────────────────────────────────
st.divider()
st.markdown("### Factor Analysis — Spearman Correlations & Bivariate Maps")

FACTOR_DATA = {
    "Safety":         {"bar": "safety/safety_spearman_bar.png",               "map": "maps/safety_bivariate.png"},
    "Proudness":      {"bar": "proudness/proudness_spearman_bar.png",          "map": "maps/proudness_bivariate.jpg"},
    "Free Time":      {"bar": "Free_time/freetime_spearman_bar.png",           "map": "maps/freetime_bivariate.jpg"},
    "Green Space":    {"bar": "green_space/greenspace_spearman_bar.png",       "map": "maps/greenspace_bivariate.jpg"},
    "Need to Change": {"bar": "need_to_change/needchange_spearman_bar.png",    "map": "maps/needchange_bivariate.jpg"},
    "Traffic Hazard": {"bar": "traffic/traffic_spearman_bar_final.png",        "map": "maps/traffic_bivariate.jpg"},
    "Waste Bin":      {"bar": "waste_bin/wastebin_spearman_bar.png",           "map": "maps/wastebin_bivariate.jpg"},
}

tabs = st.tabs(list(FACTOR_DATA.keys()))
for tab, (factor, paths) in zip(tabs, FACTOR_DATA.items()):
    with tab:
        col_bar, col_map = st.columns(2)
        with col_bar:
            st.markdown(f"**Spearman Correlation — {factor}**")
            bar_path = os.path.join(BASE, paths["bar"])
            if os.path.exists(bar_path):
                st.image(bar_path, use_container_width=True)
        with col_map:
            st.markdown(f"**Bivariate Map — {factor}**")
            map_path = os.path.join(BASE, paths["map"])
            if os.path.exists(map_path):
                st.image(map_path, use_container_width=True)
            else:
                st.caption("Map not available")

# ── BOTTOM 2: Sentiment charts ─────────────────────────────────────────────────
st.divider()
st.markdown("### Comment Sentiment Analysis")

col_b1, col_b2, col_b3 = st.columns(3)

with col_b1:
    st.markdown("**Negativity by Emotion**")
    p = os.path.join(BASE, "comment_analysis", "cross_emotion_negativity.png")
    if os.path.exists(p):
        st.image(p, use_container_width=True)

with col_b2:
    st.markdown("**Sentiment by Age Group**")
    p = os.path.join(BASE, "comment_analysis", "sentiment_by_age.png")
    if os.path.exists(p):
        st.image(p, use_container_width=True)

with col_b3:
    st.markdown("**Word Clouds per Emotion**")
    p = os.path.join(BASE, "comment_analysis", "wordclouds_all_emotions.png")
    if os.path.exists(p):
        st.image(p, use_container_width=True)
