import os
import sys
import asyncio
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox
import numpy as np
import json 

# 外部庫
import customtkinter as ctk
from pynput import keyboard
import sounddevice as sd
from pydub import AudioSegment

import edge_tts
import pyttsx3
import subprocess

# Windows 特定依賴
try:
    import comtypes.client
    from comtypes import CLSCTX_ALL
except ImportError:
    comtypes_installed = False
    print("Warning: 'comtypes' not installed.")
else:
    comtypes_installed = True

# =================================================================
# 設定常數
# =================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json") # 配置儲存檔案

CABLE_OUTPUT_HINT = "CABLE Input"     # 播放目標 (VB-CABLE 虛擬喇叭)
CABLE_INPUT_HINT = "CABLE Output"     # Discord 麥克風 (VB-CABLE 虛擬麥克風)

# --- VB-CABLE 安裝設置 ---
VB_CABLE_SETUP_EXE = "VBCABLE_Setup_x64.exe" 
# -------------------------

DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"
ENGINE_EDGE = "edge-tts"
ENGINE_PYTTX3 = "pyttsx3"

# =================================================================
# 主類別
# =================================================================
class LocalTTSPlayer:
    def __init__(self):
        # 1. 載入配置
        self._load_config()

        self.is_running = False
        self.current_engine = self._config.get("engine", ENGINE_EDGE)
        self.edge_voice = self._config.get("voice", DEFAULT_EDGE_VOICE)
        self.pyttsx3_voice_id = None 
        
        self.tts_rate = self._config.get("rate", 175)
        self.tts_volume = self._config.get("volume", 1.0)
        self.current_hotkey = self._config.get("hotkey", "<shift>+z") # 載入快捷鍵
        
        self.local_output_device_name = "Default"
        self._local_output_devices = {}
        self.cable_is_present = False

        self.hotkey_listener = None
        self.quick_input_window = None
        self._pyttsx3_engine = None
        self._pyttsx3_voices = []
        self._edge_voices = []

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self.setup_ui()

        threading.Thread(target=self._load_voices_and_devices_background, daemon=True).start()
        
    # ============================================================
    # 配置儲存與載入
    # ============================================================
    def _load_config(self):
        """從 config.json 載入配置。"""
        self._config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except Exception as e:
                self.log_message(f"載入配置檔失敗: {e}")

    def _save_config(self):
        """將目前設定儲存到 config.json。"""
        self._config["engine"] = self.current_engine
        
        # 儲存語音模型 (依據引擎)
        if self.current_engine == ENGINE_EDGE:
             self._config["voice"] = self.edge_voice
        elif self.pyttsx3_voice_id and self._pyttsx3_voices:
            # 儲存 Pyttsx3 的顯示名稱
            voice_obj = next((v for v in self._pyttsx3_voices if v.id == self.pyttsx3_voice_id), None)
            if voice_obj:
                 self._config["voice"] = voice_obj.name
            else:
                 self._config["voice"] = self._config.get("voice", "default")
        else:
             # 如果 Pyttsx3 語音尚未載入完成，保持原樣
             self._config["voice"] = self._config.get("voice", "default")
             
        self._config["rate"] = self.tts_rate
        self._config["volume"] = self.tts_volume
        self._config["hotkey"] = self.current_hotkey
        
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log_message(f"儲存配置檔失敗: {e}")

    # ============================================================
    # 驅動檢查與安裝 (保持不變)
    # ============================================================
    def _check_and_install_cable(self) -> bool:
        """檢查 VB-CABLE 是否存在，若無則引導安裝。回傳 False 表示應用程式應退出重啟。"""
        devices = sd.query_devices()
        cable_installed = any(CABLE_OUTPUT_HINT.upper() in d['name'].upper() for d in devices)

        if cable_installed:
            self.log_message("✅ VB-CABLE 驅動已存在，繼續載入。")
            self.cable_is_present = True
            return True

        self.log_message("🚨 未偵測到 VB-CABLE 驅動。準備啟動安裝程序引導...")
        setup_path = os.path.join(SCRIPT_DIR, VB_CABLE_SETUP_EXE)

        if not os.path.exists(setup_path):
            self.log_message(f"🚫 錯誤: 找不到安裝檔 {VB_CABLE_SETUP_EXE}。請手動下載並安裝。")
            return True

        def run_setup():
            try:
                result = messagebox.askyesno(
                    "VB-CABLE 安裝提示",
                    "TTS 語音輸入 Discord 需要 VB-CABLE 驅動程式。\n\n"
                    f"點擊 '是' 將啟動安裝程序 ({VB_CABLE_SETUP_EXE})，您可能需要授權**管理員權限**並點擊 **Install Driver**。\n"
                    "安裝後，請**重新啟動**本應用程式。",
                    icon='info'
                )
                if result:
                    subprocess.Popen(setup_path, shell=True) 
                    messagebox.showinfo(
                        "請注意",
                        "請在彈出的 VB-CABLE 視窗中點擊 **'Install Driver'** 完成安裝。\n"
                        "安裝完成後，請**手動關閉**本應用程式並重新啟動。"
                    )
                    self.root.after(0, self.on_closing)
                else:
                    self.log_message("使用者取消了 VB-CABLE 安裝。")
            except Exception as e:
                self.log_message(f"VB-CABLE 安裝執行錯誤: {e}")

        self.root.after(0, run_setup)
        return False

    # ============================================================
    # 初始化
    # ============================================================
    def _load_voices_and_devices_background(self):
        try:
            if not self._check_and_install_cable():
                return

            self._pyttsx3_engine = pyttsx3.init()
            self._pyttsx3_voices = self._pyttsx3_engine.getProperty("voices")
            asyncio.run(self._load_edge_voices())
            self._load_local_devices()
            
            self.root.after(0, self._update_ui_after_load) 

        except Exception as e:
            self.log_message(f"初始化錯誤: {e}")
            
    def _update_ui_after_load(self):
        """在載入完成後，更新 UI 元素 (必須在主線程執行)。"""
        
        # 根據載入的配置設定 UI 初始值
        self.engine_combo.set(self.current_engine)
        self.speed_slider.set(self.tts_rate)
        self.volume_slider.set(self.tts_volume)
        
        self._update_voice_combobox_items()
        self._update_local_device_combobox_items()
        
        # 更新 hotkey 欄位
        if hasattr(self, 'hotkey_entry'):
            self.hotkey_entry.delete(0, tk.END)
            self.hotkey_entry.insert(0, self.current_hotkey)
        
        if not self.cable_is_present:
            self.start_button.configure(
                text="啟動 (無 VB-CABLE)", 
                fg_color="gray", 
                hover_color="darkgray"
            )

    async def _load_edge_voices(self):
        try:
            vm = await edge_tts.VoicesManager.create()
            # 確保使用 self._edge_voices 而非 self._edge_voice_names
            # 只篩選中文語音 (Locale 以 zh- 開頭)
            self._edge_voices = [v for v in vm.voices if v.get("Locale", "").startswith("zh-")]
        except Exception as e:
            self.log_message(f"Edge TTS 載入失敗: {e}")

    def _load_local_devices(self):
        try:
            devices = sd.query_devices()
            output_devices = [d for d in devices if d['max_output_channels'] > 0]
            self._local_output_devices = {d['name']: d['index'] for d in output_devices}
            
            found_cable = False
            for d in output_devices:
                if CABLE_OUTPUT_HINT.upper() in d['name'].upper():
                    self.local_output_device_name = d['name']
                    self.cable_is_present = True
                    found_cable = True
                    break
                    
            if not found_cable:
                self.local_output_device_name = "未找到 VB-CABLE!"
                self.log_message("⚠️ 設備列表載入完成，但未偵測到 VB-CABLE。")
            else:
                self.log_message(f"✅ 已綁定輸出設備：{self.local_output_device_name}")
                
        except Exception as e:
            self.log_message(f"取得音效卡失敗: {e}")

    # ============================================================
    # UI
    # ============================================================
    def setup_ui(self):
        self.root = ctk.CTk()
        self.root.title("TTS 虛擬麥克風控制器 (VB-CABLE)")
        self.root.geometry("600x650")
        self.root.resizable(False, False)

        ctrl = ctk.CTkFrame(self.root)
        ctrl.pack(padx=20, pady=(20, 10), fill="x")
        self.start_button = ctk.CTkButton(ctrl, text="啟動", command=self.start_local_player)
        self.start_button.pack(side="left", padx=10, pady=10)
        self.stop_button = ctk.CTkButton(ctrl, text="停止", command=self.stop_local_player, state="disabled", fg_color="red")
        self.stop_button.pack(side="left", padx=10, pady=10)
        self.status_label = ctk.CTkLabel(ctrl, text="狀態: 未啟動", text_color="red")
        self.status_label.pack(side="right", padx=10)

        # 輸出設備
        out = ctk.CTkFrame(self.root)
        out.pack(padx=20, pady=10, fill="x")
        ctk.CTkLabel(out, text="輸出設備:", anchor="w").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.local_device_combo = ctk.CTkOptionMenu(out, values=[self.local_output_device_name])
        self.local_device_combo.set(self.local_output_device_name)
        self.local_device_combo.configure(state="disabled")
        self.local_device_combo.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(out, text=f"Discord 麥克風請設定為: {CABLE_INPUT_HINT} (虛擬麥克風)", text_color="cyan", font=ctk.CTkFont(size=12, weight="bold")).grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        
        out.columnconfigure(1, weight=1)

        # 語音與引擎
        sel = ctk.CTkFrame(self.root)
        sel.pack(padx=20, pady=10, fill="x")
        ctk.CTkLabel(sel, text="引擎:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.engine_combo = ctk.CTkOptionMenu(sel, values=[ENGINE_EDGE, ENGINE_PYTTX3], command=self._on_engine_change)
        self.engine_combo.set(self.current_engine)
        self.engine_combo.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(sel, text="語音:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        # 使用 OptionMenu，不可編輯
        self.voice_combo = ctk.CTkOptionMenu(sel, values=[DEFAULT_EDGE_VOICE], command=self._on_voice_change)
        self.voice_combo.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        sel.columnconfigure(1, weight=1)

        # 語速音量
        tts = ctk.CTkFrame(self.root)
        tts.pack(padx=20, pady=10, fill="x")
        ctk.CTkLabel(tts, text="語速:", width=100).grid(row=0, column=0, padx=10, sticky="w")
        self.speed_slider = ctk.CTkSlider(tts, from_=100, to=250, command=self.update_tts_settings)
        self.speed_slider.set(self.tts_rate)
        self.speed_slider.grid(row=0, column=1, sticky="ew", padx=10)
        self.speed_value_label = ctk.CTkLabel(tts, text=f"{self.tts_rate}", width=50) 
        self.speed_value_label.grid(row=0, column=2, sticky="e", padx=10)
        
        ctk.CTkLabel(tts, text="音量:", width=100).grid(row=1, column=0, padx=10, sticky="w")
        self.volume_slider = ctk.CTkSlider(tts, from_=0.5, to=1.0, command=self.update_tts_settings)
        self.volume_slider.set(self.tts_volume)
        self.volume_slider.grid(row=1, column=1, sticky="ew", padx=10)
        self.volume_value_label = ctk.CTkLabel(tts, text=f"{self.tts_volume:.2f}", width=50) 
        self.volume_value_label.grid(row=1, column=2, sticky="e", padx=10)

        tts.columnconfigure(1, weight=1)

        # Hotkey 設定 Frame
        hotkey_frame = ctk.CTkFrame(self.root)
        hotkey_frame.pack(padx=20, pady=10, fill="x")
        
        ctk.CTkLabel(hotkey_frame, text="全域快捷鍵:").grid(row=0, column=0, padx=10, sticky="w")
        
        self.hotkey_entry = ctk.CTkEntry(hotkey_frame)
        self.hotkey_entry.insert(0, self.current_hotkey)
        # 初始狀態為 disabled (鎖定)
        self.hotkey_entry.configure(state="disabled")
        self.hotkey_entry.grid(row=0, column=1, sticky="ew", padx=5)
        
        # 綁定 Enter 鍵來保存
        self.hotkey_entry.bind("<Return>", self._on_hotkey_change_entry)

        self.hotkey_edit_button = ctk.CTkButton(
            hotkey_frame, 
            text="編輯", 
            width=80,
            command=self._toggle_hotkey_edit
        )
        self.hotkey_edit_button.grid(row=0, column=2, sticky="e", padx=10)
        
        hotkey_frame.columnconfigure(1, weight=1)

        # 快捷鍵提示 
        info = ctk.CTkFrame(self.root)
        info.pack(padx=20, pady=(0, 10), fill="x")
        ctk.CTkLabel(info, text="請輸入 pynput 格式（如：<shift>+z）。點擊 '編輯' 後再輸入，然後按 Enter 或 '儲存'。", font=ctk.CTkFont(size=10)).pack(pady=2)


        # log
        log = ctk.CTkFrame(self.root)
        log.pack(padx=20, pady=10, fill="both", expand=True)
        # Log 文字大小改為 12
        self.log_text = ctk.CTkTextbox(log, height=8, font=("Consolas", 12))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ============================================================
    # Hotkey 處理 (編輯/鎖定邏輯)
    # ============================================================
    def _toggle_hotkey_edit(self):
        """切換快捷鍵輸入框的編輯狀態 (鎖定/解鎖)。"""
        if self.hotkey_entry.cget("state") == "disabled":
            # 狀態：鎖定 -> 解鎖
            self.hotkey_entry.configure(state="normal")
            self.hotkey_edit_button.configure(text="儲存", fg_color="green", hover_color="darkgreen")
            self.hotkey_entry.focus_set()
            self.hotkey_entry.select_range(0, tk.END) 
            self.log_message("▶️ 快捷鍵輸入框已解鎖，請輸入新快捷鍵...")
        else:
            # 狀態：解鎖 -> 鎖定 (即執行儲存動作)
            self._on_hotkey_change_entry()
    
    def _lock_hotkey_entry(self):
        """將快捷鍵輸入框鎖定。"""
        self.hotkey_entry.configure(state="disabled")
        self.hotkey_edit_button.configure(text="編輯", fg_color="#3B8ED4", hover_color="#36719F") # 恢復預設顏色

    def _update_hotkey_ui_and_save(self, hotkey_str):
        """更新 UI、保存配置並鎖定輸入框。"""
        self.current_hotkey = hotkey_str.lower()
        
        # 更新 UI
        self.hotkey_entry.delete(0, tk.END)
        self.hotkey_entry.insert(0, self.current_hotkey)
        
        # 鎖定輸入框
        self._lock_hotkey_entry()
        
        # 立即更新全局熱鍵監聽
        if self.is_running:
             self._start_hotkey_listener()
        
        self.log_message(f"✅ 快捷鍵已儲存並鎖定為: {self.current_hotkey}")
        self._save_config()

    def _on_hotkey_change_entry(self, event=None):
        """處理手動輸入快捷鍵後的保存。可以在按下 Enter 或點擊儲存按鈕時觸發。"""
        new_hotkey = self.hotkey_entry.get().strip().lower()
        
        if self.hotkey_entry.cget("state") == "disabled":
             # 如果是鎖定狀態，按 Enter 應無作用
             return
             
        if new_hotkey and new_hotkey != self.current_hotkey:
            self._update_hotkey_ui_and_save(new_hotkey)
        elif new_hotkey == self.current_hotkey:
            self._lock_hotkey_entry() # 沒有改變，但執行鎖定操作
        elif not new_hotkey:
            self.log_message("⚠️ 快捷鍵不能為空，已恢復為: " + self.current_hotkey)
            self.hotkey_entry.delete(0, tk.END)
            self.hotkey_entry.insert(0, self.current_hotkey)
            self._lock_hotkey_entry()

    # ============================================================
    # 控制 (保持不變)
    # ============================================================
    def start_local_player(self):
        if self.is_running:
            return
            
        if not self.cable_is_present:
            messagebox.showerror(
                "錯誤",
                "無法啟動：未偵測到 VB-CABLE 虛擬喇叭。\n"
                "請重新啟動應用程式以啟動安裝引導，或手動安裝後再試。"
            )
            self.log_message("🚫 無法啟動：未偵測到 VB-CABLE.")
            return

        self.is_running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_label.configure(text="狀態: 運行中", text_color="green")
        self._start_hotkey_listener()
        self.log_message("✅ 已啟動")

    def stop_local_player(self):
        if not self.is_running:
            return
        self.is_running = False
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_label.configure(text="狀態: 已停止", text_color="red")
        self.log_message("TTS 播放器已停止。")
        
    def _start_hotkey_listener(self):
        """啟動全域快捷鍵監聽。"""
        def on_hotkey():
            # 確保在主線程中呼叫 UI 函數
            if self.is_running:
                try:
                    self.root.after(0, self._show_quick_input)
                except Exception as e:
                    self.log_message(f"hotkey callback error: {e}")
        
        try:
            if self.hotkey_listener:
                self.hotkey_listener.stop()
                
            self.hotkey_listener = keyboard.GlobalHotKeys({self.current_hotkey: on_hotkey})
            self.hotkey_listener.start()
            self.log_message(f"全域快捷鍵 '{self.current_hotkey}' 已啟用")
        except Exception as e:
            self.log_message(f"快捷鍵 '{self.current_hotkey}' 啟動失敗: {e}。請檢查格式是否符合 pynput 要求。")

    # ============================================================
    # 播放 (保持不變)
    # ============================================================
    async def _synth_edge_to_file(self, text, path):
        rate_param = f"{int(round((self.tts_rate - 175) * (40 / 75))):+d}%"
        volume_param = f"{int((self.tts_volume - 1.0) * 100):+d}%"
        comm = edge_tts.Communicate(text, self.edge_voice, rate=rate_param, volume=volume_param)
        await comm.save(path)

    def _synth_pyttsx3_to_file(self, text, path):
        eng = self._pyttsx3_engine or pyttsx3.init()
        eng.setProperty("rate", self.tts_rate)
        eng.setProperty("volume", self.tts_volume)
        if self.pyttsx3_voice_id:
            eng.setProperty("voice", self.pyttsx3_voice_id)
        eng.save_to_file(text, path)
        eng.runAndWait()
        eng.stop()

    def _play_local(self, text):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        synth_suffix = ".mp3" if self.current_engine == ENGINE_EDGE else ".wav"
        fd, synth_path = tempfile.mkstemp(suffix=synth_suffix)
        os.close(fd)

        try:
            if self.current_engine == ENGINE_EDGE:
                self.log_message(f"生成 Edge TTS 音訊... {text[:20]}...")
                loop.run_until_complete(self._synth_edge_to_file(text, synth_path))
            else:
                self.log_message(f"生成 Pyttsx3 音訊... {text[:20]}...")
                self._synth_pyttsx3_to_file(text, synth_path)

            audio = AudioSegment.from_file(synth_path)
            samples = np.array(audio.get_array_of_samples())
            samples = samples.astype(np.float32) / (2 ** (8 * audio.sample_width - 1))

            device_id = self._local_output_devices.get(self.local_output_device_name)

            if device_id is None:
                self.log_message("⚠️ 找不到 VB-CABLE Input，改用預設裝置。")
                device_id = sd.default.device[1] 

            self.log_message(f"🔊 播放到設備 [{device_id}] {self.local_output_device_name}")
            sd.play(samples, samplerate=audio.frame_rate, device=device_id, blocking=True)
            sd.stop()
            self.log_message("✅ 播放完成。")
        except Exception as e:
            self.log_message(f"播放錯誤: {e}")
        finally:
            loop.close()
            if os.path.exists(synth_path):
                os.remove(synth_path)

    # ============================================================
    # 其他輔助
    # ============================================================
    def _on_engine_change(self, val):
        self.current_engine = val
        self.log_message(f"切換引擎: {self.current_engine}")
        self._update_voice_combobox_items()
        self._save_config()

    def _on_voice_change(self, choice):
        val = choice
        if self.current_engine == ENGINE_EDGE:
            self.edge_voice = val or DEFAULT_EDGE_VOICE
        else:
            # 找到並設定 pyttsx3_voice_id
            if self._pyttsx3_voices:
                for v in self._pyttsx3_voices:
                    if v.name == val:
                        self.pyttsx3_voice_id = v.id
                        break
        self.log_message(f"選定語音: {val}")
        self._save_config()

    def _update_voice_combobox_items(self):
        def upd():
            # 必須在 UI 主線程執行
            if self.current_engine == ENGINE_EDGE:
                values = [DEFAULT_EDGE_VOICE] + [v["ShortName"] for v in self._edge_voices]
                # 由於改用 OptionMenu，只能在 configure 時傳入所有值
                self.voice_combo.configure(values=values)
                # 嘗試載入上次儲存的 Edge 語音
                self.voice_combo.set(self.edge_voice if self.edge_voice in values else DEFAULT_EDGE_VOICE)
            else:
                names = [v.name for v in self._pyttsx3_voices]
                self.voice_combo.configure(values=names)
                
                # 嘗試載入上次儲存的 Pyttsx3 語音
                loaded_name = self._config.get("voice")
                if loaded_name in names:
                    self.voice_combo.set(loaded_name)
                    # 同時設定 pyttsx3_voice_id
                    for v in self._pyttsx3_voices:
                         if v.name == loaded_name:
                             self.pyttsx3_voice_id = v.id
                             break
                else:
                    self.voice_combo.set(names[0] if names else "default")
                    
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, upd)
        else:
            upd()
            
    def _update_local_device_combobox_items(self):
        def upd():
            device_names = list(self._local_output_devices.keys())
            if not device_names:
                device_names = ["Default (無可用設備)"]
                
            self.local_device_combo.configure(values=device_names)
            
            if self.local_output_device_name not in device_names:
                self.local_output_device_name = device_names[0] if device_names else "Default"
            
            self.local_device_combo.set(self.local_output_device_name)
            
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, upd)
        else:
            upd()

    def update_tts_settings(self, _):
        """更新語速和音量數值，並儲存配置。"""
        self.tts_rate = int(self.speed_slider.get())
        self.tts_volume = round(self.volume_slider.get(), 2)
        
        # UI 顯示更新
        self.speed_value_label.configure(text=f"{self.tts_rate}")
        self.volume_value_label.configure(text=f"{self.tts_volume:.2f}")

        self._save_config()

    def log_message(self, msg):
        def upd():
            self.log_text.insert(tk.END, f"{msg}\n")
            self.log_text.see(tk.END)
        self.root.after(0, upd)

    def _show_quick_input(self):
        if self.quick_input_window and self.quick_input_window.winfo_exists():
            try:
                self.quick_input_window.lift()
                self.quick_input_window.focus_force()
            except:
                pass
            return

        win = ctk.CTkToplevel(self.root)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.95)
        # 初始化焦點建立狀態旗標
        win._focus_established = False
        
        # 調整位置到工作列上方右側
        w, h = 420, 38
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        # 距離右邊和底部 (工作列上方) 20 像素
        x = int(screen_w - w - 20)
        # 由於我們無法直接獲取工作列高度，暫時使用距離底邊 50px
        y = int(screen_h - h - 50) 
        win.geometry(f"{w}x{h}+{x}+{y}")

        entry = ctk.CTkEntry(win, font=("Arial", 14), height=h)
        entry.pack(fill="both", expand=True, padx=2, pady=2)

        def close_window_if_lost_focus(event=None):
            """延遲檢查並關閉視窗，如果它真的失去焦點。"""
            
            def check_and_close():
                if not win.winfo_exists():
                    return
                
                # 只有當焦點穩定建立後，才啟用自動關閉
                if not win._focus_established:
                    return

                # **關鍵修正**: 檢查目前擁有焦點的元件是否仍屬於這個 Toplevel 視窗。
                # 這比單純檢查 entry 更可靠。
                current_focus_widget = win.focus_get()
                
                # 獲取 Toplevel 的頂層視窗物件
                toplevel = win.winfo_toplevel()

                # 檢查目前焦點是否在 entry 上，或者焦點是否在 Toplevel 視窗本身
                # 如果目前的焦點不是 entry 且不是頂層視窗本身，則認為失去焦點
                # 由於 entry 是 win 的子元件，也可以用 try-except 獲取 winfo_parent
                
                is_focused_on_self = (
                    current_focus_widget is entry or 
                    current_focus_widget is win or 
                    current_focus_widget is toplevel or
                    toplevel.winfo_id() == win.winfo_id() # Toplevel 應該是其自身的頂層
                )
                
                # 如果焦點不在任何屬於這個視窗的元件上，或者 winfo_name 顯示焦點在外部
                # 這裡最簡單可靠的方法就是檢查：焦點是否仍然是 entry。
                # 如果 `current_focus_widget` 的頂層不是 `win`，或它不是 `entry`
                
                # 使用 `try-except` 和 `winfo_toplevel()` 來判斷焦點是否真的跑走了
                try:
                    # 獲取目前焦點元件的頂層視窗
                    focus_toplevel = current_focus_widget.winfo_toplevel()
                    focus_is_on_self_toplevel = (focus_toplevel is win)
                except Exception:
                    # 如果獲取不到頂層，可能是焦點在外部應用程式，但這也不絕對可靠
                    focus_is_on_self_toplevel = False
                    
                # 最終檢查: 如果焦點建立穩定，且目前沒有任何屬於這個視窗的元件有焦點
                if win._focus_established and current_focus_widget != entry and current_focus_widget != win:
                    self.log_message("輸入框失去焦點，自動關閉。")
                    win.destroy()
            
            # 延遲檢查 150ms，給予系統充足的時間處理焦點事件
            win.after(150, check_and_close) 

        
        def secure_focus():
            """優化焦點搶奪邏輯，並設置焦點穩定標誌，然後綁定 FocusOut。"""
            if not win.winfo_exists():
                return
            try:
                # 確保窗口在最上層
                win.lift()
                # 強制焦點
                win.focus_force()
                # 設定輸入框焦點
                entry.focus_set() 
                # 全選內容
                entry.select_range(0, tk.END) 
                
                # **修正**: 延遲設定 `_focus_established` 旗標，給予系統時間穩定焦點
                # 讓 FocusOut 在短時間內被忽略
                
                # 綁定 FocusOut 事件到視窗和輸入框
                # 任何一個失去焦點，都觸發檢查
                win.bind('<FocusOut>', close_window_if_lost_focus)
                entry.bind('<FocusOut>', close_window_if_lost_focus)
                
                # 延遲 300ms 後再允許 FocusOut 關閉視窗
                win.after(300, lambda: setattr(win, '_focus_established', True))
                
            except Exception as e:
                self.log_message(f"focus 嘗試失敗: {e}")

        # 延遲執行，確保視窗已準備好接受焦點 (多試幾次增加成功率)
        # 第一次嘗試 50ms
        win.after(50, secure_focus)
        # 第二次嘗試 200ms
        win.after(200, secure_focus)


        def send(event=None):
            text = entry.get().strip()
            if text:
                threading.Thread(target=self._play_local, args=(text,), daemon=True).start()
            win.destroy()

        # 綁定 Enter 和 Esc 鍵來關閉視窗
        entry.bind("<Return>", send)
        entry.bind("<Escape>", lambda e: win.destroy())

        self.quick_input_window = win


    def on_closing(self):
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ============================================================
# 主程式
# ============================================================
if __name__ == "__main__":
    if not sys.platform.startswith("win"):
        messagebox.showerror("錯誤", "僅支援 Windows 並需安裝 VB-CABLE。")
        sys.exit()
    app = LocalTTSPlayer()
    app.run()