RESTRICTION_RED = "#d32f2f"

WORK_TYPE_COLORS = {
    "下水道工事": "#1976d2",
    "排水工事": "#6b7280",
    "舗装工事": "#f59e0b",
    "橋梁工事": "#7c3aed",
    "道路復旧工事": "#00897b",
}


def get_restriction_visual_type(restriction):
    restriction = str(restriction or "").strip()
    if "全面" in restriction or restriction == "通行止め":
        return "通行止め"
    return "道路規制"


def get_work_type_color(work_type, default=RESTRICTION_RED):
    work_type = str(work_type or "").strip()
    return WORK_TYPE_COLORS.get(work_type, default)
