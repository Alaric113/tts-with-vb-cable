@echo off
chcp 65001 > NUL

REM 將當前目錄切換到批次檔所在的目錄，確保相對路徑的正確性
cd /d "%~dp0"

echo [BUILD] 正在清理舊的建置檔案...
if exist "dist" (
    rmdir /s /q "dist"
)
if exist "build" (
    rmdir /s /q "build"
)

echo [BUILD] 開始使用 PyInstaller 進行打包...
pyinstaller JuMouth.spec

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] PyInstaller 打包失敗！
    pause
    exit /b 1
)

echo.
echo [BUILD] 打包成功，等待檔案釋放...
REM 加入一個短暫延遲，防止壓縮時檔案被鎖定
timeout /t 2 /nobreak > NUL

echo [BUILD] 現在開始壓縮檔案以供發布...

set ZIP_FILENAME=JuMouth_update.zip
if exist "%ZIP_FILENAME%" (
    del "%ZIP_FILENAME%"
)

echo [BUILD] 正在壓縮 'dist\JuMouth' 的內容到 %ZIP_FILENAME%...
powershell -command "Compress-Archive -Path 'dist\JuMouth\*' -DestinationPath '%ZIP_FILENAME%'"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] 建立 ZIP 壓縮檔失敗！請確認 PowerShell 是否可正常運作。
    pause
    exit /b 1
)

echo.
echo [SUCCESS] 所有工作已成功完成！
echo 執行檔位於 'dist\JuMouth' 資料夾中。
echo 更新用的壓縮檔為 '%ZIP_FILENAME%'。
pause