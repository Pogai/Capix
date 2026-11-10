# -*- coding: utf-8 -*-
"""日志初始化：写文件日志 + 捕获未处理异常，便于问题记录与迭代。"""

import datetime
import logging
import os
import sys
import threading

from . import paths

_logger = None
_log_file = None


def setup():
    """初始化日志（进程启动时调用一次）。返回 logger。"""
    global _logger, _log_file
    d = paths.log_dir()
    os.makedirs(d, exist_ok=True)
    today = datetime.date.today().strftime("%Y%m%d")
    _log_file = os.path.join(d, "capix_%s.log" % today)

    logger = logging.getLogger("capix")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if not logger.handlers:
        fh = logging.FileHandler(_log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(fh)
    _logger = logger

    def _excepthook(exc_type, exc, tb):
        logger.error("未捕获异常", exc_info=(exc_type, exc, tb))

    def _thread_hook(args):
        logger.error(
            "线程未捕获异常: %s" % getattr(args, "thread", None),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _excepthook
    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass

    try:
        from . import __version__
    except Exception:
        __version__ = "?"
    logger.info("=" * 60)
    logger.info("启动 capix v%s | frozen=%s | python=%s",
                __version__, paths.is_frozen(), sys.version.split()[0])
    logger.info("日志文件: %s", _log_file)
    return logger


def log(msg, level=logging.INFO):
    if _logger is not None:
        _logger.log(level, msg)
    try:
        print(msg)
    except Exception:
        pass


def info(msg):
    log(msg, logging.INFO)


def error(msg, exc_info=False):
    if _logger is not None:
        _logger.error(msg, exc_info=exc_info)
    try:
        print(msg)
    except Exception:
        pass


def get_file():
    return _log_file


def get_dir():
    return paths.log_dir()