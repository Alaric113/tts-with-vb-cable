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
REM "ISCC.exe" is the Inno Setup command line compiler.
REM Check standard installation paths.
set "ISCC_PATH_X86=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set "ISCC_PATH_X64=C:\Program Files\Inno Setup 6\ISCC.exe"

if exist "%ISCC_PATH_X86%" (
    set "ISCC_PATH=%ISCC_PATH_X86%"
) else if exist "%ISCC_PATH_X64%" (
    set "ISCC_PATH=%ISCC_PATH_X64%"
) else (
    echo [WARN] Inno Setup compiler (ISCC.exe) not found.
    echo        Please install Inno Setup or correct the ISCC_PATH in build.bat.
    echo [WARN] Skipping installer creation.
    goto :skip_installer
)

echo [INFO] Using Inno Setup compiler: %ISCC_PATH%
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
echo   - Upload *all files* from this folder (including manifest.json) as release assets.
echo.
echo [INSTALLER]
echo   - The Windows installer is in the 'install' folder.
echo.
pause
