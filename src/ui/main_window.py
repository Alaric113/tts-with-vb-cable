# -*- coding: utf-8 -*-
# 檔案: src/ui/main_window.py
# 功用: 定義 PyQt6 的主視窗類別 MainWindow。

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSlider, QFrame, QTextEdit, QSizePolicy,
    QCheckBox, QTabWidget, QGraphicsDropShadowEffect, QGraphicsBlurEffect
)
from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtGui import QFont, QIcon, QColor
import os
import sys

class WheelAdjustableSlider(QSlider):
    """一個可透過滑鼠滾輪調整數值的 QSlider。"""
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        # 設定焦點策略，確保滑鼠懸停時能接收滾輪事件
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        """覆寫滾輪事件處理函式。"""
        # 根據滾輪滾動方向調整數值
        delta = event.angleDelta().y()
        if delta > 0: # 向上滾動
            self.setValue(self.value() + 1)
        elif delta < 0: # 向下滾動
            self.setValue(self.value() - 1)
        
        event.accept() # 接受事件，防止其傳播到父元件

class MainWindow(QMainWindow):
    def __init__(self, app_controller):
        super().__init__()
        self.app = app_controller
        self.setWindowTitle("JuMouth - TTS 語音助手")

        # --- 無邊框與半透明設定 ---
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.drag_position = QPoint()

        # --- 樣式定義 ---
        # -- 主色調 --
        self.BG_COLOR = "#f0f0f0"             # 主視窗背景 (極淺灰色)
        self.CARD_COLOR = "#FFFFFF"           # 卡片背景 (純白)
        self.SUB_CARD_COLOR = "#FFFFFF"       # 子卡片/輸入框背景 (白色)
        self.BORDER_COLOR = "#EAEAEA"         # 邊框顏色 (更柔和的灰色)
        # -- 強調色 --
        self.ACCENT_COLOR = "#007AFF"         # 主要強調色 (蘋果藍)
        self.ACCENT_HOVER_COLOR = "#0062CC"   # 強調色懸停
        self.ACCENT_TEXT_COLOR = "#FFFFFF"    # 強調色上的文字 (白色)
        # -- 文字顏色 --
        self.TEXT_COLOR = "#333333"           # 主要文字 (深灰) - OK
        self.SECONDARY_TEXT_COLOR = "#888888" # 次要文字 (中灰)
        self.DISABLED_TEXT_COLOR = "#B0B0B0"  # 禁用文字 (淺灰)
        # -- 狀態顏色 --
        self.STATUS_GREEN_COLOR = "#34C759"   # 運行中 (蘋果綠)
        self.STATUS_ORANGE_COLOR = "#FF9500"  # 已停止 (蘋果橘)
        self.STATUS_RED_COLOR = "#FF3B30"     # 錯誤/停止按鈕 (蘋果紅)
        # -- 視窗與卡片透明度 --
        self.WINDOW_OPACITY = 0.97                # 主視窗透明度
        self.MAIN_FRAME_BG_COLOR_RGB = "240, 240, 240" # 主框架背景色 (RGB for #f0f0f0)
        self.MAIN_FRAME_OPACITY = 1.0             # 主框架透明度 (1.0 為不透明)
        # -- 卡片透明度 --
        self.CARD_BG_COLOR_RGB = "255, 255, 255"   # 主卡片背景色 (RGB)
        self.CARD_OPACITY = 0.9                   # 主卡片透明度 (半透明)
        self.SUB_CARD_BG_COLOR_RGB = "240, 242, 245" # 子卡片背景色 (RGB)
        self.SUB_CARD_OPACITY = 1.0               # 子卡片透明度 (1.0 為不透明)
        self.QUICK_INPUT_BG_COLOR = "30, 30, 30"  # 快速輸入框背景色 (RGB)
        self.QUICK_INPUT_OPACITY = 0.95           # 快速輸入框透明度

        # 應用透明度
        self.setWindowOpacity(self.WINDOW_OPACITY)

        self.setStyleSheet(f"""
            /* Main window is transparent, this styles the main content frame */
            #MainFrame {{
                background-color: rgba({self.MAIN_FRAME_BG_COLOR_RGB}, {self.MAIN_FRAME_OPACITY});
                border-radius: 20px;
            }}
            QMessageBox {{
                background-color: {self.BG_COLOR};
                font-size: 14px;
            }}
            QFrame#BubbleCard, QFrame#Card, QTextEdit#LogArea {{
                background-color: rgba({self.CARD_BG_COLOR_RGB}, {self.CARD_OPACITY});
                border-radius: 20px;
                border: none; /* Remove border, use shadow instead */
            }}
            QLabel, QCheckBox {{
                font-size: 14px;
                background: transparent;
                color: {self.TEXT_COLOR};
            }}
            QMessageBox QLabel {{
                background-color: transparent;
                color: {self.TEXT_COLOR};
            }}
            /* Capsule Buttons */
            QPushButton, QPushButton#AccentButton {{
                background-color: #E9E9EB;
                color: {self.TEXT_COLOR};
                border: none;
                padding: 10px 20px;
                border-radius: 18px; /* Height is ~36px, so radius is half */
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #DCDFE4; /* 按鈕懸停背景 */
            }}
            QPushButton:disabled {{
                background-color: #F0F2F5;
                color: {self.DISABLED_TEXT_COLOR};
            }}
            QPushButton#AccentButton {{
                background-color: {self.ACCENT_COLOR};
                color: {self.ACCENT_TEXT_COLOR};
            }}
            QPushButton#AccentButton:hover {{
                background-color: {self.ACCENT_HOVER_COLOR};
            }}
            QPushButton#AccentButton:disabled {{
                background-color: #F0F2F5; /* 禁用時的淺灰色 */
                color: {self.DISABLED_TEXT_COLOR};
            }}
            QPushButton#StopButton:disabled {{
                background-color: #F0F2F5; /* 禁用時的淺灰色 */
                color: {self.DISABLED_TEXT_COLOR};
            }}
            QPushButton#StopButton {{
                background-color: {self.STATUS_RED_COLOR};
                color: {self.ACCENT_TEXT_COLOR};
            }}
            QPushButton#StopButton:hover {{
                background-color: #D93025; /* A slightly darker red for hover */
            }}
            /* --- 新增: 用於小工具按鈕 (如 +/-) 的樣式 --- */
            QPushButton#ToolButton {{
                padding: 0px; /* 覆蓋全域 padding */
                font-size: 20px;
                font-weight: normal;
                background-color: transparent; /* 移除背景色 */
                border: none; /* 確保沒有邊框 */
                color: black; /* 設定文字顏色 */
            }}

            #TitleBarButton {{
                background-color: transparent;
                border-radius: 7px;
                padding: 0;
                margin: 0;
            }}
            #CloseButton:hover {{ background-color: {self.STATUS_RED_COLOR}; }}
            #MinimizeButton:hover {{ background-color: #FFBD2E; /* 最小化按鈕懸停黃色 */ }}
            QComboBox {{
                padding: 8px;
                border: none;
                border-radius: 15px;
                background-color: #E9E9EB;
                color: {self.TEXT_COLOR}; /* 新增: 設定下拉選單的文字顏色 */
            }}
            QComboBox::drop-down {{
                border: none;
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 25px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {self.CARD_COLOR};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 8px;
                outline: 0px;
                color: {self.TEXT_COLOR}; /* 新增: 確保下拉列表中的文字顏色正確 */
            }}
            QSlider::groove:horizontal {{
                border: none;
                height: 6px;
                background: #E9E9EB;
                margin: 0 0;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {self.ACCENT_TEXT_COLOR};
                border: 2px solid {self.ACCENT_COLOR};
                width: 16px;
                margin: -7px 0;
                border-radius: 10px;
            }}
            QSlider::groove:vertical {{
                border: none;
                width: 6px;
                background: #E9E9EB;
                margin: 0 2px;
                border-radius: 3px;
            }}
            QSlider::handle:vertical {{
                background: {self.ACCENT_TEXT_COLOR};
                border: 2px solid {self.ACCENT_COLOR};
                height: 16px;
                margin: 0 -7px;
                border-radius: 10px;
            }}
            QTextEdit#LogArea {{
                background-color: #e0e0e0; /* 略深於主背景 */
                color: {self.TEXT_COLOR};
                border-radius: 20px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 5px;
                border: none;
            }}
            QTabWidget::pane {{
                border: none;
                background-color: transparent;
            }}
            QTabBar::tab {{
                background: #E9E9EB;
                color: {self.TEXT_COLOR};
                padding: 10px 20px;
                border-radius: 18px; /* Capsule-like tabs */
                border: none;
                margin-right: 5px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background: {self.ACCENT_COLOR};
                color: {self.ACCENT_TEXT_COLOR};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #DCDFE4;
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
        """)

        # 設定圖示
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        self.icon_path = os.path.join(base_path, '..', '..', 'icon.ico')
        if os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(self.icon_path))

        # --- 主框架 ---
        self.main_frame = QFrame()
        self.main_frame.setObjectName("MainFrame")
        # 為主框架添加陰影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 5)
        self.main_frame.setGraphicsEffect(shadow)

        # --- 修正: QMainWindow 不能直接設定 layout ---
        # 1. 建立一個容器 widget 作為 central widget
        container_widget = QWidget()
        # 2. 為這個容器 widget 設定 layout
        central_layout = QVBoxLayout(container_widget) # 這是透明 QMainWindow 的佈局
        central_layout.addWidget(self.main_frame)
        central_layout.setContentsMargins(20, 20, 20, 20) # 陰影的可見區域

        # 3. 將容器 widget 設為 QMainWindow 的 central widget
        self.setCentralWidget(container_widget)

        content_layout = QVBoxLayout(self.main_frame) # 這是圓角框架內的佈局
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        # 建立各個區塊
        content_layout.addWidget(self._create_title_bar())
        
        # 內容容器
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(20, 10, 20, 20)
        body_layout.setSpacing(15)
        content_layout.addWidget(body_widget)

        body_layout.addWidget(self._create_dashboard()) # 頂部儀表板
        body_layout.addWidget(self._create_main_content_area()) # 新的整合內容區
        body_layout.addWidget(self._create_log_area(), 1) # 底部日誌區

        # 將 app controller 的參照指向 UI 元件
        self.app.engine_combo = self.engine_combo
        self.app.voice_combo = self.voice_combo
        self.app.local_device_combo = self.local_device_combo

        # --- 新增: 覆蓋層與模糊效果 ---
        self.overlay_widget = QWidget(self.main_frame)
        self.overlay_widget.setObjectName("Overlay")
        self.overlay_widget.setStyleSheet("#Overlay { background-color: rgba(0, 0, 0, 0.3); }")
        self.overlay_layout = QVBoxLayout(self.overlay_widget)
        self.overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay_widget.hide()

        # 設置初始大小
        self.resize(720, 610) # 初始為收合狀態

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 檢查點擊是否在標題列區域
            if self.title_bar.underMouse():
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = QPoint()
        event.accept()

    def closeEvent(self, event):
        self.app.on_closing()
        event.accept()

    def resizeEvent(self, event):
        """確保覆蓋層始終與主框架大小相同。"""
        self.overlay_widget.resize(self.main_frame.size())
        super().resizeEvent(event)

    def _create_title_bar(self):
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(40)
        self.title_bar.setStyleSheet("background-color: transparent;")
        layout = QHBoxLayout(self.title_bar)
        layout.setContentsMargins(15, 0, 5, 0)

        if os.path.exists(self.icon_path):
            icon_label = QLabel()
            icon_label.setPixmap(QIcon(self.icon_path).pixmap(QSize(20, 20)))
            layout.addWidget(icon_label)

        title_label = QLabel("JuMouth - TTS 語音助手")
        title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {self.SECONDARY_TEXT_COLOR};")
        layout.addWidget(title_label)
        layout.addStretch()

        minimize_button = QPushButton("—")
        minimize_button.setObjectName("TitleBarButton")
        minimize_button.setFixedSize(28, 28)
        minimize_button.clicked.connect(self.showMinimized)
        layout.addWidget(minimize_button)

        close_button = QPushButton("✕")
        close_button.setObjectName("TitleBarButton")
        close_button.setFixedSize(28, 28)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)

        return self.title_bar

    def _add_shadow(self, widget):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(0, 3)
        widget.setGraphicsEffect(shadow)
        return widget

    def _create_dashboard(self):
        card = QFrame()
        card.setObjectName("BubbleCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 15, 20, 15)

        title = QLabel("JuMouth TTS")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        layout.addStretch(1)

        self.start_button = QPushButton("▶ 啟動服務")
        self.start_button.setObjectName("AccentButton")
        self.start_button.setFixedWidth(140)
        self.start_button.clicked.connect(self.app.start_local_player)
        layout.addWidget(self._add_shadow(self.start_button))

        self.stop_button = QPushButton("■ 停止服務")
        self.stop_button.setObjectName("StopButton") # 設定 ID 以應用紅色樣式
        self.stop_button.setFixedWidth(140)
        self.stop_button.clicked.connect(self.app.stop_local_player)
        self.stop_button.setEnabled(False)
        layout.addWidget(self._add_shadow(self.stop_button))

        self.status_label = QLabel("● 已停止")
        self.status_label.setStyleSheet(f"color: {self.STATUS_ORANGE_COLOR}; font-weight: bold;")
        self.status_label.setFixedWidth(80)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        return self._add_shadow(card)

    def _create_main_content_area(self):
        """建立整合後的主內容區域，取代舊的 Tab 視圖。"""
        self.content_widget = QWidget() # 將 content_widget 提升為實例屬性
        # 主佈局改為垂直，以容納兩排
        main_layout = QVBoxLayout(self.content_widget)
        main_layout.setContentsMargins(0, 15, 0, 15)
        main_layout.setSpacing(15)

        # --- 第一排: 輸出設備 & TTS 引擎 ---
        top_row_widget = QWidget()
        top_row_layout = QHBoxLayout(top_row_widget)
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(15)

        out_frame = self._create_output_device_card()
        top_row_layout.addWidget(self._add_shadow(out_frame))

        sel_frame = self._create_tts_selection_card()
        top_row_layout.addWidget(self._add_shadow(sel_frame))
        main_layout.addWidget(top_row_widget)

        # --- 第二排: (左) 快捷鍵 & 功能, (右) 滑桿 ---
        bottom_row_widget = QWidget()
        bottom_row_layout = QHBoxLayout(bottom_row_widget)
        bottom_row_layout.setContentsMargins(0, 0, 0, 0)
        bottom_row_layout.setSpacing(15)

        # -- 左側: 快捷鍵 & 功能 (垂直排列) --
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(15)

        hotkey_card = self._create_hotkey_card()
        left_layout.addWidget(hotkey_card) # hotkey_card 內部已加陰影

        actions_card = self._create_actions_card()
        left_layout.addWidget(actions_card) # actions_card 內部已加陰影
        bottom_row_layout.addWidget(left_panel, 1) # 左側佔用更多空間

        # -- 右側: 垂直滑桿區 --
        sliders_card = self._create_sliders_card()
        bottom_row_layout.addWidget(self._add_shadow(sliders_card), 0) # 右側佔用最小寬度
        main_layout.addWidget(bottom_row_widget)

        return self.content_widget

    def _create_output_device_card(self):
        """建立輸出設備設定卡片。"""
        out_frame = QFrame()
        out_frame.setObjectName("BubbleCard")
        out_layout = QVBoxLayout(out_frame)
        out_layout.setSpacing(15)
        out_layout.addWidget(QLabel("輸出設備:"))
        self.local_device_combo = QComboBox()
        self.local_device_combo.addItem("正在載入...")
        self.local_device_combo.setEnabled(False)
        self.local_device_combo.currentTextChanged.connect(self.app._on_local_device_change)
        out_layout.addWidget(self.local_device_combo)
        out_layout.addWidget(QLabel(f"💡 提示: Discord 麥克風請設為 {self.app.CABLE_INPUT_HINT}", styleSheet=f"color: {self.SECONDARY_TEXT_COLOR}; font-weight: normal;"))
        return out_frame

    def _create_tts_selection_card(self):
        """建立 TTS 引擎與聲線選擇卡片。"""
        sel_frame = QFrame()
        sel_frame.setObjectName("BubbleCard")
        sel_layout = QVBoxLayout(sel_frame)
        sel_layout.setSpacing(10)
        sel_layout.addWidget(QLabel("TTS 引擎:"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItems([self.app.ENGINE_EDGE, self.app.ENGINE_PYTTX3])
        self.engine_combo.setCurrentText(self.app.audio.current_engine)
        self.engine_combo.currentTextChanged.connect(self.app._on_engine_change)
        sel_layout.addWidget(self.engine_combo)
        sel_layout.addSpacing(10)
        sel_layout.addWidget(QLabel("語音聲線:"))
        self.voice_combo = QComboBox()
        self.voice_combo.addItem("正在載入...")
        self.voice_combo.setEnabled(False)
        self.voice_combo.currentTextChanged.connect(self.app._on_voice_change)
        sel_layout.addWidget(self.voice_combo)
        sel_layout.addStretch(1)
        return sel_frame

    def _create_sliders_card(self):
        """建立包含垂直滑桿的語音參數卡片。"""
        tts_params_frame = QFrame()
        tts_params_frame.setObjectName("BubbleCard")
        main_layout = QHBoxLayout(tts_params_frame)
        main_layout.setSpacing(20)

        # 語速
        speed_layout = QVBoxLayout()
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(5) # 減少垂直間距
        speed_layout.addWidget(QLabel("語速"), 0, Qt.AlignmentFlag.AlignCenter) # 標題

        self.speed_slider = WheelAdjustableSlider(Qt.Orientation.Vertical)
        self.speed_slider.setRange(100, 250)
        self.speed_slider.setValue(self.app.audio.tts_rate)
        self.speed_slider.valueChanged.connect(self.app.update_tts_settings)

        speed_layout.addWidget(self.speed_slider, 1) # stretch=1, 移除置中對齊以填滿空間

        self.speed_value_label = QLabel(str(self.app.audio.tts_rate))
        speed_layout.addWidget(self.speed_value_label, 0, Qt.AlignmentFlag.AlignCenter)
        main_layout.addLayout(speed_layout)

        # 音量
        volume_layout = QVBoxLayout()
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.setSpacing(5)
        volume_layout.addWidget(QLabel("音量"), 0, Qt.AlignmentFlag.AlignCenter) # 標題

        self.volume_slider = WheelAdjustableSlider(Qt.Orientation.Vertical)
        self.volume_slider.setRange(50, 100) # 0.5 to 1.0
        self.volume_slider.setValue(int(self.app.audio.tts_volume * 100))
        self.volume_slider.valueChanged.connect(self.app.update_tts_settings)

        volume_layout.addWidget(self.volume_slider, 1) # stretch=1, 移除置中對齊以填滿空間

        self.volume_value_label = QLabel(f"{self.app.audio.tts_volume:.2f}")
        volume_layout.addWidget(self.volume_value_label, 0, Qt.AlignmentFlag.AlignCenter)
        main_layout.addLayout(volume_layout)

        # 音高
        pitch_layout = QVBoxLayout()
        pitch_layout.setContentsMargins(0, 0, 0, 0)
        pitch_layout.setSpacing(5)
        pitch_layout.addWidget(QLabel("音高"), 0, Qt.AlignmentFlag.AlignCenter) # 標題

        self.pitch_slider = WheelAdjustableSlider(Qt.Orientation.Vertical)
        self.pitch_slider.setRange(-100, 100)
        self.pitch_slider.setValue(self.app.audio.tts_pitch)
        self.pitch_slider.valueChanged.connect(self.app.update_tts_settings)
        pitch_layout.addWidget(self.pitch_slider, 1) # stretch=1, 移除置中對齊以填滿空間

        self.pitch_value_label = QLabel(str(self.app.audio.tts_pitch))
        pitch_layout.addWidget(self.pitch_value_label, 0, Qt.AlignmentFlag.AlignCenter)
        main_layout.addLayout(pitch_layout)

        # 讓滑桿卡片有最小高度，以容納垂直滑桿
        tts_params_frame.setMinimumHeight(220) # 移除按鈕後，可以稍微縮小高度

        return tts_params_frame

    def _create_hotkey_card(self):
        """建立主快捷鍵設定卡片。"""
        hotkey_card = QFrame()
        hotkey_card.setObjectName("BubbleCard")
        layout = QGridLayout(self._add_shadow(hotkey_card))
        layout.addWidget(QLabel("快速輸入框快捷鍵:"), 0, 0, 1, 2)
        
        keys_display_layout = QHBoxLayout()
        self.hotkey_key_buttons = []
        for i in range(3):
            btn = QPushButton("")
            btn.setFixedSize(80, 38) # Match button height
            btn.setEnabled(False)
            btn.clicked.connect(lambda _, b=i: self.app._prepare_single_key_recording(b))
            keys_display_layout.addWidget(btn)
            self.hotkey_key_buttons.append(btn)
        layout.addLayout(keys_display_layout, 1, 0)

        self.hotkey_edit_button = QPushButton("✏️ 編輯")
        self.hotkey_edit_button.setFixedWidth(100)
        self.hotkey_edit_button.clicked.connect(self.app._toggle_hotkey_edit)
        layout.addWidget(self.hotkey_edit_button, 1, 1, Qt.AlignmentFlag.AlignRight)

        self.hotkey_info_label = QLabel("點擊 '編輯' 開始設定快捷鍵。")
        self.hotkey_info_label.setStyleSheet(f"color: {self.SECONDARY_TEXT_COLOR}; font-size: 11px;")
        layout.addWidget(self.hotkey_info_label, 2, 0, 1, 2)
        layout.setColumnStretch(0, 1)
        return hotkey_card

    def _create_actions_card(self):
        """建立包含快捷語音開關和功能按鈕的卡片。"""
        actions_card = QFrame()
        actions_card.setObjectName("BubbleCard")
        # --- 核心修正: 改用網格佈局以分行顯示 ---
        actions_layout = QGridLayout(self._add_shadow(actions_card))
        actions_layout.setContentsMargins(15, 15, 15, 15)
        actions_layout.setHorizontalSpacing(10)
        actions_layout.setVerticalSpacing(15)

        # 快捷語音開關
        actions_layout.addWidget(QLabel("啟用快捷語音功能:"), 0, 0)
        self.quick_phrase_switch = QCheckBox("")
        self.quick_phrase_switch.toggled.connect(self.app._on_toggle_quick_phrases)
        actions_layout.addWidget(self.quick_phrase_switch, 0, 1)
        actions_layout.setColumnStretch(2, 1) # 讓右側有彈性空間

        # 功能按鈕 (第二行)
        self.quick_phrase_button = QPushButton("快捷語音設定")
        self.quick_phrase_button.clicked.connect(self.app._open_quick_phrases_window)
        actions_layout.addWidget(self.quick_phrase_button, 1, 0)

        self.voice_settings_button = QPushButton("語音聲線設定")
        self.voice_settings_button.clicked.connect(self.app._open_voice_selection_window)
        actions_layout.addWidget(self.voice_settings_button, 1, 1)

        self.settings_button = QPushButton("其它設定")
        self.settings_button.clicked.connect(self.app._open_settings_window)
        actions_layout.addWidget(self.settings_button, 1, 2)

        return actions_card

    def _create_log_area(self):
        log_widget = QWidget()
        layout = QVBoxLayout(log_widget)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)

        header_card = QFrame()
        header_card.setObjectName("BubbleCard")
        header_card.setStyleSheet(f"QFrame#BubbleCard {{ border-bottom-left-radius: 0; border-bottom-right-radius: 0; border-bottom: none; }}")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(20, 10, 15, 10)
        
        title = QLabel("日誌")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        self.log_toggle_button = QPushButton("▼")
        self.log_toggle_button.setFixedSize(30, 30)
        self.log_toggle_button.setObjectName("ToolButton")
        # --- 核心修正: 設定一個能顯示符號的字體 ---
        self.log_toggle_button.setFont(QFont("Arial", 12))
        self.log_toggle_button.clicked.connect(self.app.toggle_log_area)
        header_layout.addWidget(self.log_toggle_button)
        layout.addWidget(self._add_shadow(header_card))

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setObjectName("LogArea")
        self.log_text.setStyleSheet(f"QTextEdit#LogArea {{ border-top-left-radius: 0; border-top-right-radius: 0; border-top: none; }}")
        self.log_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.log_text)

        return log_widget

    def show_overlay(self, widget_to_show):
        """顯示覆蓋層並模糊背景。"""
        # 將要顯示的 widget 加入覆蓋層的佈局
        self.overlay_layout.addWidget(widget_to_show)

        # 應用模糊效果
        blur_effect = QGraphicsBlurEffect()
        blur_effect.setBlurRadius(15)
        self.content_widget.setGraphicsEffect(blur_effect)

        self.overlay_widget.show()

    def hide_overlay(self):
        """隱藏覆蓋層並移除模糊效果。"""
        # 移除模糊效果
        self.content_widget.setGraphicsEffect(None)

        # 從佈局中移除 widget 並刪除它
        if self.overlay_layout.count() > 0:
            widget_to_remove = self.overlay_layout.takeAt(0).widget()
            if widget_to_remove:
                widget_to_remove.deleteLater()
        self.overlay_widget.hide()