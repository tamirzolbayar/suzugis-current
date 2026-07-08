from datetime import datetime

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


def format_japanese_date(value):
    if value in (None, ""):
        return ""

    if isinstance(value, datetime):
        date_value = value
    else:
        try:
            date_value = datetime.fromisoformat(str(value).split(" ")[0])
        except ValueError:
            return str(value)

    return f"{date_value.year}年{date_value.month}月{date_value.day}日"


def make_progress_html(actual, planned):
    return f"""
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
    """


def construction_id(props):
    raw_id = str(props.get("規制ID", "")).strip()
    digits = "".join(char for char in raw_id if char.isdigit())
    return f"C-{int(digits):03d}" if digits else raw_id


def water_details(work_type):
    water_kind = "上水道"
    if "下水道" in work_type:
        water_kind = "下水道"
    elif "排水" in work_type:
        water_kind = "排水"

    return f"""
        <b>工事種別:</b> {water_kind}<br>
        <b>管径:</b> φ150<br>
        <b>施工延長:</b> 185m<br>
    """


def road_details(work_type):
    road_type = "市道"
    if "橋梁" in work_type:
        road_type = "県道"
    elif "道路復旧" in work_type:
        road_type = "国道"

    return f"""
        <b>施工内容:</b> 道路拡幅, 線形改良, 交差点改良<br>
        <b>施工延長:</b> 850m<br>
        <b>道路幅員:</b> 6.0m → 8.5m<br>
        <b>道路種別:</b> {road_type}<br>
        <b>舗装構成:</b> As舗装 表層・基層・路盤<br>
        <b>歩道:</b> 両側新設<br>
        <b>区画線:</b> 施工予定<br>
    """


def construction_details(work_type):
    if "下水道" in work_type or "排水" in work_type or "水道" in work_type:
        return water_details(work_type)
    return road_details(work_type)


def popup_shell(title, badge_label, badge, side_id, body_html):
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
            🚧 {title}
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
            {side_id}
        </span>

        <br>

        <hr style="
            border:none;
            border-top:1px solid #ddd;
            margin:10px 0;
        ">

        {body_html}
    </div>
    """


def make_construction_popup_html(props, actual, planned, work_type):
    start_date = format_japanese_date(props.get("開始日", ""))
    end_date = format_japanese_date(props.get("終了日", ""))
    body_html = f"""
        <b>工事ID:</b> {construction_id(props)}<br>
        <b>工事名:</b> {props.get("工事名","")}<br>
        <b>施工者:</b> {props.get("施工者","")}<br>
        <b>工事期間:</b> {start_date}～{end_date}<br><br>

        {construction_details(work_type)}

        <br>

        {make_progress_html(actual, planned)}

        <br>

        <b>備考:</b> {props.get("備考","")}
    """

    return popup_shell(
        props.get("工事名", ""),
        work_type,
        get_work_type_color(work_type, RESTRICTION_RED),
        construction_id(props),
        body_html,
    )


def make_restriction_popup_html(props, permit_link_html, actual, planned):
    body_html = f"""
        <b>期間:</b> {props.get("開始日","")} ～ {props.get("終了日","")}<br>
        <b>施工者:</b> {props.get("施工者","")}<br>
        <b>道路使用許可:</b> {permit_link_html}<br><br>

        <b>道路中心線:</b> {decode_code(ROAD_CENTERLINE_TYPES, props.get("N13_002", ""))}<br>
        <b>道路分類:</b> {decode_code(ROAD_CATEGORY_TYPES, props.get("N13_003", ""))}<br>
        <b>道路状態:</b> {decode_code(ROAD_STATE_TYPES, props.get("N13_004", ""))}<br>
        <b>幅員:</b> {decode_code(ROAD_WIDTH_TYPES, props.get("N13_006", ""))}<br><br>

        {make_progress_html(actual, planned)}

        <br>

        <b>備考:</b> {props.get("備考","")}
    """

    return popup_shell(
        props.get("工事名", ""),
        str(props.get("規制種別", "")).strip(),
        RESTRICTION_RED,
        props.get("規制ID", ""),
        body_html,
    )


def make_popup_html(props, permit_link_html="未登録"):
    actual = int(str(props.get("進捗率", "0")).replace("%", ""))
    planned = int(str(props.get("予定進捗率", "0")).replace("%", ""))

    work_type = str(props.get("工事種別", "")).strip()

    if work_type:
        return make_construction_popup_html(props, actual, planned, work_type)

    return make_restriction_popup_html(props, permit_link_html, actual, planned)
