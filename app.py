# -*- coding: utf-8 -*-
"""程序入口（固定框连续截图 · 托盘后台版 · 可打包 exe）。

运行:  python app.py [输出目录]
打包:  build\\build_exe.ps1（PyInstaller，无黑框 + 自带图标 + 日志）

行为：
  - 启动后台常驻，仅托盘图标（无黑框、无窗口）。
  - 左键托盘 → 框选；右键托盘 → 菜单（开始框选 / 打开截图目录 / 打开日志目录 / 退出程序）。
  - 取景框 + 工具条：[截图]（单会话上限可设，默认 20）/ [复制]长图 / [⚙设置] / [✕]退出框选。
  - 框侧长图预览窗：随截图变多逐渐缩放；点「复制」后重新从 0 拼接。
  - 全程写日志到 logs 目录，便于问题记录与迭代。
"""

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capix import winutil, paths, logsetup      # noqa: E402
from capix.controller import Controller         # noqa: E402
from capix.gui import App                        # noqa: E402
from capix.tray import TrayIcon                  # noqa: E402
from capix import hotkey as hk                   # noqa: E402

HOTKEY_HINTS = [
    ("Ctrl + Shift + R", "开始 / 重新框选区域"),
    ("Ctrl + Shift + S", "截取当前取景框"),
    ("托盘左键", "开始框选"),
    ("托盘右键", "菜单：框选 / 目录 / 日志 / 退出"),
]

_HOTKEY_NAMES = {1: "Ctrl+Shift+S（截图）", 2: "Ctrl+Shift+R（框选）"}


def _open_dir(path):
    try:
        os.startfile(path)  # noqa: S606
        logsetup.log("打开目录: %s" % path)
    except Exception as exc:
        logsetup.error("打开目录失败 %s: %r" % (path, exc))


def main():
    winutil.enable_dpi_awareness()   # 必须在创建窗口前
    logsetup.setup()

    default_out = paths.output_dir()
    if len(sys.argv) > 1 and os.path.isdir(os.path.dirname(os.path.abspath(sys.argv[1]))):
        default_out = sys.argv[1]
    logsetup.log("截图输出目录: %s" % default_out)

    ctrl = Controller(default_out)

    root = tk.Tk()
    # 捕获 tkinter 回调中的未处理异常写入日志（无控制台时否则会静默）
    def _tk_exc(exc, val, tb):
        logsetup.error("Tk 回调异常", exc_info=(exc, val, tb))
    root.report_callback_exception = _tk_exc

    app = App(root, ctrl, HOTKEY_HINTS)

    # 回退面板也带上程序图标
    try:
        ico = paths.resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(ico):
            root.iconbitmap(ico)
    except Exception:
        pass

    # ---- 托盘（后台任务） ----
    def tray_select():
        ctrl.events.put(("request_select",))

    def tray_quit():
        ctrl.events.put(("request_quit",))

    tray = TrayIcon(
        on_select=tray_select,
        on_open_dir=lambda: _open_dir(ctrl.output_dir),
        on_open_log=lambda: _open_dir(logsetup.get_dir()),
        on_quit=tray_quit,
        on_settings=lambda: ctrl.events.put(("request_settings",)),
    )
    tray_ok = tray.start()
    logsetup.log("托盘创建: %s" % ("成功" if tray_ok else "失败，回退面板"))
    app.tray = tray
    app.tray_mode = bool(tray_ok)
    if not tray_ok:
        root.deiconify()
        ctrl.events.put(("log", "托盘创建失败，已回退为控制面板窗口"))
    else:
        tray.notify("固定框连续截图", "已在后台运行。点击托盘图标开始框选。")

    # ---- 全局热键 ----
    def hotkey_report(failures):
        if not failures:
            return
        names = ", ".join(_HOTKEY_NAMES.get(hid, "热键#%d" % hid) for hid, _m, _v in failures)
        ctrl.events.put(("error", "热键被占用：%s。可改用托盘或关闭占用程序。" % names))
        logsetup.log("热键注册失败: %s" % names)

    gh = hk.GlobalHotkey(on_registered=hotkey_report)
    gh.register(hk.MOD_CONTROL | hk.MOD_SHIFT, hk.VK_S,
                lambda: ctrl.events.put(("request_capture",)))
    gh.register(hk.MOD_CONTROL | hk.MOD_SHIFT, hk.VK_R,
                lambda: ctrl.events.put(("request_select",)))
    gh.start()

    def on_quit():
        logsetup.log("退出程序")
        for fn in (gh.stop, tray.stop, root.destroy):
            try:
                fn()
            except Exception:
                pass

    app.on_quit = on_quit
    root.protocol("WM_DELETE_WINDOW", on_quit)
    logsetup.log("进入主循环")
    root.mainloop()
    logsetup.log("主循环结束")


if __name__ == "__main__":
    main()