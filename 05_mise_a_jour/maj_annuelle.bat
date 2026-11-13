@echo off
rem Campagne annuelle : collecte, traitement, controle qualite, rapport d'ecarts.
rem La publication se fait ensuite avec publier.bat apres validation metier.
chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
if not exist .venv\Scripts\python.exe (
  echo Creation de l'environnement Python...
  python -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.txt
)
.venv\Scripts\python.exe 05_mise_a_jour\maj_annuelle.py %*
pause
