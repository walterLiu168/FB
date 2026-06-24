"""TikTok 直式幻燈片產生器 — 將圖片 + 文案合成 1080x1920 MP4

純影片工具：縮放圖片 → 置中於黑色畫布 → 疊加文案 → 串接成影片。
不涉及任何平台 API 或上傳。
"""
import os
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from utils.config import get_data_path

# TikTok 直式規格
CANVAS_W = 1080
CANVAS_H = 1920
DEFAULT_DURATION = 3  # 每張圖片秒數
DEFAULT_FPS = 24

_TEMP_DIR = "temp_tiktok"
_OUTPUT_NAME = "output.mp4"


def _output_dir() -> str:
    path = get_data_path(_TEMP_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """載入字型，找不到 Arial 時退回 PIL 預設字型"""
    candidates = [
        "arial.ttf",
        "Arial.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\msjh.ttc",  # 微軟正黑體，支援中文
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _fit_image_on_canvas(img_path: str) -> Image.Image:
    """將圖片縮放到 1080px 寬並置中於 1080x1920 黑色畫布"""
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))
    try:
        src = Image.open(img_path).convert("RGB")
    except (OSError, IOError) as e:
        raise ValueError(f"無法開啟圖片: {img_path} ({e})")

    # 等比縮放到 1080 寬
    ratio = CANVAS_W / src.width
    new_h = int(src.height * ratio)
    src = src.resize((CANVAS_W, new_h), Image.LANCZOS)

    # 若高度超過畫布則改以高度為基準縮放
    if new_h > CANVAS_H:
        ratio = CANVAS_H / src.height
        new_w = int(src.width * ratio)
        src = src.resize((new_w, CANVAS_H), Image.LANCZOS)

    x = (CANVAS_W - src.width) // 2
    y = (CANVAS_H - src.height) // 2
    canvas.paste(src, (x, y))
    return canvas


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """將文字依畫布寬度換行（同時支援空白分隔與逐字換行）"""
    lines: List[str] = []
    for raw_line in text.split("\n"):
        if not raw_line.strip():
            lines.append("")
            continue
        words = raw_line.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                # 單一 word 仍過寬 → 逐字切
                if draw.textlength(word, font=font) > max_width:
                    chunk = ""
                    for ch in word:
                        if draw.textlength(chunk + ch, font=font) <= max_width:
                            chunk += ch
                        else:
                            lines.append(chunk)
                            chunk = ch
                    current = chunk
                else:
                    current = word
        if current:
            lines.append(current)
    return lines


def _overlay_text(canvas: Image.Image, text: str, font_size: int = 48) -> Image.Image:
    """在畫布底部疊加白字 + 黑色陰影"""
    if not text.strip():
        return canvas

    draw = ImageDraw.Draw(canvas)
    font = _load_font(font_size)

    margin = 60
    max_width = CANVAS_W - margin * 2
    lines = _wrap_text(text, font, max_width, draw)

    line_height = font_size + 12
    total_h = line_height * len(lines)
    # 從底部往上排，留 160px 邊距
    start_y = CANVAS_H - total_h - 160

    for i, line in enumerate(lines):
        if not line:
            continue
        line_w = draw.textlength(line, font=font)
        x = (CANVAS_W - line_w) // 2
        y = start_y + i * line_height
        # 黑色陰影（四向偏移）
        for dx, dy in ((-2, -2), (2, -2), (-2, 2), (2, 2), (0, 2), (2, 0)):
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        # 白色主文字
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    return canvas


def create_slideshow(
    image_paths: List[str],
    ad_text: str,
    duration_per_image: int = DEFAULT_DURATION,
    output_path: Optional[str] = None,
    fps: int = DEFAULT_FPS,
) -> str:
    """從圖片 + 文案建立直式 1080x1920 MP4 幻燈片

    Args:
        image_paths: 圖片路徑列表 (建議 2-5 張)
        ad_text: 要疊加的廣告文案
        duration_per_image: 每張圖片顯示秒數 (預設 3)
        output_path: 輸出路徑 (預設 data/temp_tiktok/output.mp4)
        fps: 影格率

    Returns:
        產生的 MP4 檔案路徑

    Raises:
        ValueError: 沒有提供圖片或圖片無法開啟
        ImportError: 未安裝 moviepy
    """
    if not image_paths:
        raise ValueError("至少需要一張圖片")

    # moviepy 為選用重相依，延遲匯入以便 import 測試不需要它
    # moviepy 2.x 移除了 moviepy.editor 命名空間，故兩種路徑都嘗試
    try:
        try:
            from moviepy import ImageSequenceClip  # moviepy >= 2.0
        except ImportError:
            from moviepy.editor import ImageSequenceClip  # moviepy 1.x
    except ImportError as e:
        raise ImportError(
            "需要 moviepy 才能合成影片，請執行: pip install moviepy"
        ) from e

    import numpy as np

    if output_path is None:
        output_path = os.path.join(_output_dir(), _OUTPUT_NAME)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    frames = []
    for path in image_paths:
        canvas = _fit_image_on_canvas(path)
        canvas = _overlay_text(canvas, ad_text)
        frames.append(np.array(canvas))

    # 每張圖片重複多個影格以維持顯示時間
    durations = [duration_per_image] * len(frames)
    clip = ImageSequenceClip(frames, durations=durations)
    # set_fps (1.x) / with_fps (2.x)
    if hasattr(clip, "with_fps"):
        clip = clip.with_fps(fps)
    else:
        clip = clip.set_fps(fps)
    clip.write_videofile(
        output_path,
        codec="libx264",
        audio=False,
        logger=None,
    )
    clip.close()

    return output_path


def clean_temp() -> None:
    """清除暫存影片目錄"""
    import shutil
    path = get_data_path(_TEMP_DIR)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
