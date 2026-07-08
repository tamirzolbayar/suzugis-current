from road_styles import RESTRICTION_RED, get_work_type_color

ROAD_CENTERLINE_TYPES = {
    "1": "通常部",
    "2": "庭園路",
    "3": "徒歩道",
    "4": "石段",
    "5": "不明",
}

ROAD_CATEGORY_TYPES = {
    "1": "国道",
    "2": "都道府県道",
    "3": "市区町村道等",
    "4": "高速自動車国道等",
    "5": "その他",
    "6": "不明",
}

ROAD_STATE_TYPES = {
    "1": "通常部",
    "2": "橋・高架",
    "3": "トンネル",
    "4": "雪囲い",
    "5": "建設中",
    "6": "その他",
    "7": "不明",
}

ROAD_WIDTH_TYPES = {
    "1": "3m未満",
    "2": "3m-5.5m未満",
    "3": "5.5m-13m未満",
    "4": "13m-19.5m未満",
    "5": "19.5m以上",
    "6": "不明",
}


def decode_code(mapping, value):
    code = str(value).strip()
    return mapping.get(code, f"不明({code})")


def make_popup_html(props, permit_link_html="未登録"):

    actual = int(str(props.get("進捗率", "0")).replace("%", ""))
    planned = int(str(props.get("予定進捗率", "0")).replace("%", ""))

    work_type = str(props.get("工事種別", "")).strip()
    badge_label = work_type or str(props.get("規制種別", "")).strip()
    badge = get_work_type_color(work_type, RESTRICTION_RED) if work_type else RESTRICTION_RED

    return f"""
    <div style="
        font-size:13px;
        width:320px;
        line-height:1.45;
        overflow-wrap:anywhere;
        word-break:break-word;
    ">

        <div style="
            margin:0 0 7px 0;
            font-size:14px;
            line-height:1.35;
            font-weight:700;
            color:#222;
        ">
            🚧 {props.get("工事名","")}
        </div>

        <span style="
            background:{badge};
            color:white;
            padding:4px 10px;
            border-radius:20px;
            font-size:12px;
            font-weight:bold;
        ">
            {badge_label}
        </span>

        <span style="float:right;color:#666;">
            {props.get("規制ID","")}
        </span>

        <br>

        <hr style="
            border:none;
            border-top:1px solid #ddd;
            margin:10px 0;
        ">

        <b>期間:</b> {props.get("開始日","")} ～ {props.get("終了日","")}<br>
        <b>施工者:</b> {props.get("施工者","")}<br>
        <b>道路使用許可:</b> {permit_link_html}<br><br>

        <b>道路中心線:</b> {decode_code(ROAD_CENTERLINE_TYPES, props.get("N13_002", ""))}<br>
        <b>道路分類:</b> {decode_code(ROAD_CATEGORY_TYPES, props.get("N13_003", ""))}<br>
        <b>道路状態:</b> {decode_code(ROAD_STATE_TYPES, props.get("N13_004", ""))}<br>
        <b>幅員:</b> {decode_code(ROAD_WIDTH_TYPES, props.get("N13_006", ""))}<br><br>

        <b>実績進捗:</b> {actual}%<br>
        <div style="
            background:#eee;
            height:14px;
            border-radius:999px;
            overflow:hidden;
        ">
            <div style="
                background:#4caf50;
                width:{actual}%;
                height:14px;
                border-radius:999px;
            "></div>
        </div>

        <br>

        <b>予定進捗:</b> {planned}%<br>
    <div style="
        background:#eee;
        height:12px;
        border-radius:6px;
        overflow:hidden;
    ">
        <div style="
            background:#2196f3;
            width:{planned}%;
            height:14px;
            border-radius:999px;
        "></div>
     </div>

        <br>

        <b>備考:</b> {props.get("備考","")}

    </div>
    """
