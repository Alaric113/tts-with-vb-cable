
@echo off
chcp 65001 > NUL
echo [橘Mouth 更新程式] 正在等待主程式關閉...
set EXE_NAME=JuMouth.exe
:wait_loop
tasklist /FI "IMAGENAME eq %EXE_NAME%" | find /I "%EXE_NAME%" > NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak > NUL
    goto wait_loop
)
echo [橘Mouth 更新程式] 正在解壓縮並覆蓋檔案...
powershell -command "Expand-Archive -Path 'C:\Users\User\Documents\GitHub\tts-with-vb-cable\dist\JuMouth\update.zip' -DestinationPath 'C:\Users\User\Documents\GitHub\tts-with-vb-cable\dist\JuMouth' -Force"
echo [橘Mouth 更新程式] 清理暫存檔案...
del "C:\Users\User\Documents\GitHub\tts-with-vb-cable\dist\JuMouth\update.zip"
echo [橘Mouth 更新程式] 正在重新啟動...
start "" "C:\Users\User\Documents\GitHub\tts-with-vb-cable\dist\JuMouth\JuMouth.exe"
(goto) 2>NUL & del "%~f0"
