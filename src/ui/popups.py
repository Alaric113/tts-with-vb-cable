# -*- coding: utf-8 -*-
# 檔案: src/ui/popups.py
# 功用: 定義應用程式中使用的各種 PyQt 彈出視窗。

from PyQt6.QtWidgets import ( # type: ignore
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QMainWindow,
    QLabel, QPushButton, QComboBox, QSlider, QCheckBox, QLineEdit,
    QFrame, QDialogButtonBox, QMessageBox, QScrollArea, QRadioButton, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QSize
from PyQt6.QtGui import QFont, QIcon, QColor

from ..utils.deps import APP_VERSION, check_model_downloaded
from ..app.model_manager import PREDEFINED_MODELS


class BaseDialog(QWidget):
    """所有彈出對話框的基類，提供統一的外觀和行為。"""
    def __init__(self, parent, title, width=500, height=300):
        super().__init__(parent)
        self.main_window = parent # 明確儲存主視窗的參照 (通常是 MainWindow)
        self.title = title
        self.setMinimumSize(width, height)
        self.setMaximumSize(width, height) # 設定最大尺寸以固定大小

        # --- 核心修改: 讓 BaseDialog 本身成為帶樣式的容器 ---
        self.setObjectName("BaseDialogFrame")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        # --- 獨立的彈出視窗樣式定義 ---
        self.TEXT_COLOR = "#333333"
        self.ACCENT_COLOR = "#007AFF"
        self.ACCENT_TEXT_COLOR = "#FFFFFF"
        self.BORDER_COLOR = "#EAEAEA"
        self.STATUS_ORANGE_COLOR = "#FF9500"
        self.STATUS_RED_COLOR = "#FF3B30"
        self.STATUS_GREEN_COLOR = "#34C759"


        # 顏色 (RGB for alpha)
        self.BG_COLOR_RGB = "247, 249, 252"
        self.CARD_BG_COLOR_RGB = "255, 255, 255"
        self.SUB_CARD_BG_COLOR_RGB = "255, 255, 255" # 根據設計稿，子卡片也是白色

        # 透明度
        self.CARD_OPACITY = 0.9
        self.SUB_CARD_OPACITY = 1.0

        # 元件顏色
        self.BUTTON_BG_COLOR = "#E9E9EB"
        self.BUTTON_HOVER_COLOR = "#DCDFE4"
        self.SLIDER_GROOVE_COLOR = "#E9E9EB"
        self.DISABLED_TEXT_COLOR = "#B0B0B0"
        self.DISABLED_BG_COLOR = "#F0F2F5"
        
        # 新增: 根據設計稿的顏色
        self.INPUT_BG_COLOR = "#E0E0E0"
        self.KEY_LABEL_BG_COLOR = "#CCCCCC"

        # --- 樣式表 ---
        self.setStyleSheet(f"""
            #BaseDialogFrame {{
                background-color: rgb({self.BG_COLOR_RGB});
                border-radius: 12px;
            }}
            QDialog {{
                background-color: transparent;
                color: {self.TEXT_COLOR};
            }}
            QLabel, QCheckBox, QRadioButton {{
                background-color: transparent;
                color: {self.TEXT_COLOR};
            }}
            QLabel#StatusLabel {{
                font-weight: bold;
            }}
            QLineEdit {{
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 8px;
                padding: 5px 8px;
                background-color: {self.INPUT_BG_COLOR};
                color: #000000; /* 確保輸入框文字為黑色 */
            }}
            QPushButton {{
                background-color: {self.BUTTON_BG_COLOR};
                color: {self.TEXT_COLOR};
                border: none;
                padding: 8px 16px;
                border-radius: 15px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {self.BUTTON_HOVER_COLOR};
            }}
            QPushButton:disabled {{
                background-color: {self.DISABLED_BG_COLOR};
                color: {self.DISABLED_TEXT_COLOR};
            }}
            QPushButton#DownloadButton {{
                background-color: {self.ACCENT_COLOR};
                color: {self.ACCENT_TEXT_COLOR};
            }}
            QPushButton#DeleteButton {{
                background-color: {self.STATUS_RED_COLOR};
                color: {self.ACCENT_TEXT_COLOR};
            }}
            QComboBox {{
                padding: 8px;
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 15px;
                background-color: rgba({self.SUB_CARD_BG_COLOR_RGB}, {self.SUB_CARD_OPACITY});
                color: {self.TEXT_COLOR};
            }}
            QSlider::groove:horizontal {{
                border: none;
                height: 6px;
                background: {self.SLIDER_GROOVE_COLOR};
                margin: 2px 0;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: rgba({self.CARD_BG_COLOR_RGB}, {self.CARD_OPACITY});
                border: 2px solid {self.ACCENT_COLOR};
                width: 16px;
                margin: -7px 0;
                border-radius: 10px;
            }}
            QFrame#SubCard {{
                background-color: rgba({self.SUB_CARD_BG_COLOR_RGB}, 0.7);
                border-radius: 18px;
            }}
            QFrame#Card {{
                background-color: rgba({self.CARD_BG_COLOR_RGB}, {self.CARD_OPACITY});
                border-radius: 18px;
                border: 1px solid {self.BORDER_COLOR};
            }}
            /* --- 新增: 快捷語音項目卡片樣式 --- */
            QFrame#PhraseItemCard, QFrame#ModelItemCard {{
                background-color: rgba(255, 255, 255, 0.7);
                border-radius: 12px;
            }}
            /* --- 新增: 快捷語音底部控制列樣式 --- */
            QFrame#ControlBar {{
                background-color: #E9E9EB; /* 使用與按鈕和下拉選單相同的背景色 */
                border-top: 1px solid #DCDFE4; /* 頂部加上分隔線 */
                border-bottom-left-radius: 12px; /* 圓角與父容器對齊 */
                border-bottom-right-radius: 12px;
            }}
            /* --- 新增: 統一滾動條樣式 --- */
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #DCDFE4;
                border-radius: 5px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #B0B0B0;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{
                background: none;
            }}

            QLabel#KeyLabel {{
                padding: 4px 10px;
                background-color: {self.KEY_LABEL_BG_COLOR};
                border-radius: 8px;
                font-weight: 500;
                color: #000000;
            }}
            QPushButton#DeleteButton {{
                background-color: transparent;
                color: {self.STATUS_RED_COLOR};
                font-size: 18px;
                font-weight: bold;
                border-radius: 14px;
                padding: 0;
                margin: 0;
                min-width: 28px;
                max-width: 28px;
            }}
            QPushButton#DeleteButton:hover {{
                background-color: {self.STATUS_RED_COLOR};
                color: white;
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
                background-color: {self.ACCENT_COLOR};
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
            /* --- Custom Title Bar --- */
            #TitleBarButton {{
                background-color: transparent;
                border-radius: 7px;
                padding: 0;
                margin: 0;
                font-size: 16px;
                color: #888888;
            }}
            #TitleBarButton:hover {{
                color: #333333;
            }}
            #CloseButton:hover {{ background-color: {self.STATUS_RED_COLOR}; color: white; }}
        """)

        # --- 核心修改: 簡化佈局 ---
        # BaseDialog 本身就是容器，直接在其上設定佈局
        frame_layout = QVBoxLayout(self)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # 加入自訂標題列和主內容區域
        frame_layout.addWidget(self._create_title_bar())
        self.main_layout = QVBoxLayout() # 這是給子類別放內容的地方
        self.main_layout.setContentsMargins(15, 10, 15, 15)
        self.main_layout.setSpacing(15)
        frame_layout.addLayout(self.main_layout)
        self._add_shadow(self) # 為 BaseDialog 本身加上陰影

    def _create_title_bar(self):
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(35)
        self.title_bar.setStyleSheet("background: transparent;") # 確保標題列透明
        layout = QHBoxLayout(self.title_bar)
        layout.setContentsMargins(15, 0, 5, 0)
        title_label = QLabel(self.title)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #666666;")
        layout.addWidget(title_label)
        layout.addStretch()
        close_button = QPushButton("✕")
        close_button.setObjectName("TitleBarButton")
        close_button.setProperty("class", "CloseButton") # 用於區分懸停樣式
        close_button.setFixedSize(28, 28)
        # 我們假設 parent 是 MainWindow
        if hasattr(self.main_window, 'hide_overlay'):
            close_button.clicked.connect(self.main_window.hide_overlay)
        layout.addWidget(close_button)
        return self.title_bar

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

    def _add_shadow(self, widget):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(0, 2)
        widget.setGraphicsEffect(shadow)
        return widget

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
        if self.app and self.app.quick_input_window:
             self.app.quick_input_window = None
        super().closeEvent(event)

class ModelManagementWindow(BaseDialog):
    def __init__(self, parent, app_controller):
        super().__init__(parent, "模型管理", 600, 400)
        self.app = app_controller
        self.ui_elements = {}
        self._build_ui()

    def _build_ui(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(10)
        
        self.main_layout.addWidget(scroll_area)
        scroll_area.setWidget(scroll_content)

        self.refresh_model_list()

    def refresh_model_list(self):
        # Clear existing widgets
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.ui_elements.clear()

        # Rebuild list
        for model_id, model_config in PREDEFINED_MODELS.items():
            self._create_model_item_widget(model_id, model_config)

        self.scroll_layout.addStretch(1)

    def _create_model_item_widget(self, model_id, model_config):
        card = QFrame()
        card.setObjectName("ModelItemCard")
        layout = QHBoxLayout(self._add_shadow(card))
        layout.setSpacing(15)

        name_label = QLabel(model_id)
        name_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(name_label, 1)

        status_label = QLabel()
        status_label.setObjectName("StatusLabel")
        layout.addWidget(status_label)

        download_button = QPushButton("下載")
        download_button.setObjectName("DownloadButton")
        download_button.clicked.connect(lambda: self.app.download_model(model_id))
        
        delete_button = QPushButton("刪除")
        delete_button.setObjectName("DeleteButton")
        delete_button.clicked.connect(lambda: self.app.delete_model(model_id))

        layout.addWidget(download_button)
        layout.addWidget(delete_button)

        self.ui_elements[model_id] = {
            "card": card,
            "status_label": status_label,
            "download_button": download_button,
            "delete_button": delete_button,
        }
        
        self.scroll_layout.addWidget(card)
        self._update_model_item_status(model_id)

    def _update_model_item_status(self, model_id):
        if model_id not in self.ui_elements:
            return

        widgets = self.ui_elements[model_id]
        is_downloaded = check_model_downloaded(model_id)

        if is_downloaded:
            widgets["status_label"].setText("已下載")
            widgets["status_label"].setStyleSheet(f"color: {self.STATUS_GREEN_COLOR};")
            widgets["download_button"].hide()
            widgets["delete_button"].show()
        else:
            widgets["status_label"].setText("未下載")
            widgets["status_label"].setStyleSheet(f"color: {self.STATUS_ORANGE_COLOR};")
            widgets["download_button"].show()
            widgets["delete_button"].hide()

class AddCustomVoiceDialog(QDialog):
    """一個用於新增或編輯自訂語音的小對話框。"""
    def __init__(self, parent, app_controller, existing_voice=None):
        super().__init__(parent)
        self.app = app_controller
        self.audio = app_controller.audio
        self.existing_voice = existing_voice

        self.setWindowTitle("新增自訂語音" if not existing_voice else "編輯自訂語音")
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QFormLayout(self)
        layout.setSpacing(15)

        self.name_input = QLineEdit(existing_voice["name"] if existing_voice else "")
        self.name_input.setPlaceholderText("例如：溫柔女聲、機器人")
        layout.addRow("自訂名稱:", self.name_input)

        self.base_voice_combo = QComboBox()
        all_edge_voices = self.audio.get_all_edge_voices()
        self.base_voice_combo.addItems([v["ShortName"] for v in all_edge_voices])
        if existing_voice:
            self.base_voice_combo.setCurrentText(existing_voice["base_voice"])
        layout.addRow("基礎聲線:", self.base_voice_combo)

        # 語速
        rate_layout = QHBoxLayout()
        self.rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.rate_slider.setRange(100, 250)
        self.rate_slider.setValue(existing_voice["rate"] if existing_voice else 175)
        self.rate_label = QLabel(str(self.rate_slider.value()))
        self.rate_slider.valueChanged.connect(lambda v: self.rate_label.setText(str(v)))
        rate_layout.addWidget(self.rate_slider)
        rate_layout.addWidget(self.rate_label)
        layout.addRow("語速:", rate_layout)

        # 音高
        pitch_layout = QHBoxLayout()
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(-100, 100)
        self.pitch_slider.setValue(existing_voice["pitch"] if existing_voice else 0)
        self.pitch_label = QLabel(str(self.pitch_slider.value()))
        self.pitch_slider.valueChanged.connect(lambda v: self.pitch_label.setText(str(v)))
        pitch_layout.addWidget(self.pitch_slider)
        pitch_layout.addWidget(self.pitch_label)
        layout.addRow("音高:", pitch_layout)

        # 按鈕
        button_box = QDialogButtonBox()
        preview_button = button_box.addButton("試聽", QDialogButtonBox.ButtonRole.ActionRole)
        preview_button.clicked.connect(self._preview)
        save_button = button_box.addButton("儲存", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_button = button_box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        save_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        layout.addRow(button_box)

    def _preview(self):
        self.audio.preview_text(
            "你好，這是自訂語音試聽。",
            override_voice=self.base_voice_combo.currentText(),
            override_rate=self.rate_slider.value(),
            override_pitch=self.pitch_slider.value()
        )

    def get_voice_data(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "錯誤", "自訂名稱不可為空。")
            return None
        return {
            "name": name,
            "base_voice": self.base_voice_combo.currentText(),
            "rate": self.rate_slider.value(),
            "pitch": self.pitch_slider.value(),
            "engine": self.app.ENGINE_EDGE # 目前只支援 Edge
        }

class VoiceSelectionWindow(BaseDialog):
    def __init__(self, parent, app_controller):
        super().__init__(parent, "Edge-TTS 語音聲線設定", 600, 550)
        self.app = app_controller
        self.audio = app_controller.audio
        # 複製一份設定進行編輯
        self.custom_voices_buffer = [v.copy() for v in self.app.config.get("custom_voices", [])]
        self.visible_voices_buffer = set(self.app.config.get("visible_voices", []))
        self.all_edge_voices = self.audio.get_all_edge_voices()
        self.ui_elements = {} # { "voice_name": {"checkbox": QCheckBox} }
        self._build_ui()

    def _build_ui(self):
        # --- 說明文字 ---
        info_label = QLabel("勾選聲線以在主視窗的下拉選單中顯示。")
        info_label.setStyleSheet("color: #666; font-size: 12px;")
        self.main_layout.addWidget(info_label)

        # --- 捲動列表 ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(10)

        # -- 自訂語音區 --
        custom_card, self.custom_layout = self._create_card("我的自訂語音")
        add_button = QPushButton("＋ 新增")
        add_button.clicked.connect(self._add_custom_voice)
        self.custom_layout.addWidget(add_button, 0, Qt.AlignmentFlag.AlignRight)
        self.scroll_layout.addWidget(custom_card)

        # -- 原始語音區 --
        original_card, self.original_layout = self._create_card("Edge-TTS 原始中文聲線")
        self.scroll_layout.addWidget(original_card)
        
        self.scroll_layout.addStretch(1)
        scroll_area.setWidget(scroll_content)
        self.main_layout.addWidget(scroll_area, 1)

        self._redraw_lists()

        # --- 底部控制區 ---
        control_frame = QFrame()
        control_frame.setObjectName("ControlBar")
        control_layout = QHBoxLayout(control_frame)
        control_layout.addStretch(1)

        save_button = QPushButton("套用並關閉")
        save_button.clicked.connect(self._save_and_close)
        control_layout.addWidget(save_button)
        self.main_layout.addWidget(control_frame)

    def _redraw_lists(self):
        # 清空
        for layout in [self.custom_layout, self.original_layout]:
            # 從 1 開始以跳過標題
            while layout.count() > 1:
                item = layout.takeAt(1)
                if item and item.widget():
                    item.widget().deleteLater()
        self.ui_elements.clear()

        # 重建自訂語音列表
        for index, voice_data in enumerate(self.custom_voices_buffer):
            self._create_voice_item_widget(voice_data, self.custom_layout, is_custom=True, index=index)

        # 重建原始語音列表
        for voice_data in self.all_edge_voices:
            self._create_voice_item_widget(voice_data, self.original_layout)

    def _create_voice_item_widget(self, voice_data, target_layout, is_custom=False, index=None):
        card = QFrame()
        card.setObjectName("PhraseItemCard")
        layout = QHBoxLayout(self._add_shadow(card))
        layout.setSpacing(15)

        voice_name = voice_data["name"] if is_custom else voice_data["ShortName"]
        
        checkbox = QCheckBox(voice_name)
        checkbox.setChecked(voice_name in self.visible_voices_buffer)
        checkbox.toggled.connect(lambda checked, name=voice_name: self._on_visibility_changed(checked, name))
        layout.addWidget(checkbox, 2)
        self.ui_elements[voice_name] = {"checkbox": checkbox}

        base_voice_name = voice_data["base_voice"] if is_custom else voice_data["ShortName"]
        base_voice_data = next((v for v in self.all_edge_voices if v["ShortName"] == base_voice_name), None)
        gender = "男" if base_voice_data and base_voice_data.get("Gender") == "Male" else "女"
        gender_label = QLabel(f"({gender})")
        gender_label.setFixedWidth(60)
        layout.addWidget(gender_label)

        if is_custom:
            params_text = f"速率: {voice_data['rate']}, 音高: {voice_data['pitch']}"
            params_label = QLabel(params_text)
            params_label.setStyleSheet("color: #666;")
            layout.addWidget(params_label, 1)

        layout.addStretch(1)

        if is_custom:
            edit_button = QPushButton("編輯")
            edit_button.clicked.connect(lambda _, i=index: self._edit_custom_voice(i))
            layout.addWidget(edit_button)
            delete_button = QPushButton("刪除")
            delete_button.clicked.connect(lambda _, i=index: self._delete_custom_voice(i))
            layout.addWidget(delete_button)

        preview_button = QPushButton("試聽")
        preview_button.setFixedWidth(80)
        preview_button.clicked.connect(lambda _, v=voice_data, c=is_custom: self._preview_voice(v, c))
        layout.addWidget(preview_button)

        target_layout.addWidget(card)

    def _on_visibility_changed(self, checked, voice_name):
        if checked:
            self.visible_voices_buffer.add(voice_name)
        else:
            self.visible_voices_buffer.discard(voice_name)

    def _preview_voice(self, voice_data, is_custom):
        if is_custom:
            self.audio.preview_text("你好", 
                override_voice=voice_data["base_voice"],
                override_rate=voice_data["rate"],
                override_pitch=voice_data["pitch"])
        else:
            self.audio.preview_text("你好", override_voice=voice_data["ShortName"])

    def _add_custom_voice(self):
        dialog = AddCustomVoiceDialog(self, self.app)
        if dialog.exec():
            new_voice_data = dialog.get_voice_data()
            if new_voice_data:
                self.custom_voices_buffer.append(new_voice_data)
                self.visible_voices_buffer.add(new_voice_data["name"]) # 新增的預設為可見
                self._redraw_lists()

    def _edit_custom_voice(self, index):
        voice_to_edit = self.custom_voices_buffer[index]
        dialog = AddCustomVoiceDialog(self, self.app, existing_voice=voice_to_edit)
        if dialog.exec():
            updated_voice_data = dialog.get_voice_data()
            if updated_voice_data:
                self.custom_voices_buffer[index] = updated_voice_data
                self._redraw_lists()

    def _delete_custom_voice(self, index):
        voice_to_delete = self.custom_voices_buffer[index]
        self.visible_voices_buffer.discard(voice_to_delete["name"])
        del self.custom_voices_buffer[index]
        self._redraw_lists()

    def _save_and_close(self):
        self.app.config.set("custom_voices", self.custom_voices_buffer)
        self.app.config.set("visible_voices", list(self.visible_voices_buffer))
        self.app.log_message("語音聲線設定已儲存。")
        self.app._update_ui_after_load()
        self.main_window.hide_overlay()
        
class QuickPhrasesWindow(BaseDialog):
    # 新增: 用於跨執行緒安全更新 UI 的信號
    # 參數: (int: 項目索引, str: 新的快捷鍵, str: 衝突訊息)
    hotkey_recorded_signal = pyqtSignal(int, str, str)

    def __init__(self, parent, app_controller):
        super().__init__(parent, "快捷語音設定", 600, 550)
        self.setObjectName("QuickPhrasesWindow")
        self.app = app_controller
        self.ui_elements = []
        # 複製一份設定進行編輯，點擊儲存時才寫回
        self.phrases_buffer = [p.copy() for p in self.app.quick_phrases]
        self._hotkey_listener = None # 新增: 用於追蹤 pynput 監聽器
        self.hotkey_recorded_signal.connect(self._on_hotkey_recorded)
        self._build_ui()

    def _build_ui(self):
        # --- 核心修改: 將所有內容放入一個卡片中 ---
        card, card_layout = self._create_card("快捷語音列表")

        # --- 新增按鈕 ---
        add_button = QPushButton("＋ 新增")
        add_button.clicked.connect(self._add_phrase_item)
        card_layout.addWidget(add_button, 0, Qt.AlignmentFlag.AlignRight)

        # --- 捲動列表 ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(10)
        self.scroll_layout.addStretch(1)
        scroll_area.setWidget(self.scroll_content)

        self._redraw_phrase_list()
        card_layout.addWidget(scroll_area, 1) # 讓捲動區佔用剩餘空間
        self.main_layout.addWidget(card, 1) # 讓卡片佔用主要空間

        # --- 儲存按鈕 ---
        save_button = QPushButton("儲存並關閉")
        save_button.clicked.connect(self._save_and_close)
        self.main_layout.addWidget(save_button, 0, Qt.AlignmentFlag.AlignRight)

    def _redraw_phrase_list(self):
        # 清空現有項目
        while self.scroll_layout.count() > 1: # 保留最後的 addStretch
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.ui_elements.clear()

        # 根據 self.phrases_buffer 重建列表
        for index, phrase in enumerate(self.phrases_buffer):
            self._create_phrase_item_widget(index, phrase)

    def _create_phrase_item_widget(self, index, phrase_data):
        phrase_card = QFrame()
        phrase_card.setObjectName("PhraseItemCard")
        card_layout = QHBoxLayout(self._add_shadow(phrase_card))
        card_layout.setSpacing(10)

        input_field = QLineEdit(phrase_data.get("text", ""))
        input_field.setPlaceholderText(f"快捷語音 {index + 1}...")
        input_field.editingFinished.connect(lambda i=index: self._update_phrase_text(i))
        card_layout.addWidget(input_field)

        # --- 變更: 合併快捷鍵顯示與設定按鈕 ---
        hotkey_button = QPushButton(phrase_data.get("hotkey") or "設定快捷鍵")
        hotkey_button.setCheckable(True)
        hotkey_button.setFixedWidth(120)
        hotkey_button.toggled.connect(lambda checked, i=index: self._record_quick_phrase_hotkey(i, checked))
        card_layout.addWidget(hotkey_button)

        delete_button = QPushButton("✕")
        delete_button.setObjectName("DeleteButton")
        delete_button.clicked.connect(lambda i=index: self._delete_phrase_item(i))
        card_layout.addWidget(delete_button)
        # 在 addStretch 之前插入
        self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, phrase_card)
        self.ui_elements.append({
            "card": phrase_card,
            "input": input_field,
            "hotkey_button": hotkey_button,
            "delete_button": delete_button
        })

    def _add_phrase_item(self):
        self.phrases_buffer.append({"text": "", "hotkey": ""})
        self._redraw_phrase_list()

    def _delete_phrase_item(self, index):
        if 0 <= index < len(self.phrases_buffer):
            del self.phrases_buffer[index]
            self._redraw_phrase_list()

    def _update_phrase_text(self, index):
        input_widget = self.ui_elements[index]["input"]
        self.phrases_buffer[index]["text"] = input_widget.text().strip()

    def _save_and_close(self):
        # 將緩衝區的內容寫回主程式的設定
        self.app.quick_phrases = self.phrases_buffer
        self.app.config.set("quick_phrases", self.app.quick_phrases)
        self.app.log_message("快捷語音設定已儲存。")
        # 如果服務正在運行，重啟快捷鍵監聽器以應用變更
        if self.app.is_running:
            self.app._start_hotkey_listener()
        
        # --- 快取邏輯: 觸發背景快取生成 ---
        self.app.log_message("開始在背景更新快捷語音快取...")
        for phrase in self.app.quick_phrases:
            if phrase.get("text") and phrase.get("hotkey"):
                self.app.audio.cache_phrase(phrase)

        self.main_window.hide_overlay()

    def _record_quick_phrase_hotkey(self, index_to_edit, is_recording):
        current_btn = self.ui_elements[index_to_edit]["hotkey_button"]
        if is_recording:
            if not self.app._quick_phrase_lock.acquire(blocking=False):
                current_btn.setChecked(False) # 立即將按鈕彈回
                self.app.log_message("已在錄製另一個快捷鍵，請先完成。", "WARN")
                return

            # 禁用所有其他按鈕
            for i, elem in enumerate(self.ui_elements):
                if i != index_to_edit:
                    elem["hotkey_button"].setEnabled(False)
                    elem["delete_button"].setEnabled(False)

            current_btn.setText("錄製中...") # 樣式由 QSS 處理
            current_btn.setStyleSheet(f"background-color: {self.STATUS_ORANGE_COLOR}; color: {self.ACCENT_TEXT_COLOR}; font-weight: bold;")
            self._start_pynput_listener(index_to_edit)
        else: # 使用者手動點擊取消錄製
            self.app.log_message("使用者取消了快捷鍵錄製。")
            self._finalize_recording(index_to_edit)

    def _finalize_recording(self, index):
        """一個集中的函式，用於停止監聽、釋放鎖並恢復 UI。"""
        # 停止 pynput 監聽器
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

        # 安全地釋放鎖
        if self.app._quick_phrase_lock.locked():
            self.app._quick_phrase_lock.release()

        # 恢復所有按鈕的狀態和外觀
        for i, elem in enumerate(self.ui_elements):
            elem["hotkey_button"].setText(self.phrases_buffer[i].get("hotkey") or "設定快捷鍵")
            elem["hotkey_button"].setEnabled(True)
            elem["delete_button"].setEnabled(True)
            elem["hotkey_button"].setStyleSheet("") # 清除特定樣式

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
            
            # --- 修正: 不直接操作 UI，而是發射信號 ---
            # 發射信號，將 UI 更新任務交給主執行緒
            self.hotkey_recorded_signal.emit(index_to_edit, normalized_hotkey, conflict_msg or "")

            return False

        # 確保在啟動新監聽器之前停止舊的
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

        self._hotkey_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._hotkey_listener.start()

    def _on_hotkey_recorded(self, index, hotkey_str, conflict_msg):
        """在主執行緒中安全地處理快捷鍵錄製完成後的 UI 更新。"""
        if conflict_msg:
            # 使用 app controller 的安全訊息框方法
            self.app.show_messagebox("快捷鍵衝突", conflict_msg, "warning")
        else:
            # 在主執行緒中更新數據
            self.phrases_buffer[index]["hotkey"] = hotkey_str
            self.app.log_message(f"快捷語音 {index + 1} 的快捷鍵已設為: {hotkey_str or '無'}")
        
        # --- 核心修正: 直接呼叫 finalize 函式，而不是觸發 toggled 信號 ---
        if 0 <= index < len(self.ui_elements):
            # 確保按鈕的勾選狀態被重設，但要阻止它再次觸發 _record_quick_phrase_hotkey
            button = self.ui_elements[index]["hotkey_button"]
            button.blockSignals(True)
            self.ui_elements[index]["hotkey_button"].setChecked(False)
            button.blockSignals(False)
            self._finalize_recording(index)