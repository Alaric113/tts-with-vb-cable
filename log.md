---
**重要規則：**
每次對專案進行任何修改時，都必須在此 `log.md` 檔案中記錄相關的交接資訊。這包括：
- 更改的目的和背景。
- 所涉及的檔案和模組。
- 所做的具體更改（高層次概述）。
- 任何新增的依賴項或配置。
- 對於下一個階段的代理或開發者來說，需要了解的任何重要事項。
- 盡量減少冗餘和重複的資訊，注重精煉和高層次概括，以減少儲存和處理的成本（token 浪費）。

請確保這些資訊清晰、簡潔並具體，以便後續人員能夠快速理解並繼續工作。
---

# 專案交接文件: 橘Mouth - TTS 虛擬麥克風控制器

## 1. 專案概述

**橘Mouth (JuMouth)** 是一個為 Windows 設計的桌面應用程式，旨在提供一個便捷的方式，讓使用者能夠透過自定義快捷鍵，將輸入的文字轉換為語音 (Text-to-Speech, TTS)，並將其透過虛擬麥克風 (VB-CABLE) 播放到任何語音通訊軟體 (如 Discord, LINE 等) 中。其核心目標是提升語音互動的便利性和靈活性。

## 2. 核心功能

*   **快捷鍵觸發**：支援全域快捷鍵，快速彈出輸入框，輸入文字後立即播放語音。
*   **雙語音引擎**：
    *   **Edge-TTS**：提供高品質、自然流暢的微軟雲端語音（需網路連線）。
    *   **pyttsx3**：使用 Windows 內建的離線語音（無需網路）。
*   **高度自定義**：
    *   自由選擇語音聲線（包括 Edge-TTS 和 pyttsx3 的多種聲線，以及自定義聲線）。
    *   調整語速、音量和音高。
    *   配置輸出設備（自動偵測 VB-CABLE）。
    *   設定快捷語音（預設短語及其專屬快捷鍵）。
*   **智慧依賴管理**：
    *   自動偵測並引導使用者安裝 **VB-CABLE** 虛擬音訊驅動程式（透過執行系統管理員權限的安裝程式）。
    *   自動偵測並下載安裝 **FFmpeg** 到應用程式資料夾，不污染系統環境。
*   **設定自動儲存**：所有使用者設定會自動儲存。
*   **直觀的日誌介面**：所有操作、狀態和錯誤訊息會清晰顯示於主視窗。
*   **單一實例運行**：確保應用程式在任何時間點只有一個實例在運行。
*   **音訊快取**：為快捷語音提供音訊快取機制，減少重複合成的時間。
*   **聆聽自己**：可選功能，允許使用者將語音同時輸出到 VB-CABLE 和另一個本地設備，以便同時監聽。

## 3. 技術棧

*   **程式語言**：Python
*   **GUI 框架**：PyQt6
*   **TTS 引擎**：
    *   `edge-tts` (透過 `asyncio`)
    *   `pyttsx3` (Windows 內建 SAPI5)
*   **音訊處理**：
    *   `sounddevice` (音訊設備互動，播放)
    *   `pydub` (音訊檔案操作，如轉換、重採樣)
    *   `numpy` (數值運算，與 `sounddevice` 配合)
*   **熱鍵監聽**：`pynput` (全域熱鍵監聽)
*   **Windows 系統交互**：`pywin32`, `comtypes` (用於單一實例、前景視窗控制、SAPI5 交互)
*   **HTTP 請求**：`requests` (用於下載依賴等)
*   **打包**：`PyInstaller` (用於生成可執行檔)

## 4. 專案架構概覽

專案採用類似 Model-View-Controller (MVC) 或 Model-View-Presenter (MVP) 的結構，核心邏輯、UI 呈現和音訊處理之間有明確的分離。

*   **`main.py`**：應用程式的頂層入口點，主要用於 `PyInstaller` 打包，並導向至 `src/__main__.py`。
*   **`src/__main__.py`**：應用程式的實際啟動點。負責初始化 PyQt 應用程式、處理單一實例檢查、設定高 DPI、處理全域異常，並實例化 `LocalTTSPlayer`。
*   **`src/app/app.py` (`LocalTTSPlayer` - Controller/Presenter)**：
    *   應用程式的核心控制器，協調所有模組。
    *   管理應用程式狀態、配置 (`ConfigManager`)。
    *   初始化並管理音訊引擎 (`AudioEngine`) 和更新管理器 (`UpdateManager`)。
    *   建立並連接主視窗 (`MainWindow`)，處理 UI 互動事件。
    *   處理全域快捷鍵監聽，顯示快速輸入框。
    *   管理依賴安裝流程 (`DependencyManager`)，包括 VB-CABLE 和 FFmpeg。
    *   使用 `AppSignals` 進行跨執行緒通信，確保 UI 更新的安全。
*   **`src/app/audio_engine.py` (`AudioEngine` - Model/Worker)**：
    *   專責音訊處理的核心模組，在獨立的工作執行緒中運行，透過佇列 (`play_queue`) 接收任務。
    *   封裝 `edge-tts` 和 `pyttsx3` 的合成邏輯。
    *   管理音訊設備（偵測 VB-CABLE，選擇輸出設備）。
    *   處理音訊的合成、檔案轉換、重採樣和多設備播放。
    *   實現語音快取機制。
*   **`src/app/config_manager.py`**：處理應用程式配置的載入、儲存和管理。
*   **`src/app/updater_manager.py`**：負責檢查應用程式更新。
*   **`src/utils/deps.py`**：定義應用程式共用常數、輔助函數和 `DependencyManager` 類別，用於自動化依賴項的檢查和安裝。
*   **`src/ui/main_window.py` (`MainWindow` - View)**：
    *   定義應用程式的主視窗佈局、視覺元素和樣式 (使用 QSS)。
    *   實現無邊框視窗拖曳、主內容區、狀態儀表板、音訊設定、快捷鍵設定、快捷語音設定、日誌顯示等。
    *   包含覆蓋層系統 (`QStackedLayout`)，用於顯示設定彈出視窗並模糊背景。
*   **`src/ui/popups.py`**：定義各種彈出視窗，如快速輸入框 (`QuickInputWindow`)、設定視窗 (`SettingsWindow`)、快捷語音設定視窗 (`QuickPhrasesWindow`)、語音聲線選擇視窗 (`VoiceSelectionWindow`)。
*   **`src/ui/animation.py`**：處理 UI 元素的動畫效果。

## 5. 依賴與設定

### 5.1 Python 環境依賴

專案使用 `requirements.txt` 和 `requirements-windows.txt` 來管理 Python 依賴。`requirements-windows.txt` 包含了 Windows 專用的依賴和版本限制。

**`requirements-windows.txt` 內容：**

```
# 這是針對 Windows 環境的依賴列表。
# 核心修正: 限制 numpy 版本小於 2.0，以解決與 torch 等套件的 ABI 相容性問題。
numpy<2.0

# GUI 框架
PyQt6

# TTS 引擎與音訊處理
edge-tts
pyttsx3
kokoro>=0.8.2
misaki[zh]>=0.8.2
sounddevice
pydub

# Windows 特定功能
pynput
comtypes
pywin32

# 其它工具
requests
packaging
```

**安裝方式：**

```bash
pip install -r requirements-windows.txt
```

### 5.2 外部系統依賴

*   **VB-CABLE Virtual Audio Device**：
    *   一個虛擬音訊線，用於將應用程式的音訊輸出重定向為麥克風輸入。
    *   應用程式會自動偵測其是否存在，並引導使用者下載安裝。
    *   安裝需要系統管理員權限。
*   **FFmpeg**：
    *   用於音訊檔案的解碼、編碼、轉換等操作。
    *   應用程式會自動偵測其是否存在，並在需要時自動下載到應用程式的 `%LOCALAPPDATA%\JuMouth` 目錄下。

## 6. 建置與執行

### 6.1 開發環境運行

1.  **克隆專案**：
    ```bash
    git clone https://github.com/your-username/tts-with-vb-cable.git
    cd tts-with-vb-cable
    ```
2.  **安裝依賴**：
    ```bash
    pip install -r requirements-windows.txt
    ```
3.  **運行應用程式**：
    ```bash
    python main.py
    ```

### 6.2 打包 (使用 PyInstaller)

專案使用 `PyInstaller` 將 Python 應用程式打包成獨立的 Windows 可執行檔 (`.exe`)。

*   `JuMouth.spec`：PyInstaller 的打包配置檔案。
*   `build.bat`：自動化打包過程的批次檔。

**打包步驟：**

1.  確保已安裝 `PyInstaller` (包含在 `requirements-windows.txt` 中)。
2.  運行批次檔：
    ```bash
    build.bat
    ```
    這將在 `dist` 目錄中生成 `JuMouth.exe`。

## 7. 注意事項與潛在問題

*   **Windows 專用**：應用程式的許多功能，特別是 VB-CABLE 安裝、`pywin32` 和 `comtypes` 的使用，都是 Windows 特定的。在其他作業系統上運行會受到限制。
*   **管理員權限**：安裝 VB-CABLE 和某些熱鍵功能可能需要應用程式以管理員權限運行，尤其是在全螢幕遊戲中。
*   **ffmpeg 路徑**：如果 FFmpeg 沒有自動下載成功，可能需要手動將其路徑配置到系統 PATH 或應用程式可訪問的位置。
*   **多執行緒**：音訊處理 (`AudioEngine`) 在單獨的執行緒中運行，透過佇列與主 UI 執行緒通信。處理跨執行緒問題時需特別注意。`pyttsx3` 引擎實例是即時創建和銷毀的，以避免跨執行緒問題。
*   **快捷鍵衝突**：應用程式內建了快捷鍵衝突檢測，但在某些情況下仍可能與其他系統或應用程式的全域快捷鍵衝突。
*   **依賴更新**：`numpy<2.0` 的限制應注意，以確保與其他可能導入 NumPy 的庫（如 `torch`）的 ABI 相容性。
*   **日誌記錄**：應用程式有詳細的日誌記錄機制，所有錯誤都會記錄到 `%LOCALAPPDATA%\JuMouth\error.log`。

---

### **2025年11月24日 更新記錄**

**修改目的與背景：**
使用者要求替換不穩定的 `edge-tts` 引擎，並希望能夠支援 `Sherpa-ONNX` 和 `ChatTTS` 這兩種高品質的離線 TTS 引擎。同時，要求新增一個「語音模型管理器」功能，允許使用者下載和管理這些 TTS 模型。

**所涉及的檔案和模組：**
- `src/utils/deps.py`
- `src/app/model_manager.py` (新增)
- `src/app/app.py`

**所做的具體更改：**
1.  **`src/utils/deps.py` 更改：**
    *   新增 `ENGINE_SHERPA_ONNX = "sherpa-onnx"` 常數。
    *   新增 `ENGINE_CHATTTS = "chattts"` 常數。
    *   這些常數用於識別新的 TTS 引擎類型。
2.  **新增 `src/app/model_manager.py`：**
    *   定義 `VoiceModel` 類別：用於儲存每個語音模型的元資料，包括 ID、名稱、引擎類型、語言、描述、下載 URL、本地路徑、狀態（未下載、下載中、已下載、錯誤）、是否啟用和是否為自定義模型。
    *   定義 `PREDEFINED_MODELS` 列表：包含預設的 `Sherpa ONNX 國語女聲 (VITS)` 和 `ChatTTS 國語通用模型` 的範例配置。
    *   定義 `ModelManager` 類別：
        *   初始化時載入設定檔中已儲存的模型資料，並整合預定義模型。
        *   提供 `get_models()` 和 `get_model_by_id()` 方法來獲取模型資訊。
        *   實作 `save_models_to_config()` 將模型狀態持久化到設定檔。
        *   實作 `download_model()` 方法：目前為模擬下載邏輯，最終將整合實際的下載和解壓縮功能。它會在獨立執行緒中運行，並發出進度信號。
        *   實作 `delete_model()` 方法：用於刪除已下載的模型檔案及其狀態。
        *   實作 `add_custom_model()` 方法：用於新增使用者自定義模型。
        *   實作 `set_model_active()` 方法：用於啟用/停用模型，並確保同一引擎類型只有一個模型處於啟用狀態。
        *   發出 `model_status_changed` 和 `model_download_progress` 信號，供 UI 更新使用。
3.  **`src/app/app.py` 更改：**
    *   從 `src.app.model_manager` 導入 `ModelManager` 和 `VoiceModel`。
    *   在 `LocalTTSPlayer` 的 `__init__` 方法中實例化 `ModelManager`，將 `self.log_message` 和 `self.config` 傳遞給它。
    *   將 `ENGINE_SHERPA_ONNX` 和 `ENGINE_CHATTTS` 常數作為 `LocalTTSPlayer` 實例的屬性暴露，以便在 UI 或其他模組中方便存取。

**新增的依賴項或配置：**
- 尚未實際新增 Python 套件依賴，但後續將新增 `sherpa-onnx` 和 `torch` 等套件到 `requirements-windows.txt`。
- 新增了 `tts_models_downloaded` 目錄用於存放下載的模型檔案。
- `ConfigManager` 將新增一個 `downloaded_voice_models` 鍵來儲存模型狀態。

**對於下一個階段的代理或開發者來說，需要了解的任何重要事項：**
- 目前 `ModelManager` 中的 `download_model` 方法只包含模擬下載邏輯，需要替換為真實的 HTTP 下載和壓縮檔解壓縮邏輯。這需要整合 `src/utils/deps.py` 中的 `download_with_progress` 和 `extract_zip` 等工具。
- `PREDEFINED_MODELS` 列表中的 `download_url` 和 `file_names` 都是範例，需要根據實際的 Sherpa-ONNX 和 ChatTTS 模型下載來源進行確認和調整。
- UI 方面，目前只設計了 `ModelManager` 的資料結構和後端邏輯，尚未有任何 UI 元素來操作這個管理器。下一步需要為「語音模型管理器」創建一個新的彈出視窗及其在 `main_window.py` 或 `SettingsWindow` 中的入口點。
- 整個 `AudioEngine` 需要重構以實際使用 `ModelManager` 中下載的模型進行 TTS 合成。
- 需要更新 `requirements-windows.txt` 以包含 `sherpa-onnx` 和 `torch` 等相關套件。
---

### **2025年11月25日 更新記錄**

**修改目的與背景：**
- 解決 `pynput` 庫在解析快捷鍵時遇到的 `ValueError` (如 `ValueError: shift` 和 `ValueError: f1`)，原因是 `pynput` 期望修飾鍵和特殊鍵以 `<key>` 格式傳入 `GlobalHotKeys`。
- 解決 `AttributeError: 'ConfigManager' object has no attribute 'save_config'`，此為之前錯誤引用 `ConfigManager` 的 `save` 方法。
- 實作音訊快取機制，以減少快捷語音的重複合成時間。
- 調整 UI 日誌顯示，提高日誌視窗高度並過濾掉過於詳細的內部日誌訊息。

**所涉及的檔案和模組：**
- `src/app/app.py`
- `src/app/audio_engine.py`
- `src/ui/popups.py`
- `src/ui/main_window.py`

**所做的具體更改（高層次概述）：**
1.  **快捷鍵系統強化 (src/app/app.py):**
    *   修改 `_normalize_hotkey` 方法，使其能將修飾鍵（如 `shift`）和特殊鍵（如 `f1`）自動轉換為 `pynput` 期望的 `<key>` 格式（例如：`shift+z` -> `<shift>+z`, `f1` -> `<f1>`）。
    *   更新 `_start_hotkey_listener` 方法，確保在註冊快捷鍵前，所有快捷鍵字串都經過 `_normalize_hotkey` 處理，並使用 `_is_hotkey_valid_for_pynput` 進行更嚴格的驗證。
    *   將 `self.config.save_config()` 修正為 `self.config.save()`，解決 `ConfigManager` 的 `AttributeError`。
    *   將多個關於熱鍵註冊、驗證的冗餘日誌級別從 `INFO` 降級為 `DEBUG`。
2.  **音訊快取機制實作 (src/app/audio_engine.py):**
    *   在 `AudioEngine` 的 `__init__` 方法中新增 `self._audio_cache` 字典用於儲存音訊數據。
    *   新增 `_synth_edge_to_memory` 和 `_synth_pyttsx3_to_memory` 方法，用於將 Edge-TTS 和 pyttsx3 的合成結果直接輸出為記憶體中的 NumPy 數組，避免不必要的檔案 I/O。
    *   實作 `cache_phrase` 方法，根據短語內容及當前 TTS 設定生成快取鍵，並將合成的音訊（NumPy 數組及採樣率）存入 `_audio_cache`。
    *   修改 `_process_and_play_text` 方法，使其在處理播放請求時，優先檢查 `_audio_cache` 是否存在對應音訊，若有則直接使用，否則進行合成並存入快取。
    *   將多個關於模型載入、設備綁定的冗餘日誌級別從 `INFO` 降級為 `DEBUG`。
3.  **UI 與日誌調整：**
    *   在 `src/ui/main_window.py` 的 `_create_log_area` 方法中，為日誌視窗 (`QTextEdit`) 設定了 `setMinimumHeight(180)`，增加其可見高度。同時修正了一處 `self.log_text = QTextEdit()` 的重複定義。
    *   在 `src/ui/popups.py` 的 `QuickPhrasesWindow._save_and_close` 方法中，將觸發背景快取更新的日誌級別從 `INFO` 降級為 `DEBUG`。

**新增的依賴項或配置：**
- 無新的 Python 套件依賴。
- 配置檔案 `config.json` 中的快捷鍵字串格式將會自動更新為帶有尖括號的格式（例如 `shift+z` -> `<shift>+z`）。

**對於下一個階段的代理或開發者來說，需要了解的任何重要事項：**
- 儘管熱鍵問題和音訊快取已實現，但模型下載與解壓縮的錯誤 (來自前次使用者反饋的 "model files incomplete" 錯誤) 仍未解決。需要等待使用者提供新的日誌來診斷此問題。
- 由於 `pynput` 的特殊性，建議後續對熱鍵輸入的處理應始終使用 `_normalize_hotkey` 方法。

**生成日期：** 2025年11月25日
**生成者：** Gemini CLI Agent
---

## Agent Memory

(For Gemini Agent use. Records high-level context to maintain continuity.)

### Session: 2025-11-25

*   **Summary:**
    *   **Initial `TypeError` Fix:** Removed an unexpected `parent` argument from `QuickInputWindow` constructor in `src/app/app.py`.
    *   **Hotkey Editing Implementation:** Implemented missing hotkey editing logic in `src/app/app.py` (for the main quick input) and modified `src/ui/main_window.py` to make the hotkey edit button checkable, improving UX.
    *   **Quick Input Positioning:** Corrected quick input window's positioning to be screen-relative in `src/app/app.py` based on user settings.
    *   **`AttributeError` Fix:** Resolved `AttributeError: 'MainWindow' object has no attribute 'hotkey_label'` by replacing a button group with the expected `QLabel` in `_create_hotkey_card` in `src/ui/main_window.py`.
    *   **Robust Hotkey Validation:** Hardened the hotkey system to prevent crashes from invalid (e.g., modifier-only) hotkeys saved in the user's config. The validation in `_start_hotkey_listener` in `app.py` now also clears invalid keys from the configuration to prevent the issue from recurring.
    *   **Model Extraction Debugging:** Added detailed file logging to the `extract_tar_bz2` function in `src/utils/deps.py` to diagnose a "model files incomplete" error. Awaiting new logs from the user to analyze the archive's structure.
*   **Key Files Modified:** `src/app/app.py`, `src/ui/main_window.py`, `src/ui/popups.py`, `src/utils/deps.py`.
*   **Project Insight:** This `log.md` file serves as my session memory. Consistency between UI and logic is crucial. Hotkey validation must handle both setting and loading. When debugging file issues, adding logging to inspect intermediate states is an effective strategy.