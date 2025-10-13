# -*- coding: utf-8 -*-
# 檔案: ui/animation.py
# 功用: 提供 UI 動畫效果的管理器。

import time

class AnimationManager:
    """一個簡單的動畫管理器，用於處理顏色漸變等效果。"""
    def __init__(self, root):
        self.root = root
        self.active_animations = {}

    def _hex_to_rgb(self, hex_color):
        """將 #RRGGBB 格式的十六進位顏色轉換為 (R, G, B) 元組。"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _rgb_to_hex(self, rgb_color):
        """將 (R, G, B) 元組轉換為 #RRGGBB 格式的十六進位顏色。"""
        r, g, b = [int(max(0, min(255, c))) for c in rgb_color]
        return f"#{r:02x}{g:02x}{b:02x}"

    def _interpolate_color(self, start_color, end_color, factor):
        """在兩種 RGB 顏色之間進行線性插值。"""
        start_rgb = self._hex_to_rgb(start_color)
        end_rgb = self._hex_to_rgb(end_color)
        new_rgb = [
            start_rgb[i] + (end_rgb[i] - start_rgb[i]) * factor
            for i in range(3)
        ]
        return self._rgb_to_hex(new_rgb)

    def animate_color(self, widget, property_name, start_color, end_color, duration=300):
        """
        為元件的指定屬性（如 fg_color, text_color）提供顏色漸變動畫。
        :param widget: 要執行動畫的 customtkinter 元件。
        :param property_name: 要改變顏色的屬性名稱 (字串)。
        :param start_color: 開始顏色 (十六進位)。
        :param end_color: 結束顏色 (十六進位)。
        :param duration: 動畫持續時間 (毫秒)。
        """
        animation_id = f"{id(widget)}-{property_name}"
        
        # 如果該元件的同一個屬性正在執行動畫，先停止舊的
        if animation_id in self.active_animations:
            self.root.after_cancel(self.active_animations[animation_id])

        start_time = time.monotonic()

        def _step():
            elapsed = (time.monotonic() - start_time) * 1000
            progress = min(1.0, elapsed / duration)
            
            current_color = self._interpolate_color(start_color, end_color, progress)
            widget.configure(**{property_name: current_color})

            if progress < 1.0:
                self.active_animations[animation_id] = self.root.after(10, _step)
            else:
                # 動畫結束後，確保最終顏色被設定
                widget.configure(**{property_name: end_color})
                if animation_id in self.active_animations:
                    del self.active_animations[animation_id]

        _step()