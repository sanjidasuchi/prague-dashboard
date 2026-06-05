import os, json
import pandas as pd
import folium
from folium.plugins import MarkerCluster, SideBySideLayers
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
    .block-container { padding-top: 0.8rem; padding-bottom: 0rem; }
    h1 { text-align:center; font-size:1.6rem; color:#1a1a2e; margin-bottom:0.3rem; }
    .filter-label { font-size:11px; font-weight:600; color:#555;
                    margin-bottom:1px; margin-top:4px; }
    div[data-testid="stSelectbox"] > div > div { font-size:12px; padding:2px 8px; }
    div[data-testid="stRadio"] label { font-size:12px; }
    .stRadio > div { gap: 4px; }
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
    "3-1":"High activity / Low env ⚠","1-2":"Low / Mid",
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
    comments = pd.read_csv(
        os.path.join(BASE,"data","comments_with_grid.csv"), encoding="utf-8-sig")
    comments.columns = comments.columns.str.strip()
    hex_topics = pd.read_csv(
        os.path.join(BASE,"data","hex_all_topics.csv"), encoding="utf-8-sig")
    hex_topics.columns = hex_topics.columns.str.strip()
    with open(os.path.join(BASE,"hex_grid.geojson"), encoding="utf-8") as f:
        geojson = json.load(f)
    for feat in geojson["features"]:
        props = feat["properties"]
        for k in list(props.keys()):
            if "GRID_ID" in k and k != "GRID_ID":
                props["GRID_ID"] = props.pop(k)
                break
    return comments, hex_topics, geojson

comments, hex_topics, geojson = load_data()

def shape_centroid(geometry):
    try:
        coords = geometry["coordinates"][0]
        return [sum(c[1] for c in coords)/len(coords),
                sum(c[0] for c in coords)/len(coords)]
    except:
        return None

# ── Layout: left | map | right ─────────────────────────────────────────────────
col_left, col_map, col_right = st.columns([1, 5, 1.4])

# ── Right panel ────────────────────────────────────────────────────────────────
with col_right:
    st.markdown('<p style="font-size:13px;font-weight:700;margin-bottom:2px">Topic</p>',
                unsafe_allow_html=True)
    topics    = list(TOPIC_EMOTION.keys())
    sel_topic = st.radio("Topic", topics, label_visibility="collapsed")

    st.markdown("---")
    st.markdown('<p style="font-size:13px;font-weight:700;margin-bottom:2px">Compare Topic</p>',
                unsafe_allow_html=True)
    topics2     = [t for t in topics if t != sel_topic]
    sel_topic2  = st.radio("Topic2", topics2, label_visibility="collapsed",
                            key="topic2")

    st.markdown("---")
    ages    = ["All"] + ["0-19","20-29","30-39","40-49","50-59","60-69","70+"]
    genders = ["All"] + sorted(comments["gender"].dropna().unique().tolist())
    st.markdown('<p class="filter-label">Age Group</p>', unsafe_allow_html=True)
    sel_age    = st.selectbox("Age",    ages,    label_visibility="collapsed")
    st.markdown('<p class="filter-label">Gender</p>', unsafe_allow_html=True)
    sel_gender = st.selectbox("Gender", genders, label_visibility="collapsed")

# ── Filter comments ────────────────────────────────────────────────────────────
filt = comments.copy()
if sel_age    != "All": filt = filt[filt["age"]    == sel_age]
if sel_gender != "All": filt = filt[filt["gender"] == sel_gender]

comments_by_hex = (
    filt.dropna(subset=["GRID_ID"])
    .groupby("GRID_ID")
    .apply(lambda g: g.head(3)[["comment","sentiment_label"]].to_dict("records"))
    .to_dict()
)

# ── Left panel ─────────────────────────────────────────────────────────────────
with col_left:
    # Bivariate legend FIRST
    st.markdown("**Bivariate Legend**")
    st.markdown("""
    <table style="border-collapse:collapse;font-size:10px;margin-bottom:4px">
    <tr>
      <td style="font-size:9px;writing-mode:vertical-rl;transform:rotate(180deg);
          padding-right:3px;font-weight:600">Activity ↑</td>
      <td>
        <table style="border-collapse:collapse">
        <tr>
          <td style="background:#be64ac;width:24px;height:20px;border:1px solid #fff"></td>
          <td style="background:#8c62aa;width:24px;height:20px;border:1px solid #fff"></td>
          <td style="background:#3b4994;width:24px;height:20px;border:1px solid #fff"></td>
        </tr><tr>
          <td style="background:#dfb0d6;width:24px;height:20px;border:1px solid #fff"></td>
          <td style="background:#a5b4c2;width:24px;height:20px;border:1px solid #fff"></td>
          <td style="background:#5698b9;width:24px;height:20px;border:1px solid #fff"></td>
        </tr><tr>
          <td style="background:#e8e8e8;width:24px;height:20px;border:1px solid #fff"></td>
          <td style="background:#ace4e4;width:24px;height:20px;border:1px solid #fff"></td>
          <td style="background:#5ac8c8;width:24px;height:20px;border:1px solid #fff"></td>
        </tr>
        <tr>
          <td colspan="3" style="text-align:center;font-size:9px;
              font-weight:600;padding-top:2px">Env. indicator →</td>
        </tr>
        </table>
      </td>
    </tr>
    </table>
    <span style="font-size:9px;color:#555">Pink=High activity · Blue=High env</span>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Welcome**")
    st.caption("Emotional mapping + Copernicus satellite data for Prague urban analysis.")

    st.markdown("---")
    st.markdown("**Emotion Legend**")
    st.markdown("".join([
        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;font-size:11px;">'
        f'<span style="width:9px;height:9px;border-radius:50%;background:{c};'
        f'flex-shrink:0;display:inline-block"></span>{e}</div>'
        for e, c in EMOTION_COLORS.items()
    ]), unsafe_allow_html=True)

# ── Map section ────────────────────────────────────────────────────────────────
with col_map:
    mode = st.radio(
        "Map mode",
        ["🗺 Bivariate", "💬 Comments", "⟺ Compare"],
        horizontal=True,
        label_visibility="collapsed",
    )

    topic_df  = hex_topics[hex_topics["topic"] == sel_topic].set_index("GRID_ID")
    topic_df2 = hex_topics[hex_topics["topic"] == sel_topic2].set_index("GRID_ID")

    def make_style(tdf):
        def fn(feat):
            gid   = feat["properties"].get("GRID_ID","")
            color = tdf.loc[gid,"color"] if gid in tdf.index else "#dddddd"
            return {"fillColor":color,"color":"#666","weight":0.5,"fillOpacity":0.75}
        return fn

    def highlight_fn(feat):
        return {"weight":2,"color":"#222","fillOpacity":0.9}

    def make_popup_html(gid, tdf):
        if gid not in tdf.index:
            return f"<b>{gid}</b><br>No data"
        row      = tdf.loc[gid]
        bv       = BIVAR_LABELS.get(str(row.get("bivar_class","")),"—")
        x_label  = row.get("x_label","Value")
        y_label  = row.get("y_label","Indicator")
        x_val    = row.get("x_val","—")
        y_val    = row.get("y_val","—")
        cx = comments_by_hex.get(gid, [])
        c_html = "".join([
            f'<div style="font-size:11px;border-left:3px solid '
            f'{"#27AE60" if c["sentiment_label"]=="positive" else "#C0392B" if c["sentiment_label"]=="negative" else "#888"}'
            f';padding:2px 5px;margin:2px 0">{str(c["comment"])[:100]}</div>'
            for c in cx
        ]) or "<i style='font-size:10px;color:#888'>No comments</i>"
        return (f'<div style="font-family:sans-serif;min-width:210px">'
                f'<b>{gid}</b><hr style="margin:3px 0">'
                f'<table style="font-size:11px;width:100%">'
                f'<tr><td><b>{x_label}</b></td><td>{x_val}</td></tr>'
                f'<tr><td><b>{y_label}</b></td><td>{y_val}</td></tr>'
                f'<tr><td><b>Bivariate</b></td><td>{bv}</td></tr>'
                f'</table><hr style="margin:3px 0">'
                f'<b style="font-size:10px">Comments:</b>{c_html}</div>')

    # ── MODE 1: Bivariate hex map ──────────────────────────────────────────────
    if mode == "🗺 Bivariate":
        m = folium.Map(location=[50.075,14.437], zoom_start=11,
                       tiles="CartoDB positron")
        folium.GeoJson(
            geojson,
            style_function=make_style(topic_df),
            highlight_function=highlight_fn,
            tooltip=folium.GeoJsonTooltip(
                fields=["GRID_ID"], aliases=["Cell:"],
                style="font-size:11px"),
        ).add_to(m)
        # Invisible centroid markers for popups with comments
        for feat in geojson["features"]:
            gid = feat["properties"].get("GRID_ID","")
            c   = shape_centroid(feat["geometry"])
            if c:
                folium.Marker(
                    location=c,
                    popup=folium.Popup(make_popup_html(gid, topic_df), max_width=300),
                    icon=folium.DivIcon(html="", icon_size=(0,0))
                ).add_to(m)
        st_folium(m, width=None, height=470, returned_objects=[])

    # ── MODE 2: Comments on map ────────────────────────────────────────────────
    elif mode == "💬 Comments":
        emotion_key = TOPIC_EMOTION.get(sel_topic, sel_topic)
        topic_filt  = filt[filt["emotion"] == emotion_key].copy()
        m = folium.Map(location=[50.075,14.437], zoom_start=11,
                       tiles="CartoDB positron")
        cluster = MarkerCluster(max_cluster_radius=50).add_to(m)
        sample  = topic_filt.sample(min(len(topic_filt), 2000), random_state=42)
        for _, row in sample.iterrows():
            s_color = ("#27AE60" if row["sentiment_label"]=="positive"
                       else "#C0392B" if row["sentiment_label"]=="negative" else "#888")
            folium.CircleMarker(
                location=[row["y"], row["x"]],
                radius=7,
                color=s_color, fill=True, fill_color=s_color,
                fill_opacity=0.8, weight=1,
                popup=folium.Popup(
                    f'<b>{row["emotion"]}</b><br>{str(row["comment"])[:180]}<br>'
                    f'<small>Age:{row["age"]} | {row["gender"]} | '
                    f'<span style="color:{s_color}">{row["sentiment_label"]}</span></small>',
                    max_width=270),
                tooltip=row["sentiment_label"],
            ).add_to(cluster)

        # Sentiment legend inside map
        legend_html = """
        <div style="position:fixed;bottom:20px;left:20px;z-index:9999;
             background:white;padding:8px 12px;border-radius:8px;
             border:1px solid #ccc;font-size:12px;box-shadow:2px 2px 5px rgba(0,0,0,0.2)">
          <b>Sentiment</b><br>
          <span style="color:#27AE60">● Positive</span><br>
          <span style="color:#888">● Neutral</span><br>
          <span style="color:#C0392B">● Negative</span>
        </div>"""
        m.get_root().html.add_child(folium.Element(legend_html))
        st_folium(m, width=None, height=470, returned_objects=[])

    # ── MODE 3: Swipe compare ──────────────────────────────────────────────────
    elif mode == "⟺ Compare":
        m = folium.Map(location=[50.075,14.437], zoom_start=11,
                       tiles="CartoDB positron")
        layer_left  = folium.FeatureGroup(name=sel_topic)
        layer_right = folium.FeatureGroup(name=sel_topic2)

        folium.GeoJson(geojson, style_function=make_style(topic_df),
                       tooltip=folium.GeoJsonTooltip(
                           fields=["GRID_ID"], aliases=["Cell:"])).add_to(layer_left)
        folium.GeoJson(geojson, style_function=make_style(topic_df2),
                       tooltip=folium.GeoJsonTooltip(
                           fields=["GRID_ID"], aliases=["Cell:"])).add_to(layer_right)

        layer_left.add_to(m)
        layer_right.add_to(m)
        SideBySideLayers(layer_left=layer_left, layer_right=layer_right).add_to(m)

        # Labels inside map
        label_html = f"""
        <div style="position:fixed;top:10px;left:60px;z-index:9999;
             background:rgba(255,255,255,0.85);padding:4px 10px;
             border-radius:6px;font-size:12px;font-weight:700;
             border:1px solid #ccc">{sel_topic}</div>
        <div style="position:fixed;top:10px;right:30px;z-index:9999;
             background:rgba(255,255,255,0.85);padding:4px 10px;
             border-radius:6px;font-size:12px;font-weight:700;
             border:1px solid #ccc">{sel_topic2}</div>"""
        m.get_root().html.add_child(folium.Element(label_html))
        st_folium(m, width=None, height=470, returned_objects=[])

# ── Right: sentiment donut ─────────────────────────────────────────────────────
with col_right:
    st.markdown("---")
    emotion_key = TOPIC_EMOTION.get(sel_topic, sel_topic)
    sent_df = filt[filt["emotion"] == emotion_key]
    st.markdown(f"**{len(sent_df):,} comments**")
    st.markdown("**Sentiment**")
    if len(sent_df) > 0:
        sent  = sent_df["sentiment_label"].value_counts()
        order = ["positive","neutral","negative"]
        cmap  = {"positive":"#27AE60","neutral":"#95A5A6","negative":"#C0392B"}
        lbls  = [l for l in order if l in sent.index]
        fig   = go.Figure(go.Pie(
            labels=lbls, values=[sent[l] for l in lbls], hole=0.55,
            marker_colors=[cmap[l] for l in lbls],
            textinfo="percent", textfont_size=11,
        ))
        fig.update_layout(margin=dict(t=0,b=0,l=0,r=0), height=180,
                          legend=dict(font=dict(size=9)))
        st.plotly_chart(fig, use_container_width=True)
