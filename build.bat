@echo off
echo ============================================
echo  Nucleus - Build completo
echo ============================================
echo.

:: PyInstaller
echo [1/2] Gerando executavel com PyInstaller...
pyinstaller nucleus.spec --noconfirm
if %errorlevel% neq 0 (
    echo ERRO: PyInstaller falhou.
    pause
    exit /b 1
)
echo.

:: Inno Setup - tenta os caminhos mais comuns de instalacao
echo [2/2] Gerando instalador com Inno Setup...
set ISCC=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"

if %ISCC%=="" (
    echo ERRO: Inno Setup nao encontrado nos caminhos padrao.
    echo Abra nucleus_installer.iss manualmente no Inno Setup IDE.
    pause
    exit /b 1
)

%ISCC% nucleus_installer.iss
if %errorlevel% neq 0 (
    echo ERRO: Inno Setup falhou.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Pronto! Instalador gerado em:
echo  dist\installer\NucleusInstaller.exe
echo ============================================
pause
