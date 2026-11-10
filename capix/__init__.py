# -*- coding: utf-8 -*-
"""capix —— 固定截图框 + 连续截图工具。

纯标准库实现（Python 3.8+，Windows），无需安装任何第三方库：
  - 屏幕捕获：ctypes 调用 GDI (BitBlt/GetDIBits)
  - PNG 编码：stdlib (zlib + struct)
  - 全局热键：ctypes 调用 RegisterHotKey + 消息循环线程
  - 界面：tkinter
  - 框选遮罩：tkinter 全屏半透明
"""

__version__ = "1.0.0"