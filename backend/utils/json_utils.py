import json
import re
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_json_from_text(text: str) -> Any:
    cleaned_text = text.strip()
    cleaned_text = re.sub(r"^```json", "", cleaned_text)
    cleaned_text = re.sub(r"^```", "", cleaned_text)
    cleaned_text = re.sub(r"```$", "", cleaned_text)
    cleaned_text = cleaned_text.strip()

    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        pass

    start = cleaned_text.find("{")
    end = cleaned_text.rfind("}")

    if start != -1 and end != -1 and end > start:
        json_text = cleaned_text[start : end + 1]
        try:
            return json.loads(json_text)
        except json.JSONDecodeError as error:
            raise ValueError(f"JSON 解析失败：{error}\n\n模型原始输出：\n{cleaned_text}") from error

    raise ValueError(f"未能从模型输出中找到合法 JSON：\n{cleaned_text}")
