"""
Run this once locally to precompute hex-level data for the dashboard.
Outputs: data/comments_with_grid.csv, data/hex_all_topics.csv
"""
import json, os
import pandas as pd
import numpy as np
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

BASE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(BASE, "data")
os.makedirs(OUT, exist_ok=True)

# ── Load hex grid ──────────────────────────────────────────────────────────────
print("Loading hex grid...")
with open(os.path.join(BASE, "hex_grid.geojson"), encoding="utf-8") as f:
    gj = json.load(f)

# Fix field name (ArcGIS exports with table prefix)
def get_grid_id(props):
    for k, v in props.items():
        if "GRID_ID" in k:
            return v
    return None

hexagons   = []
grid_ids   = []
for feat in gj["features"]:
    gid = get_grid_id(feat["properties"])
    if gid:
        hexagons.append(shape(feat["geometry"]))
        grid_ids.append(gid)

print(f"  {len(hexagons)} hexagons loaded")

# Build spatial index for fast point-in-polygon
tree = STRtree(hexagons)

def find_grid_id(x, y):
    pt = Point(x, y)
    for idx in tree.query(pt):          # get bbox candidates first
        if hexagons[idx].contains(pt):  # then exact check
            return grid_ids[idx]
    return None

# ── Assign GRID_ID to comments ─────────────────────────────────────────────────
print("Assigning comments to hexagons...")
comments = pd.read_csv(
    os.path.join(BASE, "comment_analysis", "comments_sentiment_all.csv"),
    encoding="utf-8-sig"
)
comments.columns = comments.columns.str.strip()
comments = comments.dropna(subset=["x", "y"])

comments["GRID_ID"] = comments.apply(
    lambda r: find_grid_id(r["x"], r["y"]), axis=1
)
comments.to_csv(os.path.join(OUT, "comments_with_grid.csv"), index=False, encoding="utf-8-sig")
print(f"  Saved {len(comments)} comments with GRID_ID")
print(f"  Matched: {comments['GRID_ID'].notna().sum()} / {len(comments)}")

# ── Bivariate colors ───────────────────────────────────────────────────────────
BIVAR_COLORS = {
    "1-1": "#e8e8e8", "2-1": "#dfb0d6", "3-1": "#be64ac",
    "1-2": "#ace4e4", "2-2": "#a5b4c2", "3-2": "#8c62aa",
    "1-3": "#5ac8c8", "2-3": "#5698b9", "3-3": "#3b4994",
    "nan-nan": "#cccccc", "nan-1": "#cccccc", "1-nan": "#cccccc",
}
DEFAULT_COLOR = "#dddddd"

def add_bivar(df, x_col, y_col):
    df = df.copy()
    df["PC_class"]  = pd.qcut(df[x_col].rank(method="first"), q=3,
                               labels=[1,2,3], duplicates="drop")
    df["ENV_class"] = pd.qcut(df[y_col].rank(method="first"), q=3,
                               labels=[1,2,3], duplicates="drop")
    df["bivar_class"] = df["PC_class"].astype(str) + "-" + df["ENV_class"].astype(str)
    return df

# ── Load & prepare each topic ──────────────────────────────────────────────────
print("Preparing topic data...")

topics = {}

# Safety
saf = pd.read_csv(os.path.join(BASE, "../safety/NightLights_safety.csv"))
saf = saf.rename(columns={"MEAN": "NightLights_mean"})[["GRID_ID","Point_Count","NightLights_mean"]].dropna()
saf = add_bivar(saf, "Point_Count", "NightLights_mean")
saf["topic"] = "Safety"
saf["x_label"] = "Safety marks"
saf["y_label"] = "Night Lights"
saf["x_val"]   = saf["Point_Count"].round(1).astype(str)
saf["y_val"]   = saf["NightLights_mean"].round(2).astype(str)
topics["Safety"] = saf

# Proudness
pro = pd.read_csv(os.path.join(BASE, "../proudness/proudness_bivariate.csv"))
pro["topic"] = "Proudness"
pro["x_label"] = "Proud marks"
pro["y_label"] = "NDVI"
pro["x_val"]   = pro["Point_Count"].round(1).astype(str)
pro["y_val"]   = pro["NDVI_mean"].round(3).astype(str)
topics["Proudness"] = pro

# Free Time
ft = pd.read_csv(os.path.join(BASE, "../Free_time/freetime_full.csv"))
ft["topic"] = "Free Time"
ft["x_label"] = "Activity (per capita)"
ft["y_label"] = "NDVI"
ft["x_val"]   = ft["Norm_count"].round(2).astype(str)
ft["y_val"]   = ft["NDVI_mean"].round(3).astype(str)
topics["Free Time"] = ft

# Green Space
gs = pd.read_csv(os.path.join(BASE, "../green_space/greenspace_full.csv"))
gs = add_bivar(gs, "GS_density", "NDVI_mean")
gs["topic"] = "Green Space"
gs["x_label"] = "Demand density"
gs["y_label"] = "NDVI"
gs["x_val"]   = gs["GS_density"].round(3).astype(str)
gs["y_val"]   = gs["NDVI_mean"].round(3).astype(str)
topics["Green Space"] = gs

# Need to Change
ntc = pd.read_csv(os.path.join(BASE, "../need_to_change/needchange_full.csv"))
ntc["topic"] = "Need to Change"
ntc["x_label"] = "Need to Change marks"
ntc["y_label"] = "Composite (LST+NO2+NDVI)"
ntc["x_val"]   = ntc["Point_Count"].round(1).astype(str)
ntc["y_val"]   = ntc["Composite"].round(3).astype(str)
topics["Need to Change"] = ntc

# Traffic Hazard
tr = pd.read_csv(os.path.join(BASE, "../traffic/traffic_hazard_full.csv"))
tr["topic"] = "Traffic Hazard"
tr["x_label"] = "Traffic hazard marks"
tr["y_label"] = "Imperviousness (IMD)"
tr["x_val"]   = tr["Point_Count"].round(1).astype(str)
tr["y_val"]   = tr["IMD_mean"].round(2).astype(str)
topics["Traffic Hazard"] = tr

# Waste Bin
wb = pd.read_csv(os.path.join(BASE, "../waste_bin/wastebin_full.csv"))
wb["topic"] = "Waste Bin"
wb["x_label"] = "Waste bin count"
wb["y_label"] = "Population density"
wb["x_val"]   = wb["Point_Count"].round(1).astype(str)
wb["y_val"]   = wb["Pop_mean"].round(1).astype(str)
topics["Waste Bin"] = wb

# Add respondents (Point_Count) to all topics
for name, df in topics.items():
    if "Point_Count" in df.columns:
        df["respondents"] = df["Point_Count"].fillna(0).astype(int).astype(str)
    else:
        df["respondents"] = "—"

# ── Combine all topics ─────────────────────────────────────────────────────────
KEEP = ["GRID_ID","topic","x_label","y_label","x_val","y_val","bivar_class","respondents"]
combined = []
for name, df in topics.items():
    df = df.copy()
    if "bivar_class" not in df.columns:
        df["bivar_class"] = "1-1"
    cols = [c for c in KEEP if c in df.columns]
    combined.append(df[cols])

all_topics = pd.concat(combined, ignore_index=True)
all_topics["color"] = all_topics["bivar_class"].map(
    lambda x: BIVAR_COLORS.get(str(x), DEFAULT_COLOR)
)
all_topics.to_csv(os.path.join(OUT, "hex_all_topics.csv"), index=False, encoding="utf-8-sig")
print(f"  Saved hex_all_topics.csv — {len(all_topics)} rows across {all_topics['topic'].nunique()} topics")
print("\nDone! Run dashboard.py next.")
