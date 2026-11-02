"""위젯 설정(볼트 밖): %APPDATA%\\job-compass-widget\\settings.json. 볼트에는 아무것도 쓰지 않는다."""
import json
import os
from pathlib import Path

DEFAULTS = {"vault": "", "floating": {"visible": True, "x": None, "y": None}, "notified": {}}


def config_dir():
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "job-compass-widget"


def load(path=None):
    p = Path(path) if path else config_dir() / "settings.json"
    data = json.loads(json.dumps(DEFAULTS))
    try:
        saved = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            for k, v in saved.items():
                if isinstance(v, dict) and isinstance(data.get(k), dict):
                    data[k].update(v)
                else:
                    data[k] = v
    except (OSError, ValueError):
        pass
    return data


def save(data, path=None):
    p = Path(path) if path else config_dir() / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
