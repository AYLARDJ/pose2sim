"""
Build script for creating Pose2Sim GUI executable.

Usage:
    pip install pyinstaller flask pywebview toml
    python build_exe.py

This will create a standalone .exe in the dist/ folder.
"""
import os
import sys
import subprocess
from pathlib import Path

def build():
    # Get the directory of this script
    base_dir = Path(__file__).parent
    gui_dir = base_dir / 'GUI'
    
    # PyInstaller command
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name=Pose2Sim',
        '--onedir',          # Use onedir for faster startup
        '--windowed',        # No console window
        '--noconfirm',       # Overwrite output without asking
        
        # Icon
        f'--icon={gui_dir / "assets" / "Pose2Sim_favicon.ico"}',
        
        # Add data files
        f'--add-data={gui_dir / "static"}{os.pathsep}GUI/static',
        f'--add-data={gui_dir / "assets"}{os.pathsep}GUI/assets',
        f'--add-data={gui_dir / "cache"}{os.pathsep}GUI/cache',
        f'--add-data={gui_dir / "templates_toml"}{os.pathsep}GUI/templates_toml',
        f'--add-data={gui_dir / "tabs"}{os.pathsep}GUI/tabs',
        f'--add-data={gui_dir / "blur.py"}{os.pathsep}GUI',
        
        # Hidden imports that PyInstaller may miss
        '--hidden-import=flask',
        '--hidden-import=toml',
        '--hidden-import=PIL',
        '--hidden-import=cv2',
        '--hidden-import=numpy',
        '--hidden-import=tkinter',
        '--hidden-import=tkinter.filedialog',
        '--hidden-import=tkinter.messagebox',
        
        # Try to import webview (optional)
        '--hidden-import=webview',
        
        # Entry point
        str(gui_dir / 'main.py'),
    ]
    
    print("=" * 60)
    print("Building Pose2Sim GUI executable...")
    print("=" * 60)
    print(f"Command: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, cwd=str(base_dir))
    
    if result.returncode == 0:
        print()
        print("=" * 60)
        print("BUILD SUCCESSFUL!")
        print(f"Executable location: {base_dir / 'dist' / 'Pose2Sim'}")
        print()
        print("To run: dist/Pose2Sim/Pose2Sim.exe")
        print("=" * 60)
    else:
        print()
        print("BUILD FAILED. Check errors above.")
        sys.exit(1)


if __name__ == '__main__':
    build()
