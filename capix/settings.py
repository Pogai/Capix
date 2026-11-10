# -*- coding: utf-8 -*-
"""设置持久化（JSON）。

存储位置：优先 exe/项目同目录 settings.json；
不可写时回退 %LOCALAPPDATA%\\capix\\settings.json。
"""

import json
import os

from . import paths
from .logsetup import log

_FILENAME = "settings.json"

# 可配置项与取值范围
DEFAULTS = {
    "max_shots": 20,       # 单次会话最大截图张数
}
MAX_SHOTS_LIMIT = 20       # 硬上限
MIN_SHOTS = 1


def _local_path():
    return os.path.join(paths.base_dir(), _FILENAME)


def _fallback_path():
    root = os.environ.get("LOCALAPPDATA") or os.getcwd()
    return os.path.join(root, "capix", _FILENAME)


def _load_from(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        pass
    except Exception as exc:
        log("[settings] 读取失败 %s: %r" % (path, exc))
    return None


def load():
    """读设置（不存在/损坏则返回默认值副本）。"""
    for path in (_local_path(), _fallback_path()):
        data = _load_from(path)
        if data is not None:
            merged = dict(DEFAULTS)
            merged.update({k: v for k, v in data.items() if k in DEFAULTS})
            merged["max_shots"] = _clamp(merged["max_shots"])
            return merged
    return dict(DEFAULTS)


def _clamp(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return DEFAULTS["max_shots"]
    return max(MIN_SHOTS, min(MAX_SHOTS_LIMIT, v))


def save(settings):
    """写设置：先写同目录，失败回退 LOCALAPPDATA。返回实际写入路径或 None。"""
    payload = dict(DEFAULTS)
    payload.update({k: v for k, v in settings.items() if k in DEFAULTS})
    payload["max_shots"] = _clamp(payload["max_shots"])

    try:
        p = _local_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return p
    except Exception as exc:
        log("[settings] 写入同目录失败: %r，回退 LOCALAPPDATA" % exc)
    try:
        p = _fallback_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return p
    except Exception as exc:
        log("[settings] 写入失败: %r" % exc)
        return None


def get_path():
    for p in (_local_path(), _fallback_path()):
        if os.path.exists(p):
            return p
    return _local_path()