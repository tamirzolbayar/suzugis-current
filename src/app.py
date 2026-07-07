import json
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from branca.element import MacroElement, Template
from streamlit_folium import st_folium
from popup import (
    ROAD_CATEGORY_TYPES,
    ROAD_CENTERLINE_TYPES,
    ROAD_STATE_TYPES,
    ROAD_WIDTH_TYPES,
    decode_code,
    make_popup_html,
)
from map_generator import style_by_restriction
from excel_loader import load_excel, save_excel
from filters import apply_filters
from config import DEFAULT_LOCATION, DEFAULT_ZOOM, MAP_STYLES
from permit_documents import get_permit_pdf_path, make_permit_link_html


class FeatureInfoBinder(MacroElement):
    def __init__(self, layer):
        super().__init__()
        self._name = "FeatureInfoBinder"
        self.layer_name = layer.get_name()
        self._template = Template(
            """
            {% macro script(this, kwargs) %}
            {{ this.layer_name }}.eachLayer(function(layer) {
                if (!layer.feature || !layer.feature.properties) {
                    return;
                }

                const props = layer.feature.properties;
                if (props._info_html) {
                    layer.bindTooltip(props._info_html, {
                        sticky: true,
                        className: "road-info-tooltip"
                    });
                    layer.bindPopup(props._info_html, {
                        maxWidth: 450
                    });
                }
            });
            {% endmacro %}
            """
        )


def parse_progress(value):
    try:
        return int(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return 0


def iter_coordinate_pairs(geometry):
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])

    if geometry_type == "Point":
        yield coordinates
    elif geometry_type in ("LineString", "MultiPoint"):
        yield from coordinates
    elif geometry_type in ("Polygon", "MultiLineString"):
        for part in coordinates:
            yield from part
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                yield from ring


def get_feature_bounds(features):
    lats = []
    lngs = []

    for feature in features:
        for coordinate in iter_coordinate_pairs(feature.get("geometry", {})):
            if len(coordinate) >= 2:
                lngs.append(coordinate[0])
                lats.append(coordinate[1])

    if not lats or not lngs:
        return None

    return [[min(lats), min(lngs)], [max(lats), max(lngs)]]


def find_feature_by_restriction_id(features, restriction_id):
    for feature in features:
        props = feature.get("properties", {})
        if props.get("規制ID") == restriction_id:
            return feature
    return None


def line_coordinates_to_locations(feature):
    geometry = feature.get("geometry", {})
    if geometry.get("type") != "LineString":
        return []

    return [
        [coordinate[1], coordinate[0]]
        for coordinate in geometry.get("coordinates", [])
        if len(coordinate) >= 2
    ]


def make_neighboring_route(locations, offset_direction):
    if len(locations) < 2:
        return []

    start_lat, start_lng = locations[0]
    end_lat, end_lng = locations[-1]
    lng_delta = end_lng - start_lng
    lat_delta = end_lat - start_lat
    length = (lng_delta**2 + lat_delta**2) ** 0.5

    if length == 0:
        return []

    normal_lng = -lat_delta / length
    normal_lat = lng_delta / length
    offset = DETOUR_OFFSET_DEGREES * offset_direction

    return [
        [lat + normal_lat * offset, lng + normal_lng * offset]
        for lat, lng in locations
    ]


def build_detour_routes(features, district):
    routes = []
    for source in DETOUR_ROUTE_SOURCES.get(district, []):
        feature = find_feature_by_restriction_id(features, source["restriction_id"])
        if feature is None:
            continue

        neighboring_locations = make_neighboring_route(
            line_coordinates_to_locations(feature),
            source.get("offset", 1),
        )
        if neighboring_locations:
            routes.append(
                {
                    "name": source["name"],
                    "locations": neighboring_locations,
                }
            )

    return routes


def prepare_map_properties(features):
    for feature in features:
        props = feature.setdefault("properties", {})
        restriction_id = props.get("規制ID", "")
        permit_link_html = make_permit_link_html(BASE_DIR, restriction_id)
        props["道路中心線"] = decode_code(ROAD_CENTERLINE_TYPES, props.get("N13_002", ""))
        props["道路分類"] = decode_code(ROAD_CATEGORY_TYPES, props.get("N13_003", ""))
        props["道路状態"] = decode_code(ROAD_STATE_TYPES, props.get("N13_004", ""))
        props["幅員"] = decode_code(ROAD_WIDTH_TYPES, props.get("N13_006", ""))
        props["道路使用許可"] = (
            "登録済" if get_permit_pdf_path(BASE_DIR, restriction_id).exists() else "未登録"
        )
        props["_info_html"] = make_popup_html(props, permit_link_html)


BASE_DIR = Path(__file__).resolve().parent.parent
GEOJSON_PATH = BASE_DIR / "data" / "geojson" / "suzu_sample.geojson"
EXCEL_PATH = BASE_DIR / "data" / "excel" / "restriction_list.xlsx"
DETOUR_COLOR = "#2e7d32"
DETOUR_OFFSET_DEGREES = 0.00012
DETOUR_ROUTE_SOURCES = {
    "飯田": [
        {"name": "飯田地区 迂回路 R-003", "restriction_id": "R-003", "offset": 1},
        {"name": "飯田地区 迂回路 R-098", "restriction_id": "R-098", "offset": -1},
        {"name": "飯田地区 迂回路 R-101", "restriction_id": "R-101", "offset": 1},
        {"name": "飯田地区 迂回路 R-106", "restriction_id": "R-106", "offset": -1},
        {"name": "飯田地区 迂回路 R-113", "restriction_id": "R-113", "offset": 1},
    ]
}
PRIORITY_DISTRICTS = ["蛸島", "正院", "飯田", "上戸", "直", "宝立"]

st.set_page_config(page_title="珠洲市復旧道路管理マップ", layout="wide")

st.markdown(
    """
    <style>
        .block-container {
            max-width: 100%;
            padding-top: 0.15rem;
            padding-left: 0;
            padding-right: 0;
            padding-bottom: 0;
        }

        [data-testid="stSidebar"] {
            min-width: 21rem;
            max-width: 21rem;
        }

        [data-testid="stVerticalBlock"] {
            gap: 0.15rem;
        }

        .main-title {
            display: none;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-title">珠洲市復旧道路管理マップ</div>', unsafe_allow_html=True)
df, restriction_dict = load_excel(EXCEL_PATH)


# Sidebar

with st.sidebar:
    st.header("珠洲市復旧道路管理マップ")
    st.caption("復旧道路・交通規制 管理画面")

    st.markdown("---")
    st.subheader("🗺 地図設定")

    map_style = st.selectbox(
        "地図タイプ",
        list(MAP_STYLES.keys()),
        index=list(MAP_STYLES.keys()).index("淡色地図"),
    )

    st.markdown("---")
    st.subheader("📅 表示条件")

    target_date = st.date_input(
        "対象日",
        value=pd.to_datetime("2026-07-15")
    )

    selected_districts = st.multiselect(
        "重点地区",
        PRIORITY_DISTRICTS,
        default=PRIORITY_DISTRICTS,
    )

    st.subheader("迂回路")
    show_detours = st.checkbox("迂回路を表示", value=True)
    detour_district = st.selectbox("迂回路地区", list(DETOUR_ROUTE_SOURCES.keys()))

    st.subheader("🚧 規制種別")

    show_full_closure = st.checkbox("全面通行止め", value=True)
    show_alternate = st.checkbox("片側交互通行", value=True)
    show_lane = st.checkbox("車線規制", value=True)
    show_completed = st.checkbox("完了", value=True)
    st.subheader("📊 進捗")
    st.subheader("🏗 施工者")

    contractors = ["すべて"] + sorted(df["施工者"].dropna().unique().tolist())
    
    contractor_filter = st.selectbox(
        "施工者を選択",
        contractors
    )

    st.markdown("---")
    st.subheader("✏️ 選択中の規制")

    restriction_ids = df["規制ID"].tolist()
    selected_id = st.session_state.get(
        "selected_restriction_id",
        restriction_ids[0]
    )
    if selected_id not in restriction_ids:
        selected_id = restriction_ids[0]

    selected_id = st.selectbox(
        "編集する規制ID",
        restriction_ids,
        index=restriction_ids.index(selected_id),
    )
    st.session_state["selected_restriction_id"] = selected_id

    edit_id = selected_id
    edit_row = df[df["規制ID"] == edit_id].iloc[0]
    permit_link_html = make_permit_link_html(BASE_DIR, edit_id)

    st.markdown(
        f"""
        <div style="
            background-color:#f7f9fc;
            padding:12px;
            border-radius:10px;
            border:1px solid #d0d7de;
            margin-bottom:12px;
        ">
            <div style="font-size:14px; color:#666;">現在選択中</div>
            <div style="font-size:22px; font-weight:bold;">🚧 {edit_id}</div>
            <div style="font-size:14px; margin-top:4px;">{edit_row["工事名"]}</div>
            <div style="font-size:13px; color:#666; margin-top:4px;">
                {edit_row["施工者"]} / 進捗 {edit_row["進捗率"]}%
            </div>
            <div style="font-size:13px; margin-top:8px;">
                <b>道路使用許可:</b> {permit_link_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.form("selected_road_edit_form"):
        edit_contractor = st.text_input(
            "施工者",
            value=str(edit_row["施工者"])
        )

        edit_progress = st.number_input(
            "進捗率",
            min_value=0,
            max_value=100,
            value=parse_progress(edit_row["進捗率"])
        )

        edit_note = st.text_area(
            "備考",
            value=str(edit_row["備考"])
        )

        submitted = st.form_submit_button("保存")

        if submitted:
            df.loc[df["規制ID"] == edit_id, "施工者"] = edit_contractor
            df.loc[df["規制ID"] == edit_id, "進捗率"] = edit_progress
            df.loc[df["規制ID"] == edit_id, "備考"] = edit_note

            backup_path = save_excel(df, EXCEL_PATH)
            st.success(f"{edit_id} を保存しました")
            if backup_path is not None:
                st.caption(f"バックアップ作成：{backup_path.name}")
            else:
                st.caption("バックアップ作成：未確認")
            st.rerun()
    

# GeoJSON load
with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
    geojson_data = json.load(f)

all_features = geojson_data["features"]

geojson_data, filtered_features = apply_filters(
    geojson_data=geojson_data,
    restriction_dict=restriction_dict,
    target_date=target_date,
    show_full_closure=show_full_closure,
    show_alternate=show_alternate,
    show_lane=show_lane,
    show_completed=show_completed,
    contractor_filter=contractor_filter,
)

if selected_districts:
    filtered_features = [
        feature
        for feature in filtered_features
        if feature.get("properties", {}).get("重点地区") in selected_districts
    ]
    geojson_data["features"] = filtered_features
else:
    filtered_features = []
    geojson_data["features"] = []


# Counts
restriction_counts = pd.Series(
    [feature.get("properties", {}).get("規制種別", "") for feature in filtered_features]
)

full_closure_count = int(restriction_counts.astype(str).str.contains("全面", na=False).sum())
alternate_count = int(
    restriction_counts.astype(str).str.contains("片側|片交", regex=True, na=False).sum()
)
lane_count = int(restriction_counts.astype(str).str.contains("車線", na=False).sum())
completed_count = int(restriction_counts.astype(str).str.contains("完了", na=False).sum())

m = folium.Map(
    location=DEFAULT_LOCATION,
    zoom_start=DEFAULT_ZOOM,
    tiles=None,
    width="100%",
    height="850px",
)

folium.TileLayer(
    tiles=MAP_STYLES[map_style]["url"],
    attr=MAP_STYLES[map_style]["attr"],
    name=map_style,
).add_to(m)

visible_detour_routes = []
if show_detours and detour_district in selected_districts:
    visible_detour_routes = build_detour_routes(all_features, detour_district)

if visible_detour_routes:
    detour_layer = folium.FeatureGroup(name="迂回路", show=True)
    for route in visible_detour_routes:
        route_name = route["name"]
        route_popup = f"""
        <div style="font-size:13px; line-height:1.6; min-width:180px;">
            <div style="font-weight:700; color:#1b5e20;">{route_name}</div>
            <div>規制区間に隣接する迂回路</div>
        </div>
        """
        folium.PolyLine(
            locations=route["locations"],
            color=DETOUR_COLOR,
            weight=6,
            opacity=0.92,
            tooltip=route_name,
            popup=folium.Popup(route_popup, max_width=260),
        ).add_to(detour_layer)
    detour_layer.add_to(m)

if len(geojson_data["features"]) > 0:
    prepare_map_properties(geojson_data["features"])

    feature_bounds = get_feature_bounds(geojson_data["features"])
    if feature_bounds is not None:
        m.fit_bounds(feature_bounds, padding=(30, 30))

    restriction_layer = folium.GeoJson(
        geojson_data,
        name="規制区間",
        style_function=lambda feature: style_by_restriction(
            feature,
            st.session_state.get("selected_restriction_id")
        ),
    ).add_to(m)
    m.add_child(FeatureInfoBinder(restriction_layer))

else:
    st.warning("この条件に該当する規制区間はありません。")

map_summary_html = f"""
<div style="
    position: fixed;
    right: 24px;
    bottom: 44px;
    z-index: 9999;
    min-width: 210px;
    background: rgba(255,255,255,0.94);
    border: 1px solid #d0d7de;
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.14);
    padding: 10px 12px;
    color: #1f2937;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 12px;
    line-height: 1.45;
">
    <div style="font-weight:700; font-size:13px; margin-bottom:6px;">📊 表示集計</div>
    <div style="display:grid; grid-template-columns: 1fr auto; gap:2px 12px;">
        <span>表示中</span><strong>{len(filtered_features)}</strong>
        <span>全面通行止め</span><strong>{full_closure_count}</strong>
        <span>片側交互通行</span><strong>{alternate_count}</strong>
        <span>車線規制</span><strong>{lane_count}</strong>
        <span>完了</span><strong>{completed_count}</strong>
        <span>迂回路</span><strong>{len(visible_detour_routes)}</strong>
    </div>
    <div style="height:1px; background:#e5e7eb; margin:8px 0;"></div>
    <div style="font-weight:700; font-size:13px; margin-bottom:6px;">🧭 凡例</div>
    <div style="display:grid; gap:4px;">
        <div><span style="display:inline-block;width:26px;height:5px;background:#d32f2f;margin-right:8px;vertical-align:middle;"></span>全面通行止め</div>
        <div><span style="display:inline-block;width:26px;height:5px;background:#f57c00;margin-right:8px;vertical-align:middle;"></span>片側交互通行</div>
        <div><span style="display:inline-block;width:26px;height:5px;background:#fbc02d;margin-right:8px;vertical-align:middle;"></span>車線規制</div>
        <div><span style="display:inline-block;width:26px;height:5px;background:#1976d2;margin-right:8px;vertical-align:middle;"></span>完了</div>
        <div><span style="display:inline-block;width:26px;height:5px;background:#2e7d32;margin-right:8px;vertical-align:middle;"></span>迂回路</div>
    </div>
</div>
"""
m.get_root().html.add_child(folium.Element(map_summary_html))

folium.LayerControl().add_to(m)

st_folium(m, width=1500, height=850)
