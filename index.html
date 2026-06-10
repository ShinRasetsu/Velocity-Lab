@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

:: --- CONFIGURATION ---
SET REPO_DIR=%~dp0
SET REMOTE_URL=https://github.com/ShinRasetsu/Velocity-Lab.git
cd /d "%REPO_DIR%"

echo [SYSTEM] Initializing Velocity-Lab PWA Cloud Sync...

:: --- GIT INITIALIZATION FAILSAVE ---
if not exist ".git" (
    echo [LOG] Local Git repository not found. Initializing...
    git init
    git branch -M main
)

:: --- REMOTE CONFIGURATION ---
git remote -v | findstr "origin" >nul
if %ERRORLEVEL% NEQ 0 (
    echo [LOG] Remote 'origin' missing. Binding to %REMOTE_URL%...
    git remote add origin %REMOTE_URL%
) else (
    :: Force URL update in case it is still pointing to an old MotoNexus repository
    git remote set-url origin %REMOTE_URL%
)

:: --- BRANCH DETECTION ---
:: Suppress stderr in case rev-parse fails on a completely empty, commit-less repository
for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set CURRENT_BRANCH=%%i

:: Fallback if branch is empty or in detached HEAD state
if "!CURRENT_BRANCH!"=="" set CURRENT_BRANCH=main
if "!CURRENT_BRANCH!"=="HEAD" set CURRENT_BRANCH=main

echo [LOG] Detected active branch: !CURRENT_BRANCH!

:: --- DETERMINISTIC TIMESTAMPING ---
:: Extracts YYYYMMDDHHMMSS format regardless of Windows OS regional locale settings
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set mydate=%datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2%
set mytime=%datetime:~8,2%:%datetime:~10,2%:%datetime:~12,2%
SET COMMIT_MSG=Velocity-Lab PWA Update: !mydate! [!mytime!]

:: --- GIT PIPELINE ---
echo [LOG] Staging PWA telemetry and UI payload...
git add .

:: Check for changes before committing
git diff-index --quiet HEAD -- 2>nul
if %ERRORLEVEL% NEQ 0 (
    git commit -m "!COMMIT_MSG!"
    echo [LOG] Committing payload: "!COMMIT_MSG!"
) else (
    echo [INFO] No changes detected. Proceeding to remote sync check...
)

:: Force upstream tracking (-u) critical for the first deployment to a new repo
echo [LOG] Pushing to origin/!CURRENT_BRANCH!...
git push -u origin !CURRENT_BRANCH!

:: --- ERROR HANDLING ---
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [CRITICAL] Sync failed. 
    echo [CHECK] 1. GitHub Authentication Active? 2. Network? 3. Merge conflicts present?
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Velocity-Lab PWA Cloud Sync Complete.
timeout /t 3 >nul