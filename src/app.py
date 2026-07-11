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
from road_styles import RESTRICTION_RED, WORK_TYPE_COLORS, get_restriction_visual_type


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


class MapViewPersistence(MacroElement):
    def __init__(self, map_object, storage_key="suzugis_map_view"):
        super().__init__()
        self._name = "MapViewPersistence"
        self.map_name = map_object.get_name()
        self.storage_key = storage_key
        self._template = Template(
            """
            {% macro script(this, kwargs) %}
            (function() {
                const map = {{ this.map_name }};
                const storageKey = {{ this.storage_key|tojson }};

                function restoreView() {
                    try {
                        const saved = JSON.parse(window.localStorage.getItem(storageKey));
                        if (
                            saved &&
                            typeof saved.lat === "number" &&
                            typeof saved.lng === "number" &&
                            typeof saved.zoom === "number"
                        ) {
                            map.setView([saved.lat, saved.lng], saved.zoom, { animate: false });
                        }
                    } catch (error) {
                        window.localStorage.removeItem(storageKey);
                    }
                }

                function saveView() {
                    const center = map.getCenter();
                    window.localStorage.setItem(storageKey, JSON.stringify({
                        lat: center.lat,
                        lng: center.lng,
                        zoom: map.getZoom()
                    }));
                }

                restoreView();
                map.on("moveend zoomend", saveView);
            })();
            {% endmacro %}
            """
        )


def parse_progress(value):
    try:
        return int(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return 0


def parse_date_for_input(value):
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.Timestamp.today().date()
    return parsed.date()


def next_record_id(existing_ids, prefix):
    max_number = 0
    for raw_id in existing_ids:
        digits = "".join(char for char in str(raw_id) if char.isdigit())
        if digits:
            max_number = max(max_number, int(digits))
    return f"{prefix}-{max_number + 1:03d}"


def load_geojson():
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_geojson(geojson_data):
    with open(GEOJSON_PATH, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)


def make_placeholder_geometry(geojson_data, district, seed):
    district_points = []
    for feature in geojson_data.get("features", []):
        if feature.get("properties", {}).get("重点地区") != district:
            continue
        district_points.extend(iter_coordinate_pairs(feature.get("geometry", {})))

    if not district_points:
        center_lng, center_lat = DEFAULT_LOCATION[1], DEFAULT_LOCATION[0]
    else:
        center_lng = sum(point[0] for point in district_points) / len(district_points)
        center_lat = sum(point[1] for point in district_points) / len(district_points)

    drift = ((seed % 11) - 5) * 0.00018
    length = 0.00072 + (seed % 4) * 0.00012
    return {
        "type": "LineString",
        "coordinates": [
            [center_lng - length / 2, center_lat + drift],
            [center_lng - length / 6, center_lat + drift / 2],
            [center_lng + length / 6, center_lat - drift / 2],
            [center_lng + length / 2, center_lat - drift],
        ],
    }


def create_map_item(
    item_kind,
    district,
    name,
    work_type,
    restriction_type,
    start_date,
    end_date,
    contractor,
    progress,
    note,
    extra_details=None,
):
    existing_ids = df["規制ID"].astype(str).tolist()
    new_id = next_record_id(existing_ids, "C" if item_kind == "工事" else "R")
    new_row = {
        "規制ID": new_id,
        "工事名": name,
        "工事種別": work_type if item_kind == "工事" else "",
        "規制種別": restriction_type,
        "開始日": pd.Timestamp(start_date),
        "終了日": pd.Timestamp(end_date),
        "施工者": contractor,
        "進捗率": progress,
        "備考": note,
    }
    if extra_details:
        new_row.update(extra_details)

    updated_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_excel(updated_df, EXCEL_PATH)

    current_geojson = load_geojson()
    seed = int("".join(char for char in new_id if char.isdigit()) or "0")
    current_geojson.setdefault("features", []).append(
        {
            "type": "Feature",
            "properties": {
                "N13_001": "",
                "N13_002": "1",
                "N13_003": "3",
                "N13_004": "1",
                "N13_005": 0,
                "N13_006": "1",
                "N13_007": "1",
                "N13_008": "",
                "規制ID": new_id,
                "重点地区": district,
                "元データ": "UI作成",
                "抽出条件": "manual placeholder",
                "地区中心からの距離km": 0,
            },
            "geometry": make_placeholder_geometry(current_geojson, district, seed),
        }
    )
    save_geojson(current_geojson)
    return new_id


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


def find_feature_by_id(features, restriction_id):
    for feature in features:
        if restriction_id in feature.get("properties", {}).values():
            return feature
    return None


def line_feature_locations(feature):
    geometry = feature.get("geometry", {})
    if geometry.get("type") != "LineString":
        return []

    return [
        [coordinate[1], coordinate[0]]
        for coordinate in geometry.get("coordinates", [])
        if len(coordinate) >= 2
    ]


def build_sample_detour_routes(features):
    routes = []
    for route in SAMPLE_DETOUR_ROUTES:
        locations = []
        for restriction_id in route["restriction_ids"]:
            feature = find_feature_by_id(features, restriction_id)
            if feature is None:
                locations = []
                break
            locations.extend(line_feature_locations(feature))

        if locations:
            routes.append({"name": route["name"], "locations": locations})

    return routes


def make_complaint_tooltip(complaint):
    status_color = COMPLAINT_STATUS_COLORS.get(complaint["status"], "#7c3aed")
    return f"""
    <div style="
        font-size:13px;
        line-height:1.55;
        width:300px;
        max-width:300px;
        white-space:normal;
        overflow-wrap:anywhere;
        word-break:break-word;
        box-sizing:border-box;
    ">
        <div style="font-weight:700; color:{status_color}; margin-bottom:4px;">
            苦情 {complaint["id"]} / {complaint["status"]}
        </div>
        <div><b>地区:</b> {complaint["district"]}</div>
        <div><b>受付日:</b> {complaint["date"]}</div>
        <div><b>住所:</b> {complaint["address"]}</div>
        <div><b>電話番号:</b> {complaint["phone"]}</div>
        <div style="margin-top:6px;"><b>苦情内容:</b><br>{complaint["content"]}</div>
        <div style="margin-top:6px;"><b>対応:</b><br>{complaint["response"]}</div>
    </div>
    """


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
COMPLAINT_STATUS_COLORS = {
    "未対応": "#d32f2f",
    "対応済み": "#1b5e20",
    "対応中": "#7c3aed",
}
SAMPLE_DETOUR_ROUTES = [
    {"name": "飯田地区 サンプル迂回路 1", "restriction_ids": ["R-203"]},
    {"name": "飯田地区 サンプル迂回路 2", "restriction_ids": ["R-188", "R-206"]},
    {"name": "飯田地区 サンプル迂回路 3", "restriction_ids": ["R-182"]},
]
COMPLAINTS = [
    {
        "id": "C-001",
        "district": "飯田",
        "location": [37.43618, 137.25942],
        "date": "2026-07-12",
        "address": "珠洲市飯田町12-18",
        "phone": "0768-82-1041",
        "content": "工事車両の出入りが多く、朝の通勤時間帯に歩行者が通りにくい。",
        "response": "誘導員を朝夕の時間帯に追加配置し、歩行者通路をカラーコーンで明示。",
        "status": "対応中",
    },
    {
        "id": "C-002",
        "district": "飯田",
        "location": [37.43758, 137.26036],
        "date": "2026-07-13",
        "address": "珠洲市飯田町15-7",
        "phone": "0768-82-2198",
        "content": "夜間の仮設照明が住宅側に向いていてまぶしい。",
        "response": "照明角度を道路側へ調整し、遮光板を追加設置。",
        "status": "対応済み",
    },
    {
        "id": "C-003",
        "district": "飯田",
        "location": [37.43472, 137.25892],
        "date": "2026-07-14",
        "address": "珠洲市飯田町9-31",
        "phone": "0768-82-3375",
        "content": "片側交互通行の待ち時間が長く、バス停への到着が遅れる。",
        "response": "信号サイクルを見直し、バス通過時間帯は誘導員による優先案内を実施。",
        "status": "未対応",
    },
    {
        "id": "C-004",
        "district": "飯田",
        "location": [37.43834, 137.25878],
        "date": "2026-07-15",
        "address": "珠洲市飯田町18-4",
        "phone": "0768-82-4512",
        "content": "工事区間付近の段差で自転車が通りにくく、雨の日に滑りやすい。",
        "response": "仮舗装を追加し、段差注意看板と滑り止めマットを設置。",
        "status": "対応中",
    },
    {
        "id": "C-005",
        "district": "飯田",
        "location": [37.43532, 137.26146],
        "date": "2026-07-15",
        "address": "珠洲市飯田町7-22",
        "phone": "0768-82-6204",
        "content": "大型車通行時の振動で店舗の商品棚が揺れる。",
        "response": "徐行看板を増設し、施工業者へ低速走行を再周知。",
        "status": "対応中",
    },
    {
        "id": "C-006",
        "district": "飯田",
        "location": [37.43902, 137.25794],
        "date": "2026-07-16",
        "address": "珠洲市飯田町20-11",
        "phone": "0768-82-7830",
        "content": "迂回案内の看板が小さく、交差点で迷う車が多い。",
        "response": "案内看板を大きいものに交換し、交差点手前にも予告看板を追加。",
        "status": "対応済み",
    },
    {
        "id": "C-007",
        "district": "飯田",
        "location": [37.43391, 137.26008],
        "date": "2026-07-16",
        "address": "珠洲市飯田町6-8",
        "phone": "0768-82-5409",
        "content": "朝方の重機作業音が大きく、近隣住宅で会話が聞き取りにくい。",
        "response": "早朝作業を必要最小限にし、防音シートの設置範囲を拡大。",
        "status": "未対応",
    },
    {
        "id": "C-008",
        "district": "飯田",
        "location": [37.43682, 137.26218],
        "date": "2026-07-17",
        "address": "珠洲市飯田町14-26",
        "phone": "0768-82-1187",
        "content": "歩行者通路が狭く、ベビーカーで通る際に車道へ出そうになる。",
        "response": "仮歩道幅を広げ、車道側に仮設ガードフェンスを設置。",
        "status": "対応中",
    },
    {
        "id": "C-009",
        "district": "飯田",
        "location": [37.43792, 137.26122],
        "date": "2026-07-17",
        "address": "珠洲市飯田町17-2",
        "phone": "0768-82-9044",
        "content": "雨天時に排水が悪く、住宅前に水たまりができる。",
        "response": "仮排水溝を清掃し、土のうで水の流れを側溝へ誘導。",
        "status": "対応済み",
    },
    {
        "id": "C-010",
        "district": "飯田",
        "location": [37.43571, 137.25762],
        "date": "2026-07-18",
        "address": "珠洲市飯田町5-19",
        "phone": "0768-82-6731",
        "content": "工事車両の駐車位置により、見通しが悪くなっている。",
        "response": "駐車禁止範囲を設定し、作業車の待機場所を変更。",
        "status": "対応済み",
    },
    {
        "id": "C-011",
        "district": "正院",
        "location": [37.44028, 137.27564],
        "date": "2026-07-18",
        "address": "珠洲市正院町正院21-6",
        "phone": "0768-82-3306",
        "content": "通行止め予告が直前で、配達ルートの変更が間に合わない。",
        "response": "前日までに町内掲示板と現場看板へ予定を掲示する運用に変更。",
        "status": "対応中",
    },
    {
        "id": "C-012",
        "district": "正院",
        "location": [37.43982, 137.27612],
        "date": "2026-07-19",
        "address": "珠洲市正院町正院18-14",
        "phone": "0768-82-5172",
        "content": "工事区間の砂ぼこりで洗濯物が汚れる。",
        "response": "散水回数を増やし、乾燥時は清掃車による路面清掃を追加。",
        "status": "対応中",
    },
    {
        "id": "C-013",
        "district": "蛸島",
        "location": [37.44396, 137.30212],
        "date": "2026-07-19",
        "address": "珠洲市蛸島町ナ部3-5",
        "phone": "0768-82-7925",
        "content": "港方面への案内が分かりにくく、観光客が住宅地へ入り込む。",
        "response": "港方面の誘導看板を追加し、既設看板の矢印方向を修正。",
        "status": "未対応",
    },
    {
        "id": "C-014",
        "district": "上戸",
        "location": [37.42482, 137.23166],
        "date": "2026-07-20",
        "address": "珠洲市上戸町北方2-45",
        "phone": "0768-82-4088",
        "content": "通学時間帯に工事車両が多く、児童の横断が不安。",
        "response": "通学時間帯の搬入を避け、横断箇所に誘導員を配置。",
        "status": "対応済み",
    },
    {
        "id": "C-015",
        "district": "直",
        "location": [37.45848, 137.26218],
        "date": "2026-07-20",
        "address": "珠洲市野々江町直48-9",
        "phone": "0768-82-2651",
        "content": "仮設信号の待ち時間表示がなく、いつ進めるのか分かりづらい。",
        "response": "待ち時間の目安を現場看板に掲示し、誘導員が案内する時間帯を設定。",
        "status": "対応中",
    },
    {
        "id": "C-016",
        "district": "宝立",
        "location": [37.39142, 137.20348],
        "date": "2026-07-21",
        "address": "珠洲市宝立町鵜飼1-32",
        "phone": "0768-82-6093",
        "content": "工事区間手前の道路幅が狭く、対向車とのすれ違いが怖い。",
        "response": "待避場所を明示し、幅員注意看板を手前に追加。",
        "status": "未対応",
    },
    {
        "id": "C-017",
        "district": "宝立",
        "location": [37.39314, 137.20402],
        "date": "2026-07-21",
        "address": "珠洲市宝立町鵜飼3-18",
        "phone": "0768-82-8740",
        "content": "夜間に仮設段差が見えづらく、車の底を擦りそうになる。",
        "response": "反射材付き段差プレートと夜間点滅灯を設置。",
        "status": "対応済み",
    },
    {
        "id": "C-018",
        "district": "飯田",
        "location": [37.43874, 137.26072],
        "date": "2026-07-22",
        "address": "珠洲市飯田町19-16",
        "phone": "0768-82-1437",
        "content": "店舗前の出入口が工事資材で見えにくく、来客が通り過ぎてしまう。",
        "response": "資材置き場を移動し、店舗入口を示す仮設案内板を設置。",
        "status": "対応中",
    },
]
PRIORITY_DISTRICTS = ["蛸島", "正院", "飯田", "上戸", "直", "宝立"]

st.set_page_config(page_title="珠洲市復旧道路管理マップ", layout="wide")

st.markdown(
    """
    <style>
        .block-container {
            max-width: 100%;
            padding-top: 0.25rem;
            padding-left: 0;
            padding-right: 0;
            padding-bottom: 0;
        }

        iframe[title="streamlit_folium.st_folium"] {
            display: block;
            width: 100% !important;
        }

        [data-testid="stIFrame"] {
            width: 100% !important;
        }

        [data-testid="stSidebar"] {
            min-width: 21rem;
            max-width: 21rem;
        }

        [data-testid="stSidebar"] > div:first-child {
            padding-top: 0.55rem;
        }

        .sidebar-brand {
            padding: 0.15rem 0 0.7rem 0;
            border-bottom: 1px solid #d1d5db;
            margin-bottom: 1rem;
        }

        .sidebar-brand-title {
            font-size: 1.42rem;
            line-height: 1.25;
            font-weight: 800;
            color: #111827;
            letter-spacing: 0;
            margin: 0;
        }

        .sidebar-brand-caption {
            font-size: 0.86rem;
            line-height: 1.3;
            color: #6b7280;
            margin-top: 0.22rem;
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
item_ids = df["規制ID"].tolist()


def show_item_edit_form(item_id):
    item_row = df[df["規制ID"] == item_id].iloc[0]
    current_work_type = str(item_row.get("工事種別", "")).strip()
    item_type = "工事" if current_work_type else "規制"

    st.caption(f"{item_type} ID: {item_id}")
    st.markdown(f"**{item_row['工事名']}**")

    edit_name = st.text_input(
        "工事名 / 規制名",
        value=str(item_row["工事名"]),
        key=f"dialog_name_{item_id}",
    )

    date_cols = st.columns(2)
    with date_cols[0]:
        edit_start = st.date_input(
            "開始日",
            value=parse_date_for_input(item_row["開始日"]),
            key=f"dialog_start_{item_id}",
        )
    with date_cols[1]:
        edit_end = st.date_input(
            "終了日",
            value=parse_date_for_input(item_row["終了日"]),
            key=f"dialog_end_{item_id}",
        )

    edit_contractor = st.text_input(
        "施工者",
        value=str(item_row["施工者"]),
        key=f"dialog_contractor_{item_id}",
    )

    edit_progress = st.number_input(
        "進捗率",
        min_value=0,
        max_value=100,
        value=parse_progress(item_row["進捗率"]),
        key=f"dialog_progress_{item_id}",
    )

    work_type_options = [""] + list(WORK_TYPE_COLORS.keys())
    if current_work_type not in work_type_options:
        work_type_options.append(current_work_type)
    edit_work_type = st.selectbox(
        "工事種別",
        work_type_options,
        index=work_type_options.index(current_work_type),
        key=f"dialog_work_type_{item_id}",
    )

    restriction_type_options = [
        value
        for value in df["規制種別"].dropna().astype(str).unique().tolist()
        if value.strip()
    ]
    current_restriction_type = str(item_row.get("規制種別", "")).strip()
    if current_restriction_type not in restriction_type_options:
        restriction_type_options.append(current_restriction_type)
    edit_restriction_type = current_restriction_type
    if not edit_work_type:
        edit_restriction_type = st.selectbox(
            "規制種別",
            restriction_type_options,
            index=restriction_type_options.index(current_restriction_type),
            key=f"dialog_restriction_type_{item_id}",
        )

    edit_note = st.text_area(
        "備考",
        value=str(item_row["備考"]),
        key=f"dialog_note_{item_id}",
    )

    action_cols = st.columns(2)
    with action_cols[0]:
        if st.button("保存", type="primary", key=f"dialog_save_{item_id}"):
            df.loc[df["規制ID"] == item_id, "工事名"] = edit_name
            df.loc[df["規制ID"] == item_id, "開始日"] = pd.Timestamp(edit_start)
            df.loc[df["規制ID"] == item_id, "終了日"] = pd.Timestamp(edit_end)
            df.loc[df["規制ID"] == item_id, "施工者"] = edit_contractor
            df.loc[df["規制ID"] == item_id, "進捗率"] = edit_progress
            df.loc[df["規制ID"] == item_id, "工事種別"] = edit_work_type
            df.loc[df["規制ID"] == item_id, "規制種別"] = edit_restriction_type
            df.loc[df["規制ID"] == item_id, "備考"] = edit_note

            save_excel(df, EXCEL_PATH)
            st.session_state["edit_dialog_id"] = None
            st.success(f"{item_id} を保存しました")
            st.rerun()

    with action_cols[1]:
        if st.button("閉じる", key=f"dialog_close_{item_id}"):
            st.session_state["edit_dialog_id"] = None
            st.rerun()


# Sidebar

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-title">珠洲市復旧道路管理マップ</div>
            <div class="sidebar-brand-caption">復旧道路・交通規制 管理画面</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("📅 表示条件")

    default_period_start = pd.to_datetime("2026-07-15")
    default_period_end = pd.to_datetime("2026-07-16")
    period_cols = st.columns(2)
    with period_cols[0]:
        period_start = st.date_input("開始日", value=default_period_start)
    with period_cols[1]:
        period_end = st.date_input("終了日", value=default_period_end)

    if pd.to_datetime(period_start) > pd.to_datetime(period_end):
        st.warning("開始日は終了日以前にしてください。")
        period_start, period_end = period_end, period_start

    selected_districts = st.multiselect(
        "重点地区",
        PRIORITY_DISTRICTS,
        default=PRIORITY_DISTRICTS,
    )

    st.subheader("🏗 施工者")

    contractors = ["すべて"] + sorted(df["施工者"].dropna().unique().tolist())

    contractor_filter = st.selectbox(
        "施工者を選択",
        contractors
    )

    sidebar_edit_item_id = st.session_state.get("edit_dialog_id")
    if sidebar_edit_item_id in item_ids:
        st.markdown("---")
        st.subheader("✏️ 選択項目を編集")
        show_item_edit_form(sidebar_edit_item_id)

    st.markdown("---")
    st.subheader("➕ 新規作成")

    create_kind = st.radio(
        "作成タイプ",
        ["工事", "規制"],
        horizontal=True,
        key="create_kind",
    )
    if create_kind == "工事":
        create_work_type = st.selectbox(
            "項目種別",
            list(WORK_TYPE_COLORS.keys()),
            key="create_work_type",
        )
        create_restriction_type = "道路規制"
    else:
        create_work_type = ""
        create_restriction_type = st.selectbox(
            "項目種別",
            ["通行止め", "道路規制"],
            key="create_restriction_type",
        )

    with st.form("create_map_item_form", clear_on_submit=True):
        create_district = st.selectbox("重点地区", PRIORITY_DISTRICTS)
        create_name = st.text_input(
            "工事名 / 規制名",
            value="",
            placeholder="例: 市道3号舗装補修工事",
        )

        if create_kind == "工事":
            create_extra_details = {}

            if "下水道" in create_work_type or "水道" in create_work_type:
                water_cols = st.columns(2)
                with water_cols[0]:
                    create_extra_details["管種"] = st.selectbox(
                        "管種",
                        ["下水道", "上水道"],
                        index=0 if "下水道" in create_work_type else 1,
                    )
                    create_extra_details["管径"] = st.selectbox(
                        "管径",
                        ["φ100", "φ150", "φ200", "φ250", "φ300"],
                    )
                with water_cols[1]:
                    create_extra_details["施工延長"] = st.number_input(
                        "施工延長(m)",
                        min_value=1,
                        max_value=3000,
                        value=160,
                        step=5,
                    )

            elif "排水" in create_work_type:
                drainage_cols = st.columns(2)
                with drainage_cols[0]:
                    create_extra_details["排水方式"] = st.selectbox(
                        "排水方式",
                        ["側溝", "暗渠", "開水路", "集水桝連結"],
                    )
                    create_extra_details["施工延長"] = st.number_input(
                        "施工延長(m)",
                        min_value=1,
                        max_value=3000,
                        value=160,
                        step=5,
                    )
                    create_extra_details["側溝サイズ"] = st.selectbox(
                        "側溝サイズ",
                        ["300×300", "400×400", "500×500", "600×600"],
                    )
                with drainage_cols[1]:
                    create_extra_details["集水桝"] = st.number_input(
                        "集水桝(基)",
                        min_value=0,
                        max_value=100,
                        value=8,
                        step=1,
                    )
                    create_extra_details["横断管"] = st.number_input(
                        "横断管(箇所)",
                        min_value=0,
                        max_value=100,
                        value=4,
                        step=1,
                    )
                    create_extra_details["排水方向"] = st.selectbox(
                        "排水方向",
                        ["海側", "山側", "既設水路側", "幹線側溝側"],
                    )
                create_extra_details["排水能力"] = st.selectbox(
                    "排水能力",
                    ["改善予定", "改善中", "暫定改善済み", "能力確認中"],
                )

            else:
                road_cols = st.columns(2)
                with road_cols[0]:
                    create_extra_details["施工内容"] = st.selectbox(
                        "施工内容",
                        ["道路拡幅", "線形改良", "交差点改良", "舗装補修", "橋梁補修", "道路復旧"],
                    )
                    create_extra_details["施工延長"] = st.number_input(
                        "施工延長(m)",
                        min_value=1,
                        max_value=5000,
                        value=250,
                        step=10,
                    )
                    create_extra_details["道路種別"] = st.selectbox(
                        "道路種別",
                        ["市道", "県道", "国道"],
                    )
                with road_cols[1]:
                    create_extra_details["道路幅員_前"] = st.selectbox(
                        "道路幅員(前)",
                        ["4.0m", "5.5m", "6.0m", "7.0m"],
                    )
                    create_extra_details["道路幅員_後"] = st.selectbox(
                        "道路幅員(後)",
                        ["5.5m", "7.0m", "8.5m", "9.0m"],
                    )
                    create_extra_details["舗装構成"] = st.selectbox(
                        "舗装構成",
                        ["As舗装", "表層", "基層", "路盤"],
                    )
                create_extra_details["歩道"] = st.selectbox(
                    "歩道",
                    ["両側新設", "片側新設", "既設利用", "なし"],
                )
                create_extra_details["区画線"] = st.selectbox(
                    "区画線",
                    ["施工予定", "施工済み", "一部施工予定"],
                )
        else:
            restriction_cols = st.columns(2)
            with restriction_cols[0]:
                create_extra_details = {
                    "規制理由": st.selectbox(
                        "規制理由",
                        ["災害復旧", "道路損傷", "安全確保", "緊急点検", "仮設撤去"],
                    ),
                    "規制時間帯": st.selectbox(
                        "規制時間帯",
                        ["終日", "昼間", "夜間", "片側交互時間帯あり"],
                    ),
                }
            with restriction_cols[1]:
                create_extra_details["交通誘導員"] = st.selectbox(
                    "交通誘導員",
                    ["配置あり", "配置なし", "必要時配置"],
                )
                create_extra_details["許可状況"] = st.selectbox(
                    "許可状況",
                    ["申請予定", "申請中", "許可済み"],
                )

        create_date_cols = st.columns(2)
        with create_date_cols[0]:
            create_start = st.date_input("開始日", value=default_period_start, key="create_start")
        with create_date_cols[1]:
            create_end = st.date_input("終了日", value=default_period_end, key="create_end")

        create_contractor = st.text_input(
            "施工者",
            value="" if contractor_filter == "すべて" else contractor_filter,
            placeholder="例: A建設",
        )
        create_progress = st.number_input(
            "進捗率",
            min_value=0,
            max_value=100,
            value=0,
            step=1,
        )
        create_note = st.text_area("備考", value="", height=90)

        create_submitted = st.form_submit_button("作成", type="primary", use_container_width=True)
        if create_submitted:
            if not create_name.strip():
                st.error("工事名 / 規制名を入力してください。")
            elif not create_contractor.strip():
                st.error("施工者を入力してください。")
            elif pd.to_datetime(create_start) > pd.to_datetime(create_end):
                st.error("開始日は終了日以前にしてください。")
            else:
                created_id = create_map_item(
                    item_kind=create_kind,
                    district=create_district,
                    name=create_name.strip(),
                    work_type=create_work_type,
                    restriction_type=create_restriction_type,
                    start_date=create_start,
                    end_date=create_end,
                    contractor=create_contractor.strip(),
                    progress=create_progress,
                    note=create_note.strip(),
                    extra_details=create_extra_details,
                )
                st.session_state["selected_restriction_id"] = created_id
                st.session_state["edit_dialog_id"] = created_id
                st.success(f"{created_id} を作成しました。")
                st.rerun()


# GeoJSON load
geojson_data = load_geojson()

all_features = geojson_data["features"]

geojson_data, filtered_features = apply_filters(
    geojson_data=geojson_data,
    restriction_dict=restriction_dict,
    period_start=period_start,
    period_end=period_end,
    show_road_closure=True,
    show_road_restriction=True,
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
visual_restriction_counts = restriction_counts.astype(str).apply(get_restriction_visual_type)

road_closure_count = int((visual_restriction_counts == "通行止め").sum())
road_restriction_count = int((visual_restriction_counts == "道路規制").sum())
work_type_counts = pd.Series(
    [
        str(feature.get("properties", {}).get("工事種別", "")).strip()
        for feature in filtered_features
    ]
)
delayed_count = sum(
    1
    for feature in filtered_features
    if parse_progress(feature.get("properties", {}).get("予定進捗率"))
    > parse_progress(feature.get("properties", {}).get("進捗率"))
)
work_type_count_html = "".join(
    f"<span>{work_type}</span><strong>{int((work_type_counts == work_type).sum())}</strong>"
    for work_type in WORK_TYPE_COLORS
    if int((work_type_counts == work_type).sum()) > 0
)
detour_routes = build_sample_detour_routes(all_features)

m = folium.Map(
    location=DEFAULT_LOCATION,
    zoom_start=DEFAULT_ZOOM,
    tiles=None,
    width="100%",
    height="850px",
)
m.add_child(MapViewPersistence(m))

for map_style_name, map_style in MAP_STYLES.items():
    folium.TileLayer(
        tiles=map_style["url"],
        attr=map_style["attr"],
        name=map_style_name,
        overlay=False,
        control=True,
        show=map_style_name == "淡色地図",
    ).add_to(m)

if len(geojson_data["features"]) > 0:
    prepare_map_properties(geojson_data["features"])

    layer_groups = []
    restriction_features = [
        feature
        for feature in geojson_data["features"]
        if not str(feature.get("properties", {}).get("工事種別", "")).strip()
    ]
    if restriction_features:
        layer_groups.append(("通行止め・道路規制", restriction_features))

    for work_type in WORK_TYPE_COLORS:
        work_features = [
            feature
            for feature in geojson_data["features"]
            if str(feature.get("properties", {}).get("工事種別", "")).strip() == work_type
        ]
        if work_features:
            layer_groups.append((work_type, work_features))

    for layer_name, layer_features in layer_groups:
        layer = folium.GeoJson(
            {
                "type": "FeatureCollection",
                "features": layer_features,
            },
            name=layer_name,
            style_function=lambda feature: style_by_restriction(
                feature,
                st.session_state.get("selected_restriction_id")
            ),
        ).add_to(m)
        m.add_child(FeatureInfoBinder(layer))

else:
    st.warning("この条件に該当する規制区間はありません。")

if detour_routes:
    detour_layer = folium.FeatureGroup(name="迂回路", show=True)
    for route in detour_routes:
        route_popup = f"""
        <div style="font-size:13px; line-height:1.6; min-width:180px;">
            <div style="font-weight:700; color:#1b5e20;">{route["name"]}</div>
            <div>表示確認用のサンプル迂回路</div>
        </div>
        """
        folium.PolyLine(
            locations=route["locations"],
            color="#ffffff",
            weight=11,
            opacity=0.95,
        ).add_to(detour_layer)
        folium.PolyLine(
            locations=route["locations"],
            color=DETOUR_COLOR,
            weight=7,
            opacity=1.0,
            tooltip=route["name"],
            popup=folium.Popup(route_popup, max_width=260),
        ).add_to(detour_layer)
    detour_layer.add_to(m)

visible_complaints = [
    complaint
    for complaint in COMPLAINTS
    if complaint["district"] in selected_districts
]

if visible_complaints:
    complaint_layer = folium.FeatureGroup(name="苦情", show=True)
    for complaint in visible_complaints:
        complaint_color = COMPLAINT_STATUS_COLORS.get(complaint["status"], "#7c3aed")
        folium.Marker(
            location=complaint["location"],
            tooltip=folium.Tooltip(make_complaint_tooltip(complaint), sticky=True),
            popup=folium.Popup(make_complaint_tooltip(complaint), max_width=360),
            icon=folium.DivIcon(
                html=f"""
                <div style="
                    width:28px;
                    height:28px;
                    border-radius:50%;
                    background:{complaint_color};
                    color:white;
                    border:3px solid white;
                    box-shadow:0 2px 8px rgba(0,0,0,0.35);
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    font-weight:800;
                    font-size:18px;
                    line-height:1;
                ">!</div>
                """
            ),
        ).add_to(complaint_layer)
    complaint_layer.add_to(m)

map_summary_html = f"""
<div style="
    position: fixed;
    right: 16px;
    top: 330px;
    z-index: 9999;
    width: 254px;
    box-sizing: border-box;
    max-height: calc(100vh - 360px);
    overflow-y: auto;
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
        {work_type_count_html}
        <span>通行止め</span><strong>{road_closure_count}</strong>
        <span>道路規制</span><strong>{road_restriction_count}</strong>
        <span>遅延</span><strong>{delayed_count}</strong>
        <span>苦情</span><strong>{len(visible_complaints)}</strong>
    </div>
    <div style="height:1px; background:#e5e7eb; margin:8px 0;"></div>
    <div style="font-weight:700; font-size:13px; margin-bottom:6px;">🧭 凡例</div>
    <div style="display:grid; gap:4px;">
        <div><span style="display:inline-block;width:26px;height:5px;background:{RESTRICTION_RED};margin-right:8px;vertical-align:middle;"></span>通行止め</div>
        <div><span style="display:inline-block;width:26px;border-top:5px dotted {RESTRICTION_RED};margin-right:8px;vertical-align:middle;"></span>道路規制</div>
        {''.join(
            f'<div><span style="display:inline-block;width:26px;height:5px;background:{color};margin-right:8px;vertical-align:middle;"></span>{work_type}</div>'
            for work_type, color in WORK_TYPE_COLORS.items()
            if int((work_type_counts == work_type).sum()) > 0
        )}
        <div><span style="display:inline-block;width:26px;height:5px;background:#2e7d32;margin-right:8px;vertical-align:middle;"></span>迂回路</div>
        <div><span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:#d32f2f;color:white;text-align:center;line-height:18px;font-weight:800;margin-right:8px;vertical-align:middle;">!</span>苦情 未対応</div>
        <div><span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:#1b5e20;color:white;text-align:center;line-height:18px;font-weight:800;margin-right:8px;vertical-align:middle;">!</span>苦情 対応済み</div>
        <div><span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:#7c3aed;color:white;text-align:center;line-height:18px;font-weight:800;margin-right:8px;vertical-align:middle;">!</span>苦情 対応中</div>
    </div>
</div>
"""
m.get_root().html.add_child(folium.Element(map_summary_html))

map_control_alignment_html = """
<style>
    .leaflet-top.leaflet-right {
        right: 16px;
    }

    .leaflet-control-layers {
        width: 254px;
        box-sizing: border-box;
    }

    .leaflet-control-layers-expanded {
        width: 254px;
        box-sizing: border-box;
    }
</style>
"""
m.get_root().html.add_child(folium.Element(map_control_alignment_html))

map_settings_label_html = """
<div style="
    position: fixed;
    top: 10px;
    right: 16px;
    z-index: 9999;
    background: rgba(255,255,255,0.94);
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 4px 8px;
    color: #1f2937;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 12px;
    font-weight: 700;
">
    地図設定
</div>
"""
m.get_root().html.add_child(folium.Element(map_settings_label_html))

folium.LayerControl(position="topright", collapsed=False).add_to(m)

map_output = st_folium(
    m,
    width=None,
    height=850,
    returned_objects=["last_active_drawing", "last_clicked"],
    key="main_map",
)

if isinstance(map_output, dict):
    clicked_feature = map_output.get("last_active_drawing")
    clicked_props = clicked_feature.get("properties", {}) if isinstance(clicked_feature, dict) else {}
    clicked_id = str(clicked_props.get("規制ID", "")).strip()
    clicked_point = map_output.get("last_clicked") if isinstance(map_output.get("last_clicked"), dict) else {}
    click_signature = (
        clicked_id,
        clicked_point.get("lat"),
        clicked_point.get("lng"),
    )
    if clicked_id and clicked_id in item_ids and click_signature != st.session_state.get("last_clicked_item"):
        st.session_state["selected_restriction_id"] = clicked_id
        st.session_state["edit_dialog_id"] = clicked_id
        st.session_state["last_clicked_item"] = click_signature
        st.rerun()

dialog_item_id = st.session_state.get("edit_dialog_id")
if dialog_item_id and dialog_item_id not in item_ids:
    st.session_state["edit_dialog_id"] = None
