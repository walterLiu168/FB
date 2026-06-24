"""FB POSTER Launcher — 授權檢查 + 主程式"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fb_auto_poster"))
from main import main

if __name__ == "__main__":
    main()
