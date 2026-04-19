"""
Flask web backend for Pose2Sim GUI.
Serves the HTML interface and exposes Python logic via REST API.
"""
import os
import sys
import json
import shutil
import subprocess
import threading
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file

# Add parent to path so we can import GUI modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from GUI.language_manager import LanguageManager
from GUI.config_generator import ConfigGenerator
from GUI.utils import activate_pose2sim, generate_checkerboard_image

# Support PyInstaller bundled paths  
import sys as _sys
if getattr(_sys, 'frozen', False):
    _base = Path(_sys._MEIPASS) / 'GUI'
else:
    _base = Path(__file__).parent

app = Flask(__name__, static_folder=str(_base / 'static'))

# ── Global Application State ──────────────────────────────────────
state = {
    'language': 'en',
    'analysis_mode': None,   # '2d' or '3d'
    'process_mode': None,    # 'single' or 'batch'
    'participant_name': None,
    'num_trials': 0,
    'setup_complete': False,
    'progress': 0,
    'tab_status': {},
    # Tab settings storage
    'calibration': {
        'calibration_type': 'calculate',
        'num_cameras': '2',
        'checkerboard_width': '7',
        'checkerboard_height': '5',
        'square_size': '30',
        'video_extension': 'mp4',
        'convert_from': 'qualisys',
        'binning_factor': '1',
        'object_coords_3d': [],
        'confirmed': False
    },
    'prepare_video': {
        'editing_mode': 'simple',
        'only_checkerboard': 'yes',
        'time_interval': '1',
        'extrinsic_format': 'png'
    },
    'pose_model': {
        'multiple_persons': 'single',
        'participant_height': '1.72',
        'participant_mass': '70.0',
        'pose_model': 'Body_with_feet',
        'mode': 'balanced',
        'tracking_mode': 'sports2d',
        'video_extension': 'mp4',
        'video_input': '',
        'video_input_type': 'file',
        'visible_side': 'auto',
        'multiple_videos_list': []
    },
    'synchronization': {
        'sync_videos': 'no',
        'use_gui': 'yes',
        'keypoints': 'all',
        'approx_time': 'auto',
        'time_range': '2.0',
        'likelihood_threshold': '0.4',
        'filter_cutoff': '6',
        'filter_order': '4'
    },
    'advanced': {},
    'console_output': []
}

lang_manager = LanguageManager()
config_generator = ConfigGenerator()


# ── Static file serving ──────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/favicon.ico')
def favicon():
    assets_dir = _base / 'assets'
    return send_from_directory(str(assets_dir), 'Pose2Sim_favicon.ico')

@app.route('/assets/<path:filename>')
def serve_asset(filename):
    assets_dir = _base / 'assets'
    return send_from_directory(str(assets_dir), filename)

@app.route('/video/<path:filename>')
def serve_video(filename):
    """Serve video files from any path (for playback in browser)"""
    # filename could be absolute or relative
    if os.path.isabs(filename):
        directory = os.path.dirname(filename)
        basename = os.path.basename(filename)
    else:
        directory = os.getcwd()
        basename = filename
    try:
        return send_from_directory(directory, basename)
    except:
        return "File not found", 404

@app.route('/project_file/<path:filename>')
def serve_project_file(filename):
    """Serve files from the project directory"""
    project = state.get('participant_name', '')
    if project:
        full_path = os.path.join(os.getcwd(), project, filename)
        if os.path.exists(full_path):
            return send_file(full_path)
    return "File not found", 404


# ── Language API ──────────────────────────────────────────────────
@app.route('/api/language', methods=['GET', 'POST'])
def language():
    if request.method == 'POST':
        data = request.json
        state['language'] = data.get('language', 'en')
        lang_manager.set_language(state['language'])
        return jsonify({'status': 'ok'})
    return jsonify({'language': state['language'], 'translations': lang_manager.translations[state['language']]})


# ── State API ─────────────────────────────────────────────────────
@app.route('/api/state')
def get_state():
    return jsonify({
        'language': state['language'],
        'analysis_mode': state['analysis_mode'],
        'process_mode': state['process_mode'],
        'participant_name': state['participant_name'],
        'num_trials': state['num_trials'],
        'setup_complete': state['setup_complete'],
        'progress': state['progress'],
        'tab_status': state['tab_status']
    })


# ── Welcome / Setup API ──────────────────────────────────────────
@app.route('/api/setup/start', methods=['POST'])
def setup_start():
    data = request.json
    state['analysis_mode'] = data.get('analysis_mode')
    state['process_mode'] = data.get('process_mode', 'single')
    state['participant_name'] = data.get('participant_name', 'my_project')
    state['num_trials'] = int(data.get('num_trials', 0))
    
    # Create folder structure
    _create_folder_structure()
    
    state['setup_complete'] = True
    
    # Determine which tabs to show
    tabs = _get_tabs_for_mode()
    
    return jsonify({'status': 'ok', 'tabs': tabs})


def _create_folder_structure():
    """Creates folder structure based on analysis mode"""
    p = state['participant_name']
    if state['analysis_mode'] == '3d':
        if state['process_mode'] == 'single':
            os.makedirs(os.path.join(p, 'calibration'), exist_ok=True)
            os.makedirs(os.path.join(p, 'videos'), exist_ok=True)
        else:
            os.makedirs(os.path.join(p, 'calibration'), exist_ok=True)
            for i in range(1, state['num_trials'] + 1):
                os.makedirs(os.path.join(p, f'Trial_{i}', 'videos'), exist_ok=True)
    else:
        os.makedirs(p, exist_ok=True)


def _get_tabs_for_mode():
    """Returns tab list based on analysis mode"""
    if state['analysis_mode'] == '3d':
        tabs = [
            {'id': 'tutorial', 'title': 'Tutorial', 'icon': 'school'},
            {'id': 'calibration', 'title': 'Calibration', 'icon': 'straighten'},
            {'id': 'prepare_video', 'title': 'Prepare Video', 'icon': 'movie'},
            {'id': 'pose_model', 'title': 'Pose Estimation', 'icon': 'person'},
            {'id': 'synchronization', 'title': 'Synchronization', 'icon': 'timer'},
            {'id': 'advanced', 'title': 'Advanced Settings', 'icon': 'settings'},
            {'id': 'activation', 'title': 'Run Analysis', 'icon': 'play_arrow'},
        ]
        if state['process_mode'] == 'batch':
            tabs.insert(-1, {'id': 'batch', 'title': 'Batch Config', 'icon': 'layers'})
        tabs.append({'id': 'visualization', 'title': 'Visualization', 'icon': 'bar_chart'})
        tabs.append({'id': 'about', 'title': 'About', 'icon': 'info'})
    else:
        tabs = [
            {'id': 'tutorial', 'title': 'Tutorial', 'icon': 'school'},
            {'id': 'pose_model', 'title': 'Pose Estimation', 'icon': 'person'},
            {'id': 'advanced', 'title': 'Advanced Settings', 'icon': 'settings'},
            {'id': 'activation', 'title': 'Run Analysis', 'icon': 'play_arrow'},
            {'id': 'visualization', 'title': 'Visualization', 'icon': 'bar_chart'},
            {'id': 'about', 'title': 'About', 'icon': 'info'},
        ]
    return tabs


# ── Tab Settings API ──────────────────────────────────────────────
@app.route('/api/tab/<tab_id>/settings', methods=['GET', 'POST'])
def tab_settings(tab_id):
    if request.method == 'POST':
        data = request.json
        if tab_id in state:
            state[tab_id].update(data)
        else:
            state[tab_id] = data
        return jsonify({'status': 'ok'})
    return jsonify(state.get(tab_id, {}))


@app.route('/api/tab/<tab_id>/confirm', methods=['POST'])
def tab_confirm(tab_id):
    """Mark a tab as confirmed/completed"""
    state['tab_status'][tab_id] = 'completed'
    
    # Update progress based on tab
    progress_map_3d = {
        'calibration': 15,
        'prepare_video': 30,
        'pose_model': 50,
        'synchronization': 70,
        'advanced': 85,
        'activation': 100
    }
    progress_map_2d = {
        'pose_model': 40,
        'advanced': 70,
        'activation': 100
    }
    
    pmap = progress_map_3d if state['analysis_mode'] == '3d' else progress_map_2d
    if tab_id in pmap:
        state['progress'] = pmap[tab_id]
    
    return jsonify({'status': 'ok', 'progress': state['progress']})


# ── File Browse API (uses tkinter file dialogs) ──────────────────
@app.route('/api/browse/file', methods=['POST'])
def browse_file():
    """Open a native file dialog and return selected path"""
    data = request.json or {}
    title = data.get('title', 'Select File')
    filetypes = data.get('filetypes', [('All files', '*.*')])
    
    result = {'path': ''}
    
    def _browse():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        # Convert list filetypes to tuples and always add All files
        ft = [tuple(x) if isinstance(x, list) else x for x in filetypes]
        if not any('*.*' in str(f) for f in ft):
            ft.append(("All files", "*.*"))
        path = filedialog.askopenfilename(title=title, filetypes=ft)
        root.destroy()
        result['path'] = path
    
    t = threading.Thread(target=_browse)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


@app.route('/api/browse/files', methods=['POST'])
def browse_files():
    """Open a native file dialog for multiple files"""
    data = request.json or {}
    title = data.get('title', 'Select Files')
    filetypes = data.get('filetypes', [('All files', '*.*')])
    
    result = {'paths': []}
    
    def _browse():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        paths = filedialog.askopenfilenames(title=title, filetypes=filetypes)
        root.destroy()
        result['paths'] = list(paths)
    
    t = threading.Thread(target=_browse)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


@app.route('/api/browse/directory', methods=['POST'])
def browse_directory():
    """Open a native directory dialog"""
    result = {'path': ''}
    
    def _browse():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askdirectory(title='Select Directory')
        root.destroy()
        result['path'] = path
    
    t = threading.Thread(target=_browse)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


@app.route('/api/browse/save', methods=['POST'])
def browse_save():
    """Open a native save dialog"""
    data = request.json or {}
    title = data.get('title', 'Save File')
    default_ext = data.get('default_ext', '.pdf')
    filetypes = data.get('filetypes', [('PDF files', '*.pdf')])
    
    result = {'path': ''}
    
    def _browse():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(title=title, defaultextension=default_ext, filetypes=filetypes)
        root.destroy()
        result['path'] = path
    
    t = threading.Thread(target=_browse)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


# ── Calibration-specific APIs ────────────────────────────────────
@app.route('/api/calibration/checkerboard', methods=['POST'])
def generate_checkerboard():
    """Generate and save checkerboard image"""
    data = request.json
    w = int(data.get('width', 7))
    h = int(data.get('height', 5))
    s = float(data.get('square_size', 30))
    
    img = generate_checkerboard_image(w, h, s)
    
    # Save to temp file
    temp_path = _base / 'static' / 'checkerboard_preview.png'
    img.save(str(temp_path))
    
    return jsonify({'status': 'ok', 'image_url': '/static/checkerboard_preview.png'})


@app.route('/api/calibration/save_checkerboard_pdf', methods=['POST'])
def save_checkerboard_pdf():
    """Save checkerboard as PDF via native dialog"""
    data = request.json
    w = int(data.get('width', 7))
    h = int(data.get('height', 5))
    s = float(data.get('square_size', 30))
    
    img = generate_checkerboard_image(w, h, s)
    
    result = {'path': ''}
    def _save():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(defaultextension='.pdf', filetypes=[('PDF files', '*.pdf')])
        root.destroy()
        if path:
            img.save(path, 'PDF')
            result['path'] = path
    
    t = threading.Thread(target=_save)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


@app.route('/api/calibration/create_folders', methods=['POST'])
def create_calibration_folders():
    """Create calibration folder structure"""
    num_cameras = int(state['calibration']['num_cameras'])
    base_path = Path(state['participant_name']) / 'calibration'
    
    for cam in range(1, num_cameras + 1):
        (base_path / 'intrinsics' / f'int_cam{cam}_img').mkdir(parents=True, exist_ok=True)
        (base_path / 'extrinsics' / f'ext_cam{cam}_img').mkdir(parents=True, exist_ok=True)
    
    return jsonify({'status': 'ok'})


@app.route('/api/calibration/import_files', methods=['POST'])
def import_calibration_files():
    """Import checkerboard/scene videos for calibration"""
    data = request.json
    file_type = data.get('type', 'intrinsics')  # 'intrinsics' or 'extrinsics'
    camera_num = int(data.get('camera', 1))
    
    ext = state['calibration']['video_extension']
    
    result = {'path': ''}
    def _browse():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title=f"Select {file_type} file for Camera {camera_num}",
            filetypes=[("All files", "*.*"), (f"Video/Image files", f"*.{ext}"), ("All files", "*.*")]
        )
        root.destroy()
        if path:
            base_path = Path(state['participant_name']) / 'calibration'
            if file_type == 'intrinsics':
                dest_folder = base_path / 'intrinsics' / f'int_cam{camera_num}_img'
            else:
                dest_folder = base_path / 'extrinsics' / f'ext_cam{camera_num}_img'
            dest_folder.mkdir(parents=True, exist_ok=True)
            dest = dest_folder / Path(path).name
            if dest.exists():
                dest.unlink()
            shutil.copy(path, str(dest))
            result['path'] = path
    
    t = threading.Thread(target=_browse)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


# ── Pose Model APIs ──────────────────────────────────────────────
@app.route('/api/pose/import_video', methods=['POST'])
def import_pose_video():
    """Import video for 2D analysis"""
    result = {'path': '', 'full_path': '', 'filename': ''}
    def _browse():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mpeg"), ("All files", "*.*")]
        )
        root.destroy()
        if path:
            # Copy to project dir
            dest_dir = state['participant_name']
            os.makedirs(dest_dir, exist_ok=True)
            filename = os.path.basename(path)
            dest = os.path.join(dest_dir, filename)
            if os.path.abspath(path) != os.path.abspath(dest):
                shutil.copy(path, dest)
            state['pose_model']['video_input'] = filename
            result['path'] = filename
            result['full_path'] = os.path.abspath(dest)
            result['filename'] = filename
    
    t = threading.Thread(target=_browse)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


@app.route('/api/pose/import_3d_videos', methods=['POST'])
def import_3d_videos():
    """Import videos for 3D analysis - one per camera. Matches original input_videos() exactly."""
    data = request.json
    num_cameras = int(data.get('num_cameras', 2))
    trial_num = data.get('trial_num', None)
    
    # Determine target path
    if state['process_mode'] == 'batch' and trial_num:
        target_path = os.path.join(state['participant_name'], f'Trial_{trial_num}', 'videos')
    else:
        target_path = os.path.join(state['participant_name'], 'videos')
    
    os.makedirs(target_path, exist_ok=True)
    ext = state['pose_model']['video_extension']
    
    # Check for existing videos
    try:
        existing = [f for f in os.listdir(target_path) if f.endswith(ext)]
    except:
        existing = []
    
    if existing:
        # Ask user if they want to replace
        replace_result = {'answer': False}
        def _ask_replace():
            import tkinter as tk
            from tkinter import messagebox as mb
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            answer = mb.askyesno("Existing Videos", "Existing videos found. Do you want to replace them?")
            root.destroy()
            replace_result['answer'] = answer
        
        t = threading.Thread(target=_ask_replace)
        t.start()
        t.join(timeout=30)
        
        if not replace_result['answer']:
            return jsonify({'status': 'cancelled', 'imported': []})
        
        # Delete existing videos
        for video in existing:
            try:
                os.remove(os.path.join(target_path, video))
            except:
                pass
    
    # Import new videos - one dialog per camera
    imported = []
    for cam in range(1, num_cameras + 1):
        result_path = {'path': ''}
        
        def _browse(camera_num=cam):
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            path = filedialog.askopenfilename(
                title=f"Select video for Camera {camera_num}",
                filetypes=[("All files", "*.*"), (f"Video files", f"*.{ext}")]
            )
            root.destroy()
            if path:
                dest_filename = f"cam{camera_num}.{ext}"
                dest_path = os.path.join(target_path, dest_filename)
                shutil.copy(path, dest_path)
                result_path['path'] = path
        
        t = threading.Thread(target=_browse)
        t.start()
        t.join(timeout=120)
        imported.append(result_path['path'])
    
    return jsonify({'status': 'ok', 'imported': imported})


# ── Activation / Run Analysis API ────────────────────────────────
@app.route('/api/activate', methods=['POST'])
def activate():
    """Generate config and run Pose2Sim/Sports2D"""
    # Collect all settings
    settings = _collect_all_settings()
    
    # Generate config
    if state['analysis_mode'] == '2d':
        config_path = Path(state['participant_name']) / 'Config_demo.toml'
        success = config_generator.generate_2d_config(str(config_path), settings)
    else:
        config_path = Path(state['participant_name']) / 'Config.toml'
        success = config_generator.generate_3d_config(str(config_path), settings)
        
        if state['process_mode'] == 'batch':
            for i in range(1, state['num_trials'] + 1):
                trial_path = Path(state['participant_name']) / f'Trial_{i}' / 'Config.toml'
                config_generator.generate_3d_config(str(trial_path), settings)
    
    if not success:
        return jsonify({'status': 'error', 'message': 'Failed to generate config file'}), 400
    
    # Determine skip flags
    skip_pose = False
    skip_sync = False
    skip_marker_augmentation = False
    
    if state['analysis_mode'] == '3d':
        pm = state['pose_model'].get('pose_model', 'Body_with_feet')
        if pm != 'Body_with_feet':
            skip_pose = True
        skip_sync = state['synchronization'].get('sync_videos', 'no') == 'yes'
        
        # Check use_augmentation from advanced settings
        adv = state.get('advanced', {})
        kin = adv.get('kinematics', {})
        if kin.get('use_augmentation') == False or kin.get('use_augmentation') == 'false':
            skip_marker_augmentation = True
    
    try:
        script_path = activate_pose2sim(
            state['participant_name'],
            method='conda',
            skip_pose_estimation=skip_pose,
            skip_synchronization=skip_sync,
            skip_marker_augmentation=skip_marker_augmentation,
            analysis_mode=state['analysis_mode']
        )
        
        # Launch in background
        def _run():
            process = subprocess.Popen(
                script_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, shell=True
            )
            for line in process.stdout:
                state['console_output'].append(line.rstrip())
                if len(state['console_output']) > 500:
                    state['console_output'] = state['console_output'][-500:]
            process.wait()
        
        threading.Thread(target=_run, daemon=True).start()
        
        state['progress'] = 100
        state['tab_status']['activation'] = 'completed'
        
        return jsonify({'status': 'ok', 'script_path': script_path})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/console')
def get_console():
    """Get console output"""
    return jsonify({'output': state['console_output']})


# ── Prepare Video APIs ───────────────────────────────────────────
@app.route('/api/prepare_video/launch_editor', methods=['POST'])
def launch_editor():
    """Launch the blur.py external editor"""
    script_path = _base / 'blur.py'
    if not script_path.exists():
        return jsonify({'status': 'error', 'message': 'blur.py not found'}), 404
    
    subprocess.Popen([sys.executable, str(script_path)])
    return jsonify({'status': 'ok'})


# ── Calibration Convert File Import ───────────────────────────────
@app.route('/api/calibration/import_convert_file', methods=['POST'])
def import_convert_file():
    """Import a calibration file for conversion (Qualisys, Optitrack, etc.)"""
    result = {'path': '', 'filename': ''}
    
    def _browse():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title="Select Calibration File to Convert",
            filetypes=[
                ("All files", "*.*"),
                ("QTM files", "*.qtm"),
                ("CSV files", "*.csv"),
                ("XML files", "*.xml"),
                ("YAML files", "*.yaml *.yml"),
                ("JSON files", "*.json"),
                ("TOML files", "*.toml"),
            ]
        )
        root.destroy()
        if path:
            # Create calibration folder and copy file
            cal_path = Path(state['participant_name']) / 'calibration'
            cal_path.mkdir(parents=True, exist_ok=True)
            dest = cal_path / Path(path).name
            if dest.exists():
                dest.unlink()
            shutil.copy(path, str(dest))
            result['path'] = str(dest)
            result['filename'] = Path(path).name
    
    t = threading.Thread(target=_browse)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


# ── Dependency Check API ─────────────────────────────────────────
@app.route('/api/check_dependencies', methods=['GET'])
def check_dependencies():
    """Check system dependencies"""
    deps = {}
    
    # Check conda
    try:
        r = subprocess.run(['conda', '--version'], capture_output=True, text=True, shell=True, timeout=10)
        deps['anaconda'] = r.returncode == 0
    except:
        deps['anaconda'] = False
    
    # Check pose2sim
    try:
        r = subprocess.run([sys.executable, '-c', 'import Pose2Sim'], capture_output=True, text=True, timeout=10)
        deps['pose2sim'] = r.returncode == 0
    except:
        deps['pose2sim'] = False
    
    # Check opensim
    try:
        r = subprocess.run([sys.executable, '-c', 'import opensim'], capture_output=True, text=True, timeout=10)
        deps['opensim'] = r.returncode == 0
    except:
        deps['opensim'] = False
    
    # Check pytorch
    try:
        r = subprocess.run([sys.executable, '-c', 'import torch; print(torch.cuda.is_available())'], capture_output=True, text=True, timeout=10)
        deps['pytorch'] = r.returncode == 0 and 'True' in r.stdout
    except:
        deps['pytorch'] = False
    
    # Check onnxruntime-gpu
    try:
        r = subprocess.run([sys.executable, '-c', 'import onnxruntime'], capture_output=True, text=True, timeout=10)
        deps['onnxruntime'] = r.returncode == 0
    except:
        deps['onnxruntime'] = False
    
    return jsonify(deps)


# ── Scene Calibration Image API ──────────────────────────────────
@app.route('/api/calibration/load_scene_image', methods=['POST'])
def load_scene_image():
    """Open file dialog to load a scene image/video, extract frame, save as static"""
    import cv2
    
    ext = state['calibration'].get('video_extension', 'mp4')
    result = {'url': '', 'width': 0, 'height': 0}
    
    def _browse():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title="Select Scene Image/Video for Point Selection",
            filetypes=[("All files", "*.*"), (f"Video/Image files", f"*.{ext}"), ("All files", "*.*")]
        )
        root.destroy()
        if path:
            # Load image (from video first frame or image file)
            if Path(path).suffix.lower() in ('.mp4', '.avi', '.mov'):
                cap = cv2.VideoCapture(path)
                ret, frame = cap.read()
                cap.release()
                if ret:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                else:
                    return
            else:
                frame_rgb = cv2.imread(path)
                if frame_rgb is not None:
                    frame_rgb = cv2.cvtColor(frame_rgb, cv2.COLOR_BGR2RGB)
                else:
                    return
            
            # Save to static folder
            out_path = _base / 'static' / 'scene_image.jpg'
            cv2.imwrite(str(out_path), cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR))
            h, w = frame_rgb.shape[:2]
            result['url'] = f'/static/scene_image.jpg?t={int(threading.current_thread().ident)}'
            result['width'] = w
            result['height'] = h
    
    t = threading.Thread(target=_browse)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


@app.route('/api/calibration/save_scene_coords', methods=['POST'])
def save_scene_coords():
    """Save 2D pixel + 3D world coordinate pairs for scene calibration"""
    data = request.json
    state['calibration']['object_coords_3d'] = data.get('coords_3d', [])
    state['calibration']['points_2d'] = data.get('points_2d', [])
    return jsonify({'status': 'ok'})


# ── Visualization APIs ───────────────────────────────────────────
@app.route('/api/visualization/load_trc', methods=['POST'])
def load_trc():
    """Load a TRC file via dialog and return parsed data"""
    result = {'data': None, 'headers': [], 'path': ''}
    
    def _browse():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(title="Select TRC File", filetypes=[("TRC files", "*.trc"), ("All files", "*.*")])
        root.destroy()
        if path:
            parsed = _parse_trc(path)
            result.update(parsed)
    
    t = threading.Thread(target=_browse)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


@app.route('/api/visualization/load_trc_path', methods=['POST'])
def load_trc_path():
    """Load a TRC file from a given path"""
    data = request.json
    path = data.get('path', '')
    return jsonify(_parse_trc(path))


def _parse_trc(path):
    """Parse a TRC file"""
    result = {'data': None, 'headers': [], 'path': path, 'is_3d': False}
    if not path or not os.path.exists(path):
        return result
    try:
        with open(path, 'r') as f:
            lines = f.readlines()
        if len(lines) > 5:
            # Line 4 (index 3) has marker names
            header_line = lines[3].strip()
            if '\t' in header_line:
                headers = header_line.split('\t')
            else:
                headers = header_line.split()
            
            # Line 5 (index 4) has X/Y/Z sub-headers
            sub_headers = lines[4].strip().split('\t') if '\t' in lines[4] else lines[4].strip().split()
            
            # Check if it's 3D data (has X, Y, Z columns)
            result['is_3d'] = any('Z' in h.upper() for h in sub_headers if h.strip())
            
            data_lines = []
            for line in lines[5:]:
                line = line.strip()
                if not line:
                    continue
                if '\t' in line:
                    vals = line.split('\t')
                else:
                    vals = line.split()
                try:
                    data_lines.append([float(v) if v.strip() else 0 for v in vals])
                except:
                    pass
            result['headers'] = headers
            result['sub_headers'] = sub_headers
            result['data'] = data_lines[:1000]
            
            # Extract marker names (non-empty entries after Frame# and Time)
            marker_names = [h.strip() for h in headers[2:] if h.strip()]
            result['markers'] = marker_names
    except Exception as e:
        result['error'] = str(e)
    return result


@app.route('/api/visualization/load_mot', methods=['POST'])
def load_mot():
    """Load a MOT file via dialog and return parsed data"""
    result = {'data': None, 'headers': [], 'path': ''}
    
    def _browse():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(title="Select MOT File", filetypes=[("MOT files", "*.mot"), ("All files", "*.*")])
        root.destroy()
        if path:
            parsed = _parse_mot(path)
            result.update(parsed)
    
    t = threading.Thread(target=_browse)
    t.start()
    t.join(timeout=120)
    
    return jsonify(result)


@app.route('/api/visualization/load_mot_path', methods=['POST'])
def load_mot_path():
    """Load a MOT file from a given path"""
    data = request.json
    path = data.get('path', '')
    return jsonify(_parse_mot(path))


def _parse_mot(path):
    """Parse a MOT file"""
    result = {'data': None, 'headers': [], 'path': path}
    if not path or not os.path.exists(path):
        return result
    try:
        with open(path, 'r') as f:
            lines = f.readlines()
        # Find endheader or nRows/nColumns
        start = 0
        for i, line in enumerate(lines):
            if 'endheader' in line.lower():
                start = i + 1
                break
        # If no endheader, try to find column headers (first line with multiple tab/space separated values)
        if start == 0:
            for i, line in enumerate(lines):
                parts = line.strip().split()
                if len(parts) > 3 and not parts[0].replace('.','',1).replace('-','',1).isdigit():
                    start = i
                    break
        
        if start < len(lines):
            # Split by tabs first, fall back to whitespace
            header_line = lines[start].strip()
            if '\t' in header_line:
                headers = header_line.split('\t')
            else:
                headers = header_line.split()
            
            data_lines = []
            for line in lines[start+1:]:
                line = line.strip()
                if not line:
                    continue
                if '\t' in line:
                    vals = line.split('\t')
                else:
                    vals = line.split()
                try:
                    data_lines.append([float(v) if v else 0 for v in vals])
                except:
                    pass
            result['headers'] = headers
            result['data'] = data_lines[:1000]
    except Exception as e:
        result['error'] = str(e)
    return result


@app.route('/api/visualization/auto_detect', methods=['GET'])
def auto_detect_files():
    """Auto-detect TRC, MOT and video files in project folder"""
    project = state.get('participant_name', '')
    results = {'trc': [], 'mot': [], 'video': []}
    
    if not project or not os.path.exists(project):
        return jsonify(results)
    
    for root_dir, dirs, files in os.walk(project):
        for f in files:
            full = os.path.join(root_dir, f)
            ext = f.lower().split('.')[-1] if '.' in f else ''
            if ext == 'trc':
                results['trc'].append(os.path.abspath(full))
            elif ext == 'mot':
                results['mot'].append(os.path.abspath(full))
            elif ext in ('mp4', 'avi', 'mov', 'mpeg'):
                results['video'].append(os.path.abspath(full))
    
    return jsonify(results)


@app.route('/api/about/releases', methods=['GET'])
def get_releases():
    """Fetch GitHub releases"""
    try:
        import urllib.request
        url = 'https://api.github.com/repos/perfanalytics/pose2sim/releases?per_page=5'
        req = urllib.request.Request(url, headers={'User-Agent': 'Pose2Sim-GUI'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        releases = [{'tag': r.get('tag_name',''), 'name': r.get('name',''), 'date': r.get('published_at','')[:10], 'body': r.get('body','')[:300]} for r in data[:5]]
        return jsonify({'releases': releases})
    except:
        return jsonify({'releases': []})


# ── Helper: collect all settings ─────────────────────────────────
def _collect_all_settings():
    """Collect settings from all tabs into a config dict"""
    settings = {}
    
    # Calibration settings
    cal = state['calibration']
    cal_settings = {
        'calibration': {
            'calibration_type': cal['calibration_type'],
        }
    }
    if cal['calibration_type'] == 'calculate':
        cal_settings['calibration']['calculate'] = {
            'intrinsics': {
                'intrinsics_corners_nb': [int(cal['checkerboard_width']), int(cal['checkerboard_height'])],
                'intrinsics_square_size': float(cal['square_size']),
                'intrinsics_extension': cal['video_extension']
            },
            'extrinsics': {
                'scene': {
                    'extrinsics_extension': cal['video_extension']
                }
            }
        }
        if cal['object_coords_3d']:
            cal_settings['calibration']['calculate']['extrinsics']['scene']['object_coords_3d'] = cal['object_coords_3d']
    else:
        cal_settings['calibration']['convert'] = {
            'convert_from': cal['convert_from']
        }
        if cal['convert_from'] == 'qualisys':
            cal_settings['calibration']['convert']['qualisys'] = {
                'binning_factor': int(cal['binning_factor'])
            }
    _merge_nested(settings, cal_settings)
    
    # Pose model settings
    pm = state['pose_model']
    pm_settings = {
        'pose': {
            'pose_model': pm['pose_model'],
            'mode': pm['mode'],
            'tracking_mode': pm['tracking_mode'],
            'vid_img_extension': pm['video_extension'],
            'parallel_workers_pose': 'auto',
            'average_likelihood_threshold_pose': 0.5,
        },
        'project': {
            'multi_person': pm['multiple_persons'] == 'multiple'
        }
    }
    
    if state['analysis_mode'] == '2d':
        pm_settings['base'] = {
            'video_input': pm.get('video_input', ''),
            'visible_side': pm.get('visible_side', 'auto'),
            'first_person_height': float(pm.get('participant_height', '1.72'))
        }
        if pm.get('video_input_type') == 'webcam':
            pm_settings['base']['video_input'] = 'webcam'
        elif pm.get('video_input_type') == 'multiple' and pm.get('multiple_videos_list'):
            pm_settings['base']['video_input'] = pm['multiple_videos_list']
    else:
        if pm['multiple_persons'] == 'single':
            pm_settings['project']['participant_height'] = float(pm.get('participant_height', '1.72'))
            pm_settings['project']['participant_mass'] = float(pm.get('participant_mass', '70.0'))
    
    _merge_nested(settings, pm_settings)
    
    # Synchronization settings
    sync = state['synchronization']
    sync_settings = {'synchronization': {}}
    if sync['sync_videos'] == 'yes':
        sync_settings['synchronization']['synchronization_gui'] = False
    else:
        sync_settings['synchronization']['synchronization_gui'] = sync['use_gui'] == 'yes'
        if sync['use_gui'] != 'yes':
            kp = sync['keypoints']
            sync_settings['synchronization'].update({
                'keypoints_to_consider': 'all' if kp == 'all' else [kp],
                'approx_time_maxspeed': 'auto',
                'time_range_around_maxspeed': float(sync.get('time_range', '2.0')),
                'likelihood_threshold_synchronization': float(sync.get('likelihood_threshold', '0.4')),
                'filter_cutoff': int(sync.get('filter_cutoff', '6')),
                'filter_order': int(sync.get('filter_order', '4'))
            })
    _merge_nested(settings, sync_settings)
    
    # Advanced settings
    if state['advanced']:
        _merge_nested(settings, state['advanced'])
    
    return settings


def _merge_nested(d1, d2):
    """Recursively merge d2 into d1"""
    for key, value in d2.items():
        if key in d1 and isinstance(d1[key], dict) and isinstance(value, dict):
            _merge_nested(d1[key], value)
        else:
            d1[key] = value


# ── Launch ────────────────────────────────────────────────────────
def run_server(port=5789):
    """Run the Flask server"""
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    run_server()
