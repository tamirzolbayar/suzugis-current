from datetime import datetime
from html import escape

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


def record_seed(props):
    raw_id = str(props.get("規制ID", "")).strip()
    digits = "".join(char for char in raw_id if char.isdigit())
    if digits:
        return int(digits)
    return sum(ord(char) for char in raw_id)


def pick_option(options, seed, offset=0):
    return options[(seed + offset) % len(options)]


def detail_value(props, key, fallback):
    value = props.get(key, "")
    if value is None:
        return fallback
    if isinstance(value, float) and value != value:
        return fallback
    value = str(value).strip()
    return value if value and value.lower() != "nan" else fallback


def display_value(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    value = str(value).strip()
    if value.endswith(".0"):
        head = value[:-2]
        if head.replace("-", "", 1).isdigit():
            return head
    return value


def restriction_details(props):
    rows = []
    for label, key in [
        ("規制理由", "規制理由"),
        ("規制時間帯", "規制時間帯"),
        ("交通誘導員", "交通誘導員"),
        ("許可状況", "許可状況"),
    ]:
        value = detail_value(props, key, "")
        if value:
            rows.append(f"<b>{label}:</b> {value}<br>")
    return "".join(rows)


def water_details(props, work_type):
    seed = record_seed(props)
    water_kind = "上水道"
    if "下水道" in work_type:
        water_kind = "下水道"
    elif "排水" in work_type:
        water_kind = "排水"

    water_kind = detail_value(props, "管種", water_kind)
    pipe_diameter = detail_value(props, "管径", pick_option(["φ100", "φ150", "φ200", "φ250", "φ300"], seed))
    length = detail_value(props, "施工延長", 80 + (seed * 17) % 260)

    return f"""
        <b>工事種別:</b> {water_kind}<br>
        <b>管径:</b> {pipe_diameter}<br>
        <b>施工延長:</b> {length}m<br>
    """


def drainage_details(props):
    seed = record_seed(props)
    drainage_method = detail_value(props, "排水方式", pick_option(["側溝", "暗渠", "開水路", "集水桝連結"], seed))
    length = detail_value(props, "施工延長", 60 + (seed * 19) % 260)
    gutter_size = detail_value(props, "側溝サイズ", pick_option(["300×300", "400×400", "500×500", "600×600"], seed, 1))
    catch_basins = detail_value(props, "集水桝", 2 + (seed * 3) % 14)
    crossing_pipes = detail_value(props, "横断管", 1 + (seed * 2) % 7)
    drainage_direction = detail_value(props, "排水方向", pick_option(["海側", "山側", "既設水路側", "幹線側溝側"], seed, 2))
    capacity_status = detail_value(props, "排水能力", pick_option(["改善予定", "改善中", "暫定改善済み", "能力確認中"], seed, 3))

    return f"""
        <b>排水方式:</b> {drainage_method}<br>
        <b>施工延長:</b> {length}m<br>
        <b>側溝サイズ:</b> {gutter_size}<br>
        <b>集水桝:</b> {catch_basins}基<br>
        <b>横断管:</b> {crossing_pipes}箇所<br>
        <b>排水方向:</b> {drainage_direction}<br>
        <b>排水能力:</b> {capacity_status}<br>
    """


def road_details(props, work_type):
    seed = record_seed(props)
    road_type = detail_value(props, "道路種別", pick_option(["市道", "県道", "国道"], seed))
    road_width_pairs = [
        ("4.0m", "5.5m"),
        ("5.5m", "7.0m"),
        ("6.0m", "8.5m"),
        ("7.0m", "9.0m"),
    ]
    before_width, after_width = pick_option(road_width_pairs, seed, 1)
    before_width = detail_value(props, "道路幅員_前", before_width)
    after_width = detail_value(props, "道路幅員_後", after_width)
    if "舗装" in work_type:
        content_options = ["舗装補修", "路面切削", "表層打換え", "段差解消"]
    elif "橋梁" in work_type:
        content_options = ["橋梁補修", "高欄補修", "伸縮装置補修", "床版補修"]
    elif "道路復旧" in work_type:
        content_options = ["道路復旧", "路肩復旧", "路盤復旧", "法面復旧"]
    else:
        content_options = ["道路拡幅", "線形改良", "交差点改良", "路肩復旧"]
    construction_content = detail_value(props, "施工内容", pick_option(content_options, seed, 2))
    pavement = detail_value(props, "舗装構成", pick_option(["As舗装", "表層", "基層", "路盤"], seed, 3))
    sidewalk = detail_value(props, "歩道", pick_option(["両側新設", "片側新設", "既設利用", "なし"], seed, 4))
    road_marking = detail_value(props, "区画線", pick_option(["施工予定", "施工済み", "一部施工予定"], seed, 5))
    length = detail_value(props, "施工延長", 120 + (seed * 23) % 880)

    return f"""
        <b>施工内容:</b> {construction_content}<br>
        <b>施工延長:</b> {length}m<br>
        <b>道路幅員:</b> {before_width} → {after_width}<br>
        <b>道路種別:</b> {road_type}<br>
        <b>舗装構成:</b> {pavement}<br>
        <b>歩道:</b> {sidewalk}<br>
        <b>区画線:</b> {road_marking}<br>
    """


def construction_details(props, work_type):
    if "排水" in work_type:
        return drainage_details(props)
    if "下水道" in work_type or "水道" in work_type:
        return water_details(props, work_type)
    return road_details(props, work_type)


def popup_shell(title, badge_label, badge, body_html):
    title = display_value(title) or "名称未設定"
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

        <br>

        <hr style="
            border:none;
            border-top:1px solid #ddd;
            margin:10px 0;
        ">

        {body_html}
    </div>
    """


def wrapped_note_html(note):
    return f"""
        <div style="
            margin-top:6px;
            max-width:100%;
            white-space:normal;
            overflow-wrap:anywhere;
            word-break:break-word;
            line-break:anywhere;
        ">
            <b>備考:</b><br>
            <span>{escape(str(note or ""))}</span>
        </div>
    """


def real_construction_source_html(props):
    if str(props.get("実データ", "")).strip().lower() != "true":
        return ""

    is_candidate = str(props.get("項目状態", "")).strip() == "候補"
    rows = []
    field_pairs = [
        ("地区", "重点地区"),
        ("査定番号", "査定番号"),
        ("箇所名", "箇所名"),
        ("道路名称", "道路名称"),
        ("復旧延長", "復旧延長_m"),
        ("幅員", "幅員_m"),
    ]
    if is_candidate:
        field_pairs.insert(1, ("工事区分", "工事区分"))

    for label, key in field_pairs:
        value = props.get(key, "")
        if value is None:
            continue
        value = display_value(value)
        if not value or value.lower() == "nan":
            continue
        suffix = "m" if key in ("復旧延長_m", "幅員_m") and not value.endswith("m") else ""
        rows.append(f"<b>{label}:</b> {escape(value)}{suffix}<br>")

    return "".join(rows) + ("<br>" if rows else "")


def make_construction_popup_html(props, actual, planned, work_type):
    is_real_data = str(props.get("実データ", "")).strip().lower() == "true"
    is_candidate = str(props.get("項目状態", "")).strip() == "候補"
    start_date = format_japanese_date(props.get("開始日", ""))
    end_date = format_japanese_date(props.get("終了日", ""))
    period = "未定" if is_candidate else f"{start_date}～{end_date}"
    display_work_type = display_value(props.get("工事区分", "")) if is_real_data else work_type
    display_work_type = display_work_type or work_type
    source_html = real_construction_source_html(props)
    common_html = (
        source_html
        if source_html
        else f"""
        <b>地区:</b> {props.get("重点地区","")}<br>
        <b>工事名:</b> {props.get("工事名","")}<br>
        """
    )
    body_html = f"""
        {common_html}
        <b>施工者:</b> {props.get("施工者","")}<br>
        <b>工事期間:</b> {period}<br><br>

        {make_progress_html(actual, planned)}

        <br>

        {wrapped_note_html(props.get("備考",""))}
    """

    return popup_shell(
        props.get("工事名", ""),
        display_work_type,
        get_work_type_color(work_type, RESTRICTION_RED),
        body_html,
    )


def make_candidate_popup_html(props):
    title = (
        props.get("道路名称", "")
        or props.get("工事名", "")
        or props.get("箇所名", "")
        or "名称未設定"
    )
    body_html = f"""
        {real_construction_source_html(props)}
        <b>状態:</b> 未着手・施工候補<br>
    """

    return popup_shell(
        title,
        "道路復旧工事（未着手）",
        "#475569",
        body_html,
    )


def make_restriction_popup_html(props, permit_link_html, actual, planned):
    body_html = f"""
        <b>地区:</b> {props.get("重点地区","")}<br>
        <b>期間:</b> {props.get("開始日","")} ～ {props.get("終了日","")}<br>
        <b>施工者:</b> {props.get("施工者","")}<br>
        <b>道路使用許可:</b> {permit_link_html}<br><br>

        {restriction_details(props)}

        <b>道路中心線:</b> {decode_code(ROAD_CENTERLINE_TYPES, props.get("N13_002", ""))}<br>
        <b>道路分類:</b> {decode_code(ROAD_CATEGORY_TYPES, props.get("N13_003", ""))}<br>
        <b>道路状態:</b> {decode_code(ROAD_STATE_TYPES, props.get("N13_004", ""))}<br>
        <b>幅員:</b> {decode_code(ROAD_WIDTH_TYPES, props.get("N13_006", ""))}<br><br>

        {make_progress_html(actual, planned)}

        <br>

        {wrapped_note_html(props.get("備考",""))}
    """

    return popup_shell(
        props.get("工事名", ""),
        str(props.get("規制種別", "")).strip(),
        RESTRICTION_RED,
        body_html,
    )


def make_popup_html(props, permit_link_html="未登録"):
    actual = int(str(props.get("進捗率", "0")).replace("%", ""))
    planned = int(str(props.get("予定進捗率", "0")).replace("%", ""))

    if str(props.get("項目状態", "")).strip() == "候補":
        return make_candidate_popup_html(props)

    work_type = str(props.get("工事種別", "")).strip()

    if work_type:
        return make_construction_popup_html(props, actual, planned, work_type)

    return make_restriction_popup_html(props, permit_link_html, actual, planned)
