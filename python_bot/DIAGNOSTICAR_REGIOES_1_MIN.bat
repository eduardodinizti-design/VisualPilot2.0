@echo off
cd /d "%~dp0"
python coletar_sessao.py --minutos 1 --amostras
pause
