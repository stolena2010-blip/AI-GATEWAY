@echo off
echo Starting DrawingAI Pro — Orders Profile
cd /d "%~dp0.."
call .venv\Scripts\activate
python run_pipeline.py --profile orders
pause
