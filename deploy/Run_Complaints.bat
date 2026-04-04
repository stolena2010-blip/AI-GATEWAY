@echo off
echo Starting DrawingAI Pro — Complaints Profile
cd /d "%~dp0.."
call .venv\Scripts\activate
python run_pipeline.py --profile complaints
pause
