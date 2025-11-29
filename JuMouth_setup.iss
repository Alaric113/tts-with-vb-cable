; JuMouth Inno Setup Script
; -- 由 Gemini Code Assist 生成 --

#define MyAppVersion "1.0.0" ; 預設版本，可被命令列覆寫

[Setup]
; 註：AppId 是應用程式的唯一標識符。建議為每個新應用生成一個新的 GUID。
; 你可以在 Inno Setup 編譯器的 "Tools" -> "Generate GUID" 中生成。
AppId={{F2A4B6E0-1C3D-4B7A-9F2E-5A8D6F0C1B9A}}
AppName=JuMouth TTS
AppVersion={#MyAppVersion}
AppPublisher=Alaric113
AppPublisherURL=https://github.com/Alaric113/tts-with-vb-cable
AppSupportURL=https://github.com/Alaric113/tts-with-vb-cable/issues
AppUpdatesURL=https://github.com/Alaric113/tts-with-vb-cable/releases

; 預設安裝目錄。{localappdata} 會自動解析為 "C:\Users\<使用者>\AppData\Local"
; 這與 config.json 和 ffmpeg 的儲存位置一致。
DefaultDirName={localappdata}\JuMouth
; 因為是安裝到使用者目錄，所以不需要管理員權限。
PrivilegesRequired=lowest
; 由於路徑是固定的，直接隱藏目錄選擇頁面，簡化安裝流程。
DisableDirPage=yes
DefaultGroupName=JuMouth TTS

; 輸出設定
OutputDir=.\install
OutputBaseFilename=JuMouth_v{#MyAppVersion}_setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

; 安裝程式圖示
SetupIconFile=icon.ico

; 解除安裝程式圖示
UninstallDisplayIcon={app}\JuMouth.exe

[Languages]
Name: "chinesetraditional"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"
; [Languages]
; Name: "chinesetraditional"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"
; 註：暫時註解掉此區塊，讓安裝程式預設使用英文，以解決找不到語言檔案的問題。

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 這裡是最關鍵的部分：
; Source 指定了 PyInstaller 打包後產生的資料夾中的所有內容。
; DestDir 指定了它們將被安裝到使用者選擇的路徑 ({app})。
; Flags: recursesubdirs 表示遞迴包含所有子目錄； createallsubdirs 表示在目標位置創建所有子目錄。
Source: "dist\JuMouth\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; 注意：請確保在執行此腳本前，你已經運行了 `pyinstaller JuMouth.spec`
; 並且 `dist\JuMouth` 資料夾已經存在。

[Icons]
; 開始功能表捷徑
Name: "{group}\JuMouth TTS"; Filename: "{app}\JuMouth.exe"
Name: "{group}\{cm:UninstallProgram,JuMouth TTS}"; Filename: "{uninstallexe}"

; 桌面捷徑 (根據使用者在 Tasks 頁面的選擇)
Name: "{autodesktop}\JuMouth TTS"; Filename: "{app}\JuMouth.exe"; Tasks: desktopicon

[Run]
; 安裝完成後，提供一個選項讓使用者立即執行應用程式。
Filename: "{app}\JuMouth.exe"; Description: "{cm:LaunchProgram,JuMouth TTS}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 解除安裝時，刪除整個應用程式目錄，包括使用者產生的 config.json 和 ffmpeg。
Type: filesandordirs; Name: "{app}"