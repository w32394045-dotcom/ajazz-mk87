"""MK87 库异常类型。"""
from __future__ import annotations


class MK87Error(Exception):
    """库内所有异常基类。"""


class DeviceNotFound(MK87Error):
    """未找到设备（未插、被其他程序占用、或复合设备启动失败）。"""


class DeviceDisconnected(MK87Error):
    """设备断开 / 句柄失效。"""


class ProtocolTimeout(MK87Error):
    """等待设备响应超时。"""


class ProtocolError(MK87Error):
    """设备返回了非法帧或错误码。"""


class UnsupportedFeature(MK87Error):
    """当前设备/连接方式不支持该功能（如 2.4G 下 TFT/音乐）。"""
