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

REM --- NEW: Assemble the final directory structure ---
echo [ASSEMBLE] Assembling final application structure...
set MAIN_APP_DIR="dist\JuMouth"
set WIZARD_DIR="dist\update_wizard"
set INTERNAL_DIR_PARENT="%MAIN_APP_DIR%\"
set INTERNAL_DIR="%MAIN_APP_DIR%\_internal"
set FINAL_WIZARD_PATH="%INTERNAL_DIR%\update_wizard"

if not exist %WIZARD_DIR% (
    echo [ERROR] PyInstaller did not create the update_wizard directory.
    pause
    exit /b 1
)

echo [ASSEMBLE] Creating _internal directory.
mkdir %INTERNAL_DIR%
echo [ASSEMBLE] Moving update_wizard into _internal.
move %WIZARD_DIR% %INTERNAL_DIR%
echo [ASSEMBLE] Final structure assembled successfully.

REM --- Zip _internal folder ---
echo [ZIP] Zipping _internal folder for GitHub Release...
set INTERNAL_DIR_TO_ZIP="dist\JuMouth\_internal"
set INTERNAL_ZIP="dist\JuMouth\_internal.zip"

if exist %INTERNAL_DIR_TO_ZIP% (
    powershell -command "Compress-Archive -Path '%INTERNAL_DIR_TO_ZIP%\*' -DestinationPath '%INTERNAL_ZIP%'"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create _internal.zip!
        pause
        exit /b 1
    )
    rmdir /s /q %INTERNAL_DIR_TO_ZIP%
    echo [ZIP] _internal.zip created and _internal folder removed.
) else (
    echo [ZIP] _internal folder not found, skipping zipping.
)

REM --- 4. Create manifest.json ---
echo [MANIFEST] Creating manifest.json for partial updates...
python create_manifest.py "dist\JuMouth" "%APP_VERSION%"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create manifest.json!
    pause
    exit /b 1
)
echo [MANIFEST] manifest.json created successfully.

REM --- 5. Build installer with Inno Setup ---
echo [INSTALLER] Creating Windows installer...

REM Check for Inno Setup compiler in standard locations
set "ISCC_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"

if not defined ISCC_PATH (
    echo [WARN] Inno Setup compiler (ISCC.exe) not found.
    echo        Please install Inno Setup or add its path to the build script.
    echo [WARN] Skipping installer creation.
    goto :skip_installer
)

echo [INFO] Using Inno Setup compiler: "%ISCC_PATH%"
REM Pass version number to Inno Setup script using /D
"%ISCC_PATH%" "JuMouth_setup.iss" /DAppVersion=%APP_VERSION%
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create installer!
    pause
    exit /b 1
)
echo [INSTALLER] Installer created successfully.

:skip_installer

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
