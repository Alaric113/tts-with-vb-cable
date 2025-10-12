@echo off
chcp 65001 > NUL

REM 將當前目錄切換到批次檔所在的目錄，確保相對路徑的正確性
cd /d "%~dp0"
echo [Build Script] 當前工作目錄已設定為: %cd%

echo [Build Script] 清理舊的打包檔案...
if exist "build" (
    echo [Build Script] 正在刪除 build 資料夾...
    rmdir /s /q build
)
if exist "dist" (
    echo [Build Script] 正在刪除 dist 資料夾...
    rmdir /s /q dist
)
echo [Build Script] 清理完成。
echo.

echo [Build Script] ========== 步驟 1: 打包更新精靈 (update_wizard) ==========
pyinstaller update_wizard.spec
if %errorlevel% neq 0 (
    echo [Build Script] !! 錯誤: 打包 update_wizard 失敗。請檢查上面的錯誤訊息。
    pause
    exit /b 1
)
echo [Build Script] ========== 步驟 1 完成。 ==========
echo.

echo [Build Script] ========== 步驟 2: 打包主程式 (JuMouth) ==========
pyinstaller JuMouth.spec
if %errorlevel% neq 0 (
    echo [Build Script] !! 錯誤: 打包 JuMouth 失敗。請檢查上面的錯誤訊息。
    pause
    exit /b 1
)
echo [Build Script] ========== 步驟 2 完成。 ==========
echo.

echo [Build Script] ========== 步驟 3: 組合最終應用程式 ==========
echo [Build Script] 正在建立目標資料夾: dist\JuMouth\_internal\update_wizard
mkdir "dist\JuMouth\_internal"
mkdir "dist\JuMouth\_internal\update_wizard"

echo [Build Script] 正在將更新精靈複製到主程式目錄中...
xcopy "dist\update_wizard" "dist\JuMouth\_internal\update_wizard" /E /I /Y
if %errorlevel% neq 0 (
    echo [Build Script] !! 錯誤: 複製 update_wizard 失敗。
    pause
    exit /b 1
)
echo [Build Script] ========== 步驟 3 完成。 ==========
echo.

echo [Build Script] ========== 步驟 4: 建立更新用的 ZIP 壓縮檔 ==========
set ZIP_FILENAME=JuMouth_update.zip
if exist "%ZIP_FILENAME%" (
    del "%ZIP_FILENAME%"
)
echo [Build Script] 正在壓縮 'dist\JuMouth' 的內容到 %ZIP_FILENAME%...
powershell -command "Compress-Archive -Path 'dist\JuMouth\*' -DestinationPath '%ZIP_FILENAME%'"
if %errorlevel% neq 0 (
    echo [Build Script] !! 錯誤: 建立 ZIP 壓縮檔失敗。
    pause
    exit /b 1
)
echo [Build Script] ========== 步驟 4 完成。 ==========
echo.

echo [Build Script] >>> 所有打包工作已成功完成！ <<<
echo [Build Script] 最終的應用程式位於 'dist\JuMouth' 資料夾中。