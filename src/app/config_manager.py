# -*- coding: utf-8 -*-
# 檔案: config_manager.py
# 功用: 封裝所有與設定檔 (config.json) 相關的讀寫操作。

import json
import os
import shutil
from datetime import datetime

from ..utils.deps import CONFIG_FILE, ENGINE_EDGE, DEFAULT_EDGE_VOICE

class ConfigManager:
    """
    一個專門用來管理 config.json 的類別。
    - 初始化時自動載入設定。
    - 提供 get/set 介面來安全地存取設定。
    - set 操作會自動觸發儲存。
    """
    DEFAULT_CONFIG = {
        "engine": ENGINE_EDGE,
        "voice": DEFAULT_EDGE_VOICE,
        "rate": 175,
        "volume": 1.0,
        "hotkey": "<shift>+z",
        "quick_phrases": [],
        "quick_input_position": "bottom-right",
        "enable_quick_phrases": True,
        "enable_listen_to_self": False,
        "listen_device_name": "Default",
        "listen_volume": 1.0,
        "auto_start_service": False,
        "text_history": [],
    }

    def __init__(self, log_func):
        self.log = log_func
        self.config = self.DEFAULT_CONFIG.copy()
        self.load()

    def get(self, key, default=None):
        """取得一個設定值。"""
        return self.config.get(key, default)

    def set(self, key, value):
        """設定一個值並自動儲存到檔案。"""
        self.config[key] = value
        self.save()

    def load(self):
        """從 config.json 載入設定，並與預設值合併。"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # 確保所有預設鍵都存在
                    for key, value in self.DEFAULT_CONFIG.items():
                        loaded_config.setdefault(key, value)
                    self.config.update(loaded_config)
            except (json.JSONDecodeError, IOError) as e:
                self.log(f"載入設定檔失敗: {e}。將備份損壞的檔案並建立新的預設設定。", "ERROR")
                try:
                    # 備份損壞的設定檔
                    backup_path = f"{CONFIG_FILE}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
                    shutil.move(CONFIG_FILE, backup_path)
                    self.log(f"已將損壞的設定檔備份至: {backup_path}", "INFO")
                except Exception as backup_error:
                    self.log(f"備份設定檔失敗: {backup_error}", "ERROR")
                # 使用預設值並儲存，以便下次啟動
                self.save()

    def save(self):
        """將當前設定儲存到 config.json。"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except IOError as e:
            self.log(f"儲存設定檔失敗: {e}", "ERROR")