@echo off
chcp 65001 > NUL
cd /d "%~dp0"

REM --- 1. Get version number ---
set /p APP_VERSION="Enter the version for this build (e.g., 1.2.3): "
if not defined APP_VERSION (
    echo [ERROR] No version number provided. Aborting build.
    pause
    exit /b 1
)
echo [INFO] Building version: %APP_VERSION%

REM --- 2. Clean up old files ---
echo [CLEAN] Cleaning up old build files...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "install" rmdir /s /q "install"
mkdir "install"

REM --- 3. Build with PyInstaller ---
echo [BUILD] Building with PyInstaller...
pyinstaller JuMouth.spec --noconfirm
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed!
    pause
    exit /b 1
)

REM --- 4. Build installer with Inno Setup (Moved Up) ---
echo [INSTALLER] Creating Windows installer...

setlocal enabledelayedexpansion

set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "!ISCC_PATH!" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"

if not defined ISCC_PATH (
    echo [WARN] Inno Setup compiler (ISCC.exe) not found.
    echo        Please install Inno Setup.
    echo [WARN] Skipping installer creation.
    goto :skip_installer
)

echo [INFO] Using Inno Setup compiler: "!ISCC_PATH!"
"!ISCC_PATH!" "JuMouth_setup.iss" /DAppVersion=%APP_VERSION%
if !errorlevel! neq 0 (
    echo [ERROR] Failed to create installer!
    pause
    exit /b 1
)
echo [INSTALLER] Installer created successfully.

endlocal

:skip_installer

REM --- 5. Assemble the final directory structure for GitHub Release ---
echo [ASSEMBLE] Assembling final application structure for release...
set "MAIN_APP_DIR=dist\JuMouth"
set "WIZARD_DIR=dist\update_wizard"
set "INTERNAL_DIR=%MAIN_APP_DIR%_internal"

if not exist "%WIZARD_DIR%" (
    echo [WARN] update_wizard directory not found, skipping assembly for release.
    goto :skip_assembly
)

if not exist "%INTERNAL_DIR%" mkdir "%INTERNAL_DIR%"
move "%WIZARD_DIR%" "%INTERNAL_DIR%"
echo [ASSEMBLE] Final structure assembled successfully.

REM --- Add a delay to prevent "Access Denied" errors ---
echo [INFO] Waiting for file handles to be released...
timeout /t 2 /nobreak > NUL

REM --- Zip _internal folder ---
echo [ZIP] Zipping _internal folder for GitHub Release...
set "INTERNAL_DIR_TO_ZIP=%MAIN_APP_DIR%_internal"
set "INTERNAL_ZIP=%MAIN_APP_DIR%_internal.zip"

if exist "%INTERNAL_DIR_TO_ZIP%" (
    powershell -command "Compress-Archive -Path '%INTERNAL_DIR_TO_ZIP%\*' -DestinationPath '%INTERNAL_ZIP%'"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create _internal.zip! Check for powershell errors above.
        pause
        exit /b 1
    )
    rmdir /s /q "%INTERNAL_DIR_TO_ZIP%"
    echo [ZIP] _internal.zip created and _internal folder removed.
) else (
    echo [WARN] _internal folder not found, skipping zipping.
)

:skip_assembly

REM --- 6. Create manifest.json ---
echo [MANIFEST] Creating manifest.json for partial updates...
python create_manifest.py "dist\JuMouth" "%APP_VERSION%"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create manifest.json!
    pause
    exit /b 1
)
echo [MANIFEST] manifest.json created successfully.


echo.
echo [SUCCESS] All tasks completed successfully!
echo.
echo [RELEASE FILES]
echo   - Files for the GitHub Release are in the 'dist\JuMouth' folder.
echo   - Upload *all files* from this folder (including manifest.json and _internal.zip) as release assets.
echo.
echo [INSTALLER]
echo   - The Windows installer is in the 'install' folder.
echo.
pause