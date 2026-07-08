import folium
import json
import pandas as pd
from pathlib import Path
from road_styles import RESTRICTION_RED, WORK_TYPE_COLORS, get_restriction_visual_type, get_work_type_color

BASE_DIR = Path(__file__).resolve().parent.parent

GEOJSON_PATH = BASE_DIR / "data" / "geojson" / "suzu_sample.geojson"
EXCEL_PATH = BASE_DIR / "data" / "excel" / "restriction_list.xlsx"
OUTPUT_PATH = BASE_DIR / "output" / "suzu_map.html"

df = pd.read_excel(EXCEL_PATH)


# 列名の前後空白を削除
df.columns = df.columns.str.strip()

# 規制IDを文字列化して前後空白削除
df["規制ID"] = df["規制ID"].astype(str).str.strip()
if "工事種別" not in df.columns:
    df["工事種別"] = ""
df["工事種別"] = df["工事種別"].fillna("").astype(str).str.strip()

TARGET_DATE = pd.to_datetime("2026-07-15")

restriction_dict = df.set_index("規制ID").to_dict("index")

with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
    geojson_data = json.load(f)

m = folium.Map(
    location=[37.436, 137.260],
    zoom_start=14,
    tiles=None
)
filtered_features = []

for i, feature in enumerate(geojson_data["features"], start=1):
    props = feature.setdefault("properties", {})
    props["規制ID"] = f"R-{i:03}"

    if props["規制ID"] in restriction_dict:
        props.update(restriction_dict[props["規制ID"]])

        start = pd.to_datetime(props["開始日"])
        end = pd.to_datetime(props["終了日"])

        if start <= TARGET_DATE <= end:
            filtered_features.append(feature)
    else:
        props["工事名"] = "Excel未登録"
        props["規制種別"] = "未登録"
        props["開始日"] = ""
        props["終了日"] = ""
        props["施工者"] = ""
        props["進捗率"] = ""
        props["備考"] = "restriction_list.xlsx に該当IDなし"

geojson_data["features"] = filtered_features
        
def style_by_restriction(feature):
    props = feature["properties"]
    restriction = str(props.get("規制種別", "")).strip()
    work_type = str(props.get("工事種別", "")).strip()
    visual_type = get_restriction_visual_type(restriction)
    color = get_work_type_color(work_type)

    style = {
        "color": color,
        "weight": 6,
        "opacity": 0.9,
    }
    if not work_type and visual_type == "道路規制":
        style["dashArray"] = "2, 9"
    return style

folium.TileLayer(
    tiles="https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
    attr="地理院地図",
    name="地理院地図",
    overlay=False,
    control=True
).add_to(m)

from shapely.geometry import shape

folium.GeoJson(
    geojson_data,
    name="規制区間",
    style_function=style_by_restriction,
    tooltip=folium.GeoJsonTooltip(
        fields=["規制ID", "規制種別", "進捗率"],
        aliases=["ID", "規制", "進捗"],
        sticky=True
    ),
    popup=folium.GeoJsonPopup(
        fields=["規制ID", "工事名", "規制種別", "開始日", "終了日", "施工者", "進捗率", "備考"],
        aliases=["ID", "工事名", "規制種別", "開始日", "終了日", "施工者", "進捗率", "備考"],
        localize=True
    )
).add_to(m)

for feature in geojson_data["features"]:
    geom = shape(feature["geometry"])
    center = geom.centroid
    props = feature["properties"]

    label_text = f"{props.get('規制ID', '')}<br>{props.get('規制種別', '')}"

    folium.Marker(
        location=[center.y, center.x],
        icon=folium.DivIcon(
            html=f"""
            <div style="
                font-size: 12px;
                font-weight: bold;
                background-color: white;
                border: 1px solid #666;
                border-radius: 4px;
                padding: 2px 4px;
                white-space: nowrap;
            ">
            {label_text}
            </div>
            """
        )
    ).add_to(m)

title_html = f"""
<div style="
    position: fixed;
    top: 20px;
    left: 50px;
    z-index: 9999;
    background-color: white;
    padding: 10px 16px;
    border: 2px solid #999;
    border-radius: 6px;
    font-size: 16px;
">
<b>珠洲市 交通規制マップ</b><br>
対象日：{TARGET_DATE.strftime('%Y-%m-%d')}
</div>
"""

m.get_root().html.add_child(folium.Element(title_html))

folium.LayerControl().add_to(m)
legend_html = """
<div style="
    position: fixed;
    bottom: 30px;
    right: 30px;
    z-index: 9999;
    background-color: white;
    padding: 12px 16px;
    border: 2px solid #999;
    border-radius: 6px;
    font-size: 14px;
    line-height: 1.8;
">
<b>凡例</b><br>
<span style="color:%s;">━</span> 通行止め<br>
<span style="color:%s;">┄</span> 道路規制<br>
%s
<span style="color:gray;">━</span> 未分類
</div>
""" % (
    RESTRICTION_RED,
    RESTRICTION_RED,
    "".join(
        f'<span style="color:{color};">━</span> {work_type}<br>'
        for work_type, color in WORK_TYPE_COLORS.items()
        if work_type in set(df["工事種別"])
    ),
)

m.get_root().html.add_child(folium.Element(legend_html))
m.save(OUTPUT_PATH)

print(f"作成完了: {OUTPUT_PATH}")
