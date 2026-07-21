from road_styles import get_restriction_visual_type, get_work_type_color


def style_by_restriction(feature, selected_id=None):
    props = feature.get("properties", {})
    is_candidate = str(props.get("項目状態", "")).strip() == "候補"
    restriction = str(props.get("規制種別", "")).strip()
    work_type = str(props.get("工事種別", "")).strip()
    visual_type = get_restriction_visual_type(restriction)
    color = get_work_type_color(work_type)

    if is_candidate:
        return {
            "color": "#475569",
            "weight": 4,
            "opacity": 0.78,
        }

    if props.get("規制ID") == selected_id:
        return {
            "color": color,
            "weight": 10,
            "opacity": 1.0,
        }

    style = {
        "color": color,
        "weight": 6,
        "opacity": 0.9,
    }
    if not work_type and visual_type == "道路規制":
        style["dashArray"] = "2, 9"
    return style


def highlight_by_restriction(feature):
    props = feature.get("properties", {})
    is_candidate = str(props.get("項目状態", "")).strip() == "候補"
    restriction = str(props.get("規制種別", "")).strip()
    work_type = str(props.get("工事種別", "")).strip()
    visual_type = get_restriction_visual_type(restriction)

    if is_candidate:
        return {
            "color": "#2563eb",
            "weight": 9,
            "opacity": 1.0,
        }

    style = {
        "color": "#facc15",
        "weight": 11,
        "opacity": 1.0,
    }
    if not work_type and visual_type == "道路規制":
        style["dashArray"] = "2, 9"
    return style
