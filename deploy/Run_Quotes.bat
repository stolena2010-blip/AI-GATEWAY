@echo off
echo Starting DrawingAI Pro — Quotes Profile
cd /d "%~dp0.."
call .venv\Scripts\activate
python run_pipeline.py --profile quotes
pause
