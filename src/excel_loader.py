import pandas as pd
from pathlib import Path
from datetime import datetime
import shutil

def load_excel(excel_path):
    df = pd.read_excel(excel_path)

    df.columns = df.columns.str.strip()
    if "工事種別" not in df.columns:
        insert_at = df.columns.get_loc("工事名") + 1 if "工事名" in df.columns else len(df.columns)
        df.insert(insert_at, "工事種別", "")

    for column in df.select_dtypes(include="object").columns:
        df[column] = df[column].fillna("").astype(str).str.strip()

    df["開始日"] = pd.to_datetime(df["開始日"])
    df["終了日"] = pd.to_datetime(df["終了日"])

    restriction_dict = df.set_index("規制ID").to_dict("index")

    return df, restriction_dict


def save_excel(df, excel_path):
    excel_path = Path(excel_path)

    backup_dir = excel_path.parent.parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{excel_path.stem}_{timestamp}{excel_path.suffix}"

    if excel_path.exists():
        shutil.copy2(excel_path, backup_path)

    df.to_excel(excel_path, index=False)

    return backup_path
