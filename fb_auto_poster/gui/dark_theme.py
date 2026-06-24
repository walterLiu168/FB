"""暗色主題樣式"""
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

DARK_THEME = "darkly"


def setup_theme():
    """初始化暗色主題"""
    return ttk.Window(themename=DARK_THEME)


def create_styled_button(parent, text, command, bootstyle="primary", **kwargs):
    """建立暗色主題按鈕"""
    return ttk.Button(parent, text=text, command=command, bootstyle=bootstyle, **kwargs)


def create_styled_entry(parent, **kwargs):
    """建立暗色主題輸入框"""
    return ttk.Entry(parent, **kwargs)


def create_styled_label(parent, text, **kwargs):
    """建立暗色主題標籤"""
    return ttk.Label(parent, text=text, **kwargs)


def create_styled_frame(parent, **kwargs):
    """建立暗色主題框架"""
    return ttk.Frame(parent, **kwargs)


def create_notebook(parent, **kwargs):
    """建立分頁"""
    return ttk.Notebook(parent, **kwargs)
