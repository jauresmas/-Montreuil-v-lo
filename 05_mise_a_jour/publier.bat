@echo off
rem Publication apres validation metier : archive la version en ligne puis republie.
chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
set /p REFERENT="Nom et service du referent qui valide : "
if "%REFERENT%"=="" (echo Publication annulee : referent obligatoire. & pause & exit /b 1)
.venv\Scripts\python.exe 05_mise_a_jour\maj_annuelle.py --publier --valide-par "%REFERENT%"
pause
