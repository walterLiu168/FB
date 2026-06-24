"""FB POSTER Launcher — 直接啟動主程式"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fb_auto_poster"))
from gui.app import FBPosterApp
print("Starting FB POSTER...")
app = FBPosterApp()
app.mainloop()
