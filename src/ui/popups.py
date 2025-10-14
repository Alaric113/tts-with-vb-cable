# -*- coding: utf-8 -*-
# 檔案: src/ui/popups.py
# 功用: 定義應用程式中使用的各種 PyQt 彈出視窗。

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSlider, QCheckBox, QLineEdit,
    QFrame, QDialogButtonBox, QMessageBox, QScrollArea, QRadioButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIntValidator

from ..utils.deps import APP_VERSION

class BaseDialog(QDialog):
    """所有彈出對話框的基類，提供統一的外觀和行為。"""
    def __init__(self, parent, title, width=500, height=300):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(width, height)
        self.setModal(False) # 非模態，允許與主視窗互動

        # --- 修正: 為彈出視窗設定獨立、正確的樣式，不再繼承主視窗樣式 ---
        # 這可以從根本上解決「白底白字」的問題。
        self.setStyleSheet(f"""
            QDialog {{
                background-color: rgb({parent.BG_COLOR_RGB});
                color: {parent.TEXT_COLOR};
            }}
            QLabel, QCheckBox, QRadioButton {{
                background-color: transparent;
                color: {parent.TEXT_COLOR};
            }}
            QPushButton {{
                background-color: {parent.BUTTON_BG_COLOR};
                color: {parent.TEXT_COLOR};
                border: none;
                padding: 8px 16px;
                border-radius: 15px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {parent.BUTTON_HOVER_COLOR};
            }}
            QComboBox {{
                padding: 8px;
                border: 1px solid {parent.BORDER_COLOR};
                border-radius: 15px;
                background-color: rgba({parent.SUB_CARD_BG_COLOR_RGB}, {parent.SUB_CARD_OPACITY});
                color: {parent.TEXT_COLOR}; /* 新增: 設定下拉選單的文字顏色 */
            }}
            QSlider::groove:horizontal {{
                border: none;
                height: 6px;
                background: {parent.SLIDER_GROOVE_COLOR};
                margin: 2px 0;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: rgba({parent.CARD_BG_COLOR_RGB}, {parent.CARD_OPACITY});
                border: 2px solid {parent.ACCENT_COLOR};
                width: 16px;
                margin: -7px 0;
                border-radius: 10px;
            }}
            QFrame#SubCard {{
                background-color: rgba({parent.SUB_CARD_BG_COLOR_RGB}, {parent.SUB_CARD_OPACITY});
                border-radius: 18px;
            }}
            QFrame#Card {{
                background-color: rgba({parent.CARD_BG_COLOR_RGB}, {parent.CARD_OPACITY});
                border-radius: 18px;
                border: 1px solid {parent.BORDER_COLOR};
            }}
            /* --- CheckBox --- */
            QCheckBox::indicator {{
                width: 42px;
                height: 24px;
                border-radius: 12px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: #DCDFE4;
            }}
            QCheckBox::indicator:checked {{
                background-color: {parent.ACCENT_COLOR};
            }}
            QCheckBox::handle {{
                /* This is the white ball */
                width: 20px;
                height: 20px;
                border-radius: 10px;
                background-color: white;
            }}
            QCheckBox::handle:unchecked {{
                margin: 2px 20px 2px 2px;
            }}
            QCheckBox::handle:checked {{
                margin: 2px 2px 2px 20px;
            }}
            QCheckBox::indicator:disabled {{
                background-color: #F0F2F5;
            }}
            QCheckBox {{
                spacing: 10px; /* 文字與指示器之間的間距 */
            }}
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(15)

    def _create_card(self, title=""):
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(15, 10, 15, 10)
        card_layout.setSpacing(10)

        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet("font-size: 16px; font-weight: bold; border-bottom: 1px solid #EAEAEA; padding-bottom: 5px; background: transparent;")
            card_layout.addWidget(title_label)

        return card, card_layout

class SettingsWindow(BaseDialog):
    def __init__(self, parent, app_controller):
        super().__init__(parent, "其它設定", 450, 550)
        self.app = app_controller
        self.audio = app_controller.audio
        
        self._build_ui()
        self._toggle_listen_controls()

    def _build_ui(self):
        # --- 啟動時自動運行服務 ---
        auto_start_card, auto_start_layout = self._create_card()
        auto_start_layout.setDirection(QHBoxLayout.Direction.LeftToRight)
        auto_start_layout.addWidget(QLabel("啟動時自動運行服務:"))
        auto_start_layout.addStretch(1)
        self.auto_start_switch = QCheckBox("")
        self.auto_start_switch.setChecked(self.app.config.get("auto_start_service"))
        self.auto_start_switch.toggled.connect(self._on_toggle_auto_start)
        auto_start_layout.addWidget(self.auto_start_switch)
        self.main_layout.addWidget(auto_start_card)

        # --- 快捷輸入框位置 ---
        pos_card, pos_layout = self._create_card("快捷輸入框顯示位置")
        self.position_group = {}
        positions = { "螢幕中央": "center", "左上角": "top-left", "右上角": "top-right", "左下角": "bottom-left", "右下角": "bottom-right" }
        pos_grid = QGridLayout()
        for i, (text, value) in enumerate(positions.items()):
            rb = QRadioButton(text)
            rb.toggled.connect(lambda checked, v=value: self._on_position_change(checked, v))
            if self.app.quick_input_position == value:
                rb.setChecked(True)
            pos_grid.addWidget(rb, i // 2, i % 2)
        pos_layout.addLayout(pos_grid)
        self.main_layout.addWidget(pos_card)

        # --- 聆聽自己語音 ---
        listen_card, listen_layout = self._create_card("聆聽自己的語音")
        
        switch_layout = QHBoxLayout()
        switch_layout.addWidget(QLabel("啟用聆聽功能:"))
        switch_layout.addStretch(1)
        self.listen_switch = QCheckBox("")
        self.listen_switch.setChecked(self.audio.enable_listen_to_self)
        self.listen_switch.toggled.connect(self._on_toggle_listen_to_self)
        switch_layout.addWidget(self.listen_switch)
        listen_layout.addLayout(switch_layout)

        listen_layout.addWidget(QLabel("聆聽設備:"))
        self.listen_device_combo = QComboBox()
        self.listen_device_combo.addItems(self.audio.get_listen_device_names())
        self.listen_device_combo.setCurrentText(self.audio.listen_device_name)
        self.listen_device_combo.currentTextChanged.connect(self._on_listen_device_change)
        listen_layout.addWidget(self.listen_device_combo)

        volume_layout = QGridLayout()
        volume_layout.addWidget(QLabel("聆聽音量:"), 0, 0)
        self.listen_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.listen_volume_slider.setRange(0, 100)
        self.listen_volume_slider.setValue(int(self.audio.listen_volume * 100))
        self.listen_volume_slider.valueChanged.connect(self._on_listen_volume_change)
        volume_layout.addWidget(self.listen_volume_slider, 0, 1)
        self.listen_volume_label = QLabel(f"{int(self.audio.listen_volume * 100)}%")
        volume_layout.addWidget(self.listen_volume_label, 0, 2)
        volume_layout.setColumnStretch(1, 1)
        listen_layout.addLayout(volume_layout)
        self.main_layout.addWidget(listen_card)

        # --- 檢查更新 ---
        update_button = QPushButton("檢查更新")
        update_button.clicked.connect(lambda: self.app.updater.check_for_updates(silent=False))
        self.main_layout.addWidget(update_button)

        self.main_layout.addStretch(1)

        # --- 版本號 ---
        version_label = QLabel(f"版本: {APP_VERSION}")
        version_label.setStyleSheet("color: gray; font-size: 12px;")
        self.main_layout.addWidget(version_label, 0, Qt.AlignmentFlag.AlignRight)

    def _on_toggle_auto_start(self, checked):
        self.app.log_message(f"啟動時自動運行服務已 {'啟用' if checked else '停用'}")
        self.app.config.set("auto_start_service", checked)

    def _on_position_change(self, checked, value):
        if checked:
            self.app.quick_input_position = value
            self.app.log_message(f"輸入框位置已設定為: {self.app.quick_input_position}")
            self.app.config.set("quick_input_position", self.app.quick_input_position)

    def _on_toggle_listen_to_self(self, checked):
        self.audio.enable_listen_to_self = checked
        self.app.log_message(f"聆聽自己的語音功能已 {'啟用' if checked else '停用'}")
        self.app.config.set("enable_listen_to_self", checked)
        self._toggle_listen_controls()

    def _toggle_listen_controls(self):
        is_enabled = self.audio.enable_listen_to_self
        self.listen_device_combo.setEnabled(is_enabled)
        self.listen_volume_slider.setEnabled(is_enabled)

    def _on_listen_device_change(self, choice):
        self.audio.listen_device_name = choice
        self.app.log_message(f"聆聽設備已設定為: {self.audio.listen_device_name}")
        self.app.config.set("listen_device_name", self.audio.listen_device_name)

    def _on_listen_volume_change(self, value):
        self.audio.listen_volume = round(value / 100.0, 2)
        self.listen_volume_label.setText(f"{value}%")
        self.app.config.set("listen_volume", self.audio.listen_volume)

class QuickPhrasesWindow(BaseDialog):
    def __init__(self, parent, app_controller):
        super().__init__(parent, "快捷語音設定", 600, 550)
        self.app = app_controller
        self.ui_elements = []
        self._build_ui()

    def _build_ui(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setObjectName("Card")
        scroll_area.setStyleSheet("#Card { border: none; }")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(10)

        for index in range(10):
            phrase = self.app.quick_phrases[index]
            item_frame = QFrame()
            item_frame.setObjectName("SubCard")
            item_layout = QHBoxLayout(item_frame)
            item_frame.setStyleSheet(f"#SubCard {{ background-color: rgba({self.parent().SUB_CARD_BG_COLOR_RGB}, {self.parent().SUB_CARD_OPACITY}); border-radius: 18px; }}")

            entry = QLineEdit(phrase.get("text", ""))
            entry.setPlaceholderText(f"快捷語音 {index + 1}...")
            entry.setStyleSheet("border: none; background: transparent;")
            entry.editingFinished.connect(lambda i=index: self._update_phrase_text(i))
            item_layout.addWidget(entry)

            hotkey_btn = QPushButton(phrase.get("hotkey", "設定快捷鍵"))
            hotkey_btn.setFixedWidth(120)
            hotkey_btn.setCheckable(True)
            hotkey_btn.toggled.connect(lambda checked, i=index: self._record_quick_phrase_hotkey(i, checked))
            item_layout.addWidget(hotkey_btn)

            content_layout.addWidget(item_frame)
            self.ui_elements.append({"entry": entry, "button": hotkey_btn})

        content_layout.addStretch(1)
        scroll_area.setWidget(content_widget)
        self.main_layout.addWidget(scroll_area)

    def _update_phrase_text(self, index):
        entry_widget = self.ui_elements[index]["entry"]
        current_text = entry_widget.text()
        self.app.quick_phrases[index]["text"] = current_text.strip()
        self.app.config.set("quick_phrases", self.app.quick_phrases)
        self.app.log_message(f"快捷語音 {index + 1} 已更新。")

    def _record_quick_phrase_hotkey(self, index_to_edit, is_recording):
        if not self.app._quick_phrase_lock.acquire(blocking=False):
            self.ui_elements[index_to_edit]["button"].setChecked(False)
            self.app.log_message("已在錄製另一個快捷鍵，請先完成。", "WARN")
            return

        # 禁用所有其他按鈕
        for i, elem in enumerate(self.ui_elements):
            if i != index_to_edit:
                elem["button"].setEnabled(False)

        current_btn = self.ui_elements[index_to_edit]["button"]
        if is_recording:
            current_btn.setText("錄製中...")
            current_btn.setStyleSheet(f"background-color: {self.parent().STATUS_ORANGE_COLOR}; color: {self.parent().ACCENT_TEXT_COLOR}; font-weight: bold;")
            self._start_pynput_listener(index_to_edit)
        else: # 錄製被取消或完成
            self.app._quick_phrase_lock.release()
            # 恢復所有按鈕
            for i, elem in enumerate(self.ui_elements):
                elem["button"].setEnabled(True)
                elem["button"].setStyleSheet("")

    def _start_pynput_listener(self, index_to_edit):
        from pynput import keyboard
        pressed = set()

        def on_press(key):
            key_str = self.app._key_to_str(key)
            if key_str:
                pressed.add(key_str)

        def on_release(key):
            hotkey_str = "+".join(sorted(list(pressed))) if pressed else ""
            normalized_hotkey = self.app._normalize_hotkey(hotkey_str)

            conflict_msg = self.app._check_hotkey_conflict(normalized_hotkey, 'quick_phrase', index_to_edit)
            if conflict_msg:
                QMessageBox.warning(self, "快捷鍵衝突", conflict_msg)
            else:
                self.app.quick_phrases[index_to_edit]["hotkey"] = normalized_hotkey
                self._update_phrase_text(index_to_edit)
                self.app.log_message(f"快捷語音 {index_to_edit + 1} 的快捷鍵已設為: {normalized_hotkey or '無'}")

            # 恢復 UI
            self.ui_elements[index_to_edit]["button"].setChecked(False) # 這會觸發 toggled 信號，進而釋放鎖和恢復按鈕
            self.ui_elements[index_to_edit]["button"].setText(self.app.quick_phrases[index_to_edit].get("hotkey") or "設定快捷鍵")

            if self.app.is_running:
                self.app._start_hotkey_listener()
            return False

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

class QuickInputWindow(QWidget):
    def __init__(self, app_controller):
        super().__init__()
        self.app = app_controller
        self.history_index = -1

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.entry = QLineEdit(self)
        # 從主視窗讀取樣式變數
        bg_color_rgb = self.app.main_window.QUICK_INPUT_BG_COLOR
        opacity = self.app.main_window.QUICK_INPUT_OPACITY

        self.entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba({bg_color_rgb}, {opacity});
                color: #FFFFFF;
                border: 1px solid #0078D7;
                border-radius: 5px;
                padding: 8px;
                font-size: 16px;
            }}
        """)
        self.layout.addWidget(self.entry)

        self.entry.returnPressed.connect(self.app.send_quick_input)
        self.entry.installEventFilter(self)

        QTimer.singleShot(100, self.app.release_input_window_lock)

    def eventFilter(self, source, event):
        if event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self.app.handle_quick_input_history(self.entry, event.key())
                return True
            elif event.key() == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(source, event)

    def focusOutEvent(self, event):
        self.close()
        super().focusOutEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.entry.setFocus()
        self.entry.selectAll()

    def closeEvent(self, event):
        self.app.release_input_window_lock()
        self.app.quick_input_window = None
        super().closeEvent(event)
