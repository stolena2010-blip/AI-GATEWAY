@echo off
echo Starting DrawingAI Pro — Invoices Profile
cd /d "%~dp0.."
call .venv\Scripts\activate
python run_pipeline.py --profile invoices
pause
