<h3 align="center" tabindex="-1" class="heading-element" dir="auto">OutputControl</h3>
<p align="center"><img width="360" height="360" alt="outputcontrol_icon" src="https://github.com/user-attachments/assets/cd6fabae-c0fe-4066-ba63-349793a0b611" /></p><br>

## Features
- Change audio outputs and inputs from any monitor without the need to open settings

## Why?
- I often find myself needing to adjust audio inputs/outputs and volume on my PC while I have my PlayStation displaying on my main monitor. This usually forces me to open the settings app or change my main display's output to my PC; this program aims to solve this problem.
<p align="center"><img width="240" height="240" alt="image" src="https://github.com/user-attachments/assets/97089f6c-79f6-4038-a6a1-60e5d85202d8" /></p><br>

## Requirements
- Python 3.13.1 or higher
  
## Getting Started
- Download and install Python and all required packages.
- Download and run .exe file
- Left click in the taskbar tray to open menu, right click to change settings or close program
- OPTIONAL: Add shortcut to startup

## Building
- If you would like to build the program yourself, download the repo and run the following command while inside the directory:
```py -3.12 -m nuitka --mingw64 --enable-plugin=pyqt5 --standalone --onefile --windows-console-mode=disable --windows-icon-from-ico=outputcontrol_icon.ico --include-data-files=outputcontrol_icon.png=outputcontrol_icon.png --include-data-files=config.ini=config.ini OutputControl.py
