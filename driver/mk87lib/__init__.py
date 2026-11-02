"""mk87lib —— AJAZZ MK87 (0C45:8047 / 2.4G 0C45:FEFE) 协议库。

模块:
    const      常量（VID/PID、命令表、能力）
    transport  hidapi 封装（Windows/Linux）
    protocol   AA/55 帧协议
    device     设备对象（连接、命令、通知）
    keymap     改键 / FN 层编解码
    macro      宏表编解码
    lighting   灯效 / 逐键灯 / 0x32 帧流
    tft        TFT 图片与动画上传
    music      音乐律动
    wireless   2.4G 无线
    keyscan    OS 级按键捕获
    backup     备份 / 恢复
"""

__version__ = "0.1.1"
__all__ = [
    "const", "transport", "protocol", "device", "keymap", "macro",
    "lighting", "tft", "music", "wireless", "keyscan", "backup",
]
