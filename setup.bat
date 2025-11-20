@echo off
python3 -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
echo Virtual environment created and dependencies installed!
echo Run "venv\Scripts\activate" to activate the environment