@echo off
setlocal
cd /d "%~dp0"
python -m streamlit run app.py --server.headless true --server.port 8501
pause
