# -*- coding: utf-8 -*-
"""
打包配置（PyInstaller）。

用法：
    pip install pyinstaller
    pyinstaller build_exe.py

产物：
    dist/日程备忘.exe   （单文件，双击即可运行，无需安装 Python）
"""

import os
import sys

# 打包参数
APP_NAME = "日程备忘"
MAIN_SCRIPT = "main.py"
ICON = "app_icon.ico"   # 可选：自备 .ico 图标；不存在则自动跳过

# 隐藏导入（pystray 在 Windows 上需要显式指定后端）
HIDDEN_IMPORTS = [
    "pystray._win32",
    "PIL._tkinter_finder",
]

# 排除无用的大模块，减小体积
EXCLUDES = [
    "numpy", "pandas", "matplotlib", "scipy", "pytest",
    "tkinter.test", "test", "unittest",
]


def build() -> int:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",           # 覆盖已存在的产物
        "--clean",               # 清理缓存
        "--onefile",             # 单文件 exe
        "--windowed",            # 不显示控制台窗口
        "--name", APP_NAME,
        "--hidden-import", HIDDEN_IMPORTS[0],
        "--hidden-import", HIDDEN_IMPORTS[1],
    ]
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]

    if os.path.exists(ICON):
        args += ["--icon", ICON]

    args.append(MAIN_SCRIPT)

    print("执行：", " ".join(args))
    ret = os.system(" ".join(f'"{a}"' if " " in a else a for a in args))
    if ret == 0:
        print("\n打包完成：dist/%s.exe" % APP_NAME)
    else:
        print("\n打包失败，请检查上方错误信息")
    return ret


if __name__ == "__main__":
    sys.exit(build())
