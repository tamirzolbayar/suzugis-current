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

    st.subheader("🚧 規制種別")

    show_full_closure = st.checkbox("全面通行止め", value=True)
    show_alternate = st.checkbox("片側交互通行", value=True)
    show_lane = st.checkbox("車線規制", value=True)
    show_completed = st.checkbox("完了", value=True)
    show_complaints = st.checkbox("苦情を表示", value=True)
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
    period_start=period_start,
    period_end=period_end,
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
delayed_count = sum(
    1
    for feature in filtered_features
    if parse_progress(feature.get("properties", {}).get("予定進捗率"))
    > parse_progress(feature.get("properties", {}).get("進捗率"))
)
detour_routes = build_sample_detour_routes(all_features)

m = folium.Map(
    location=DEFAULT_LOCATION,
    zoom_start=DEFAULT_ZOOM,
    tiles=None,
    width="100%",
    height="850px",
)

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
    if show_complaints and complaint["district"] in selected_districts
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
        <span>遅延</span><strong>{delayed_count}</strong>
        <span>迂回路</span><strong>{len(detour_routes)}</strong>
        <span>苦情</span><strong>{len(visible_complaints)}</strong>
    </div>
    <div style="height:1px; background:#e5e7eb; margin:8px 0;"></div>
    <div style="font-weight:700; font-size:13px; margin-bottom:6px;">🧭 凡例</div>
    <div style="display:grid; gap:4px;">
        <div><span style="display:inline-block;width:26px;height:5px;background:#d32f2f;margin-right:8px;vertical-align:middle;"></span>全面通行止め</div>
        <div><span style="display:inline-block;width:26px;height:5px;background:#f57c00;margin-right:8px;vertical-align:middle;"></span>片側交互通行</div>
        <div><span style="display:inline-block;width:26px;height:5px;background:#fbc02d;margin-right:8px;vertical-align:middle;"></span>車線規制</div>
        <div><span style="display:inline-block;width:26px;height:5px;background:#1976d2;margin-right:8px;vertical-align:middle;"></span>完了</div>
        <div><span style="display:inline-block;width:26px;height:5px;background:#2e7d32;margin-right:8px;vertical-align:middle;"></span>迂回路</div>
        <div><span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:#d32f2f;color:white;text-align:center;line-height:18px;font-weight:800;margin-right:8px;vertical-align:middle;">!</span>苦情 未対応</div>
        <div><span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:#1b5e20;color:white;text-align:center;line-height:18px;font-weight:800;margin-right:8px;vertical-align:middle;">!</span>苦情 対応済み</div>
        <div><span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:#7c3aed;color:white;text-align:center;line-height:18px;font-weight:800;margin-right:8px;vertical-align:middle;">!</span>苦情 対応中</div>
    </div>
</div>
"""
m.get_root().html.add_child(folium.Element(map_summary_html))

map_settings_label_html = """
<div style="
    position: fixed;
    top: 10px;
    right: 58px;
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

st_folium(m, width=1500, height=850)
