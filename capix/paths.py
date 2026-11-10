# -*- coding: utf-8 -*-
"""路径工具：兼容开发运行与 PyInstaller 打包(exe)运行。

- resource_path：读取随包分发的资源（打包后在 _MEIPASS 临时目录）
- base_dir：exe 所在目录（打包后）或项目根目录（开发）
- log_dir / output_dir：优先放在 exe 同目录，不可写时回退到 LOCALAPPDATA
"""

import os
import sys
import tempfile


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def base_dir():
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    # paths.py 位于 <root>/capix/paths.py
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(rel):
    """获取资源文件绝对路径（打包后从 _MEIPASS 取）。"""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = base_dir()
    return os.path.join(base, rel)


def _writable_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".w_probe")
        with open(probe, "wb") as f:
            f.write(b"ok")
        os.remove(probe)
        return True
    except Exception:
        return False


def _fallback_dir(name):
    root = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    path = os.path.join(root, "capix", name)
    os.makedirs(path, exist_ok=True)
    return path


def log_dir():
    cand = os.path.join(base_dir(), "logs")
    return cand if _writable_dir(cand) else _fallback_dir("logs")


def output_dir():
    cand = os.path.join(base_dir(), "output")
    return cand if _writable_dir(cand) else _fallback_dir("output")