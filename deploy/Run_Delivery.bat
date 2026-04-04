@echo off
echo Starting DrawingAI Pro — Delivery Profile
cd /d "%~dp0.."
call .venv\Scripts\activate
python run_pipeline.py --profile delivery
pause
