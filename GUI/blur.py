import cv2
import os
import numpy as np
import tkinter as tk
from tkinter import filedialog, ttk, Scale, IntVar, StringVar, BooleanVar, colorchooser
from PIL import Image, ImageTk
import time
import json
import sys
import threading

# Try to import RTMLib and DeepSort
try:
    from rtmlib import PoseTracker, Wholebody
    RTMPOSE_AVAILABLE = True
except ImportError:
    RTMPOSE_AVAILABLE = False
    print("Warning: RTMLib not available. Install with: pip install rtmlib")

try:
    from deep_sort_realtime.deepsort_tracker import DeepSort
    DEEPSORT_AVAILABLE = True
except ImportError:
    DEEPSORT_AVAILABLE = False
    print("Warning: DeepSort not available. Install with: pip install deep-sort-realtime")

class VideoBlurApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced Video Face Masking Tool")
        
        # Configure the root window with grid layout
        self.root.grid_columnconfigure(0, weight=0)  # Control panel - fixed width
        self.root.grid_columnconfigure(1, weight=1)  # Video display - expandable
        self.root.grid_rowconfigure(0, weight=1)     # Main content
        self.root.grid_rowconfigure(1, weight=0)     # Status bar - fixed height
        
        # Input variables
        self.input_video = None
        self.output_path = None
        self.shapes = []  # Will store [shape_type, points, mask_type, blur_strength, color, start_frame, end_frame]
        self.auto_detect_faces = False
        self.current_frame = None
        self.frame_index = 0
        self.cap = None
        self.total_frames = 0
        
        # Drawing variables
        self.drawing = False
        self.current_shape = []
        self.temp_shape_id = None
        self.current_shape_type = "rectangle"
        
        # Mask settings
        self.blur_strength = 21  # Default medium blur (kernel size)
        self.mask_type = "blur"  # Default mask type
        self.mask_shape = "oval"  # Default mask shape (oval works better for faces)
        self.mask_color = (0, 0, 0)  # Default color for solid masks
        
        # Frame range variables
        self.blur_entire_video = BooleanVar(value=True)
        self.start_frame = IntVar(value=0)
        self.end_frame = IntVar(value=0)
        
        # Crop settings
        self.crop_enabled = BooleanVar(value=False)
        self.crop_x = 0
        self.crop_y = 0
        self.crop_width = 0
        self.crop_height = 0
        self.drawing_crop = False
        self.temp_crop_rect = None
        
        # Enhanced crop settings
        self.crop_type = StringVar(value="traditional")
        self.crop_mask_type = StringVar(value="black")
        self.crop_all_frames = BooleanVar(value=True)
        self.crop_start_frame = IntVar(value=0)
        self.crop_end_frame = IntVar(value=0)
        
        # Rotation settings (new)
        self.rotation_angle = IntVar(value=0)
        self.rotation_enabled = BooleanVar(value=False)
        
        # Video trimming variables
        self.trim_enabled = BooleanVar(value=False)
        self.trim_start_frame = IntVar(value=0)
        self.trim_end_frame = IntVar(value=0)
        self.dragging_start = False
        self.dragging_end = False
        
        # Status variable
        self.status_text = StringVar(value="Open a video file to begin")
        
        # Image positioning
        self.x_offset = 0
        self.y_offset = 0
        
        # Face detection & tracking
        self.face_detect_var = BooleanVar(value=False)
        self.init_face_detection()
        
        # Create UI components
        self.create_ui()
        
        # Add status bar
        self.status_bar = ttk.Label(self.root, textvariable=self.status_text, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        
    def init_face_detection(self):
        """Initialize face detection and tracking components"""
        self.rtmpose_initialized = False
        self.has_deepsort = False
        self.tracked_faces = []
        self.next_face_id = 0
        self.detection_frequency = 3
        
        # Initialize RTMPose if available
        if RTMPOSE_AVAILABLE:
            try:
                # Setup RTMPose
                backend = device = 'cpu'  # Default
                try:
                    import torch
                    import onnxruntime as ort
                    if torch.cuda.is_available() and 'CUDAExecutionProvider' in ort.get_available_providers():
                        backend, device = 'onnxruntime', 'cuda'
                except:
                    pass
                
                # Initialize with Wholebody model
                self.pose_tracker = PoseTracker(
                    Wholebody,
                    det_frequency=2,
                    mode="balanced",
                    backend=backend,
                    device=device,
                    tracking=False,
                    to_openpose=False
                )
                self.rtmpose_initialized = True
            except Exception as e:
                print(f"Error initializing RTMPose: {e}")
        
        # Initialize DeepSort if available
        if DEEPSORT_AVAILABLE:
            try:
                self.deepsort_tracker = DeepSort(
                    max_age=30,
                    n_init=3,
                    nms_max_overlap=1.0,
                    max_cosine_distance=0.2,
                    nn_budget=None,
                    embedder='mobilenet',
                    half=True,
                    bgr=True,
                    embedder_gpu=True
                )
                self.has_deepsort = True
            except Exception as e:
                print(f"Error initializing DeepSort: {e}")
    
    def create_ui(self):
        """Create the main UI layout with fixed positioning"""
        # Create left panel (controls)
        control_panel = ttk.Frame(self.root, width=300)
        control_panel.grid(row=0, column=0, sticky="ns", padx=5, pady=5)
        control_panel.grid_propagate(False)  # Keep fixed width
        
        # Create right panel (video display and navigation)
        video_panel = ttk.Frame(self.root)
        video_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        video_panel.grid_columnconfigure(0, weight=1)
        video_panel.grid_rowconfigure(0, weight=1)  # Canvas expands
        video_panel.grid_rowconfigure(1, weight=0)  # Navigation fixed height
        
        # Create canvas for video display
        self.canvas_frame = ttk.Frame(video_panel)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew")
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Create navigation panel
        nav_panel = ttk.Frame(video_panel, height=120)
        nav_panel.grid(row=1, column=0, sticky="ew", pady=(5,0))
        nav_panel.grid_propagate(False)  # Fix height
        
        # Add components to the control panel
        self.setup_control_panel(control_panel)
        
        # Add components to the navigation panel
        self.setup_navigation_panel(nav_panel)
        
        # Bind canvas events for drawing
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
    
    def setup_control_panel(self, parent):
        """Set up the left control panel with all controls"""
        # Create a canvas with scrollbar for the control panel
        canvas = tk.Canvas(parent, width=280)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # File operations
        file_frame = ttk.LabelFrame(scrollable_frame, text="File Operations")
        file_frame.pack(fill=tk.X, pady=(0,5), padx=2)
        
        ttk.Button(file_frame, text="Open Video", command=self.open_video).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(file_frame, text="Set Output Path", command=self.set_output_path).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(file_frame, text="Process Video", command=self.process_video).pack(fill=tk.X, padx=5, pady=2)
        
        # Drawing tools
        draw_frame = ttk.LabelFrame(scrollable_frame, text="Drawing Tools")
        draw_frame.pack(fill=tk.X, pady=5, padx=2)
        
        tool_frame = ttk.Frame(draw_frame)
        tool_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(tool_frame, text="Rectangle", command=lambda: self.set_drawing_mode("rectangle")).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(tool_frame, text="Polygon", command=lambda: self.set_drawing_mode("polygon")).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(tool_frame, text="Freehand", command=lambda: self.set_drawing_mode("freehand")).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        mask_frame = ttk.Frame(draw_frame)
        mask_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(mask_frame, text="Mask Type:").pack(side=tk.LEFT)
        self.mask_type_var = StringVar(value="blur")
        ttk.Combobox(mask_frame, textvariable=self.mask_type_var, values=["blur", "black", "pixelate", "solid"], width=10, state="readonly").pack(side=tk.RIGHT)
        
        strength_frame = ttk.Frame(draw_frame)
        strength_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(strength_frame, text="Effect Strength:").pack(side=tk.LEFT)
        self.blur_strength_var = IntVar(value=21)
        self.strength_label = ttk.Label(strength_frame, text="21")
        self.strength_label.pack(side=tk.RIGHT)
        
        # Add a scale for blur strength
        strength_scale = ttk.Scale(draw_frame, from_=3, to=51, orient=tk.HORIZONTAL, variable=self.blur_strength_var)
        strength_scale.pack(fill=tk.X, padx=5, pady=2)
        strength_scale.bind("<Motion>", self.update_blur_strength)
        
        ttk.Button(draw_frame, text="Choose Color", command=self.choose_color).pack(fill=tk.X, padx=5, pady=2)
        
        # Shape list section
        shape_frame = ttk.LabelFrame(scrollable_frame, text="Shape List")
        shape_frame.pack(fill=tk.X, pady=5, padx=2)
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(shape_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        
        self.shapes_listbox = tk.Listbox(list_frame, height=5)
        self.shapes_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.shapes_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.shapes_listbox.config(yscrollcommand=scrollbar.set)
        self.shapes_listbox.bind("<<ListboxSelect>>", self.on_shape_selected)
        
        # Frame range for shapes
        range_frame = ttk.LabelFrame(shape_frame, text="Shape Frame Range")
        range_frame.pack(fill=tk.X, padx=5, pady=2)
        
        frame_inputs = ttk.Frame(range_frame)
        frame_inputs.pack(fill=tk.X, pady=2)
        
        ttk.Label(frame_inputs, text="Start:").pack(side=tk.LEFT)
        self.shape_start_frame = ttk.Entry(frame_inputs, width=6)
        self.shape_start_frame.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(frame_inputs, text="End:").pack(side=tk.LEFT, padx=(5,0))
        self.shape_end_frame = ttk.Entry(frame_inputs, width=6)
        self.shape_end_frame.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(frame_inputs, text="Apply", command=self.set_shape_frame_range).pack(side=tk.RIGHT)
        
        btn_frame = ttk.Frame(shape_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(btn_frame, text="Delete Selected", command=self.delete_selected_shape).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(btn_frame, text="Clear All", command=self.clear_shapes).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        # Video cropping section
        crop_frame = ttk.LabelFrame(scrollable_frame, text="Video Cropping")
        crop_frame.pack(fill=tk.X, pady=5, padx=2)
        
        ttk.Checkbutton(crop_frame, text="Enable video cropping", variable=self.crop_enabled, command=self.toggle_crop).pack(anchor=tk.W, padx=5, pady=2)
        
        crop_type_frame = ttk.Frame(crop_frame)
        crop_type_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Radiobutton(crop_type_frame, text="Traditional crop (cut out)", variable=self.crop_type, value="traditional").pack(anchor=tk.W)
        ttk.Radiobutton(crop_type_frame, text="Mask outside region", variable=self.crop_type, value="mask").pack(anchor=tk.W)
        
        mask_type_frame = ttk.Frame(crop_frame)
        mask_type_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(mask_type_frame, text="Outside area:").pack(side=tk.LEFT)
        ttk.Combobox(mask_type_frame, textvariable=self.crop_mask_type, values=["black", "blur", "pixelate"], width=10, state="readonly").pack(side=tk.RIGHT)
        
        frame_range_frame = ttk.Frame(crop_frame)
        frame_range_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Radiobutton(frame_range_frame, text="Apply to all frames", variable=self.crop_all_frames, value=True).pack(anchor=tk.W)
        ttk.Radiobutton(frame_range_frame, text="Apply to frame range", variable=self.crop_all_frames, value=False).pack(anchor=tk.W)
        
        range_inputs = ttk.Frame(crop_frame)
        range_inputs.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(range_inputs, text="Start:").pack(side=tk.LEFT)
        ttk.Entry(range_inputs, textvariable=self.crop_start_frame, width=6).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(range_inputs, text="End:").pack(side=tk.LEFT, padx=(5,0))
        ttk.Entry(range_inputs, textvariable=self.crop_end_frame, width=6).pack(side=tk.LEFT, padx=2)
        
        button_frame = ttk.Frame(crop_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(button_frame, text="Draw Crop Region", command=self.start_crop_drawing).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(button_frame, text="Reset Crop", command=self.reset_crop).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        info_frame = ttk.Frame(crop_frame)
        info_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(info_frame, text="Crop dimensions:").pack(side=tk.LEFT)
        self.crop_info_label = ttk.Label(info_frame, text="Not set")
        self.crop_info_label.pack(side=tk.RIGHT)
        
        # Video rotation section (updated)
        rotation_frame = ttk.LabelFrame(scrollable_frame, text="Video Rotation")
        rotation_frame.pack(fill=tk.X, pady=5, padx=2)
        
        ttk.Checkbutton(rotation_frame, text="Enable rotation", variable=self.rotation_enabled, 
                       command=self.toggle_rotation).pack(anchor=tk.W, padx=5, pady=2)
        
        # First row - angle input
        rotation_controls = ttk.Frame(rotation_frame)
        rotation_controls.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(rotation_controls, text="Angle:").pack(side=tk.LEFT)
        self.rotation_entry = ttk.Entry(rotation_controls, textvariable=self.rotation_angle, width=6)
        self.rotation_entry.pack(side=tk.LEFT, padx=2)
        ttk.Label(rotation_controls, text="degrees").pack(side=tk.LEFT)
        ttk.Button(rotation_controls, text="Apply", command=lambda: self.set_rotation(self.rotation_angle.get())).pack(
            side=tk.RIGHT, padx=2)
        
        # Second row - rotation buttons
        rotation_buttons = ttk.Frame(rotation_frame)
        rotation_buttons.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(rotation_buttons, text="Rotate Left 90°", command=lambda: self.set_rotation(-90)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(rotation_buttons, text="Rotate Right 90°", command=lambda: self.set_rotation(90)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(rotation_buttons, text="Reset", command=lambda: self.set_rotation(0)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        # Face detection section
        face_frame = ttk.LabelFrame(scrollable_frame, text="Face Detection")
        face_frame.pack(fill=tk.X, pady=5, padx=2)
        
        ttk.Checkbutton(face_frame, text="Auto-detect and track faces", variable=self.face_detect_var, command=self.toggle_face_detection).pack(anchor=tk.W, padx=5, pady=2)
        
        face_shape_frame = ttk.Frame(face_frame)
        face_shape_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(face_shape_frame, text="Face Mask Shape:").pack(side=tk.LEFT)
        self.mask_shape_var = StringVar(value="oval")
        ttk.Combobox(face_shape_frame, textvariable=self.mask_shape_var, values=["rectangle", "oval", "precise"], width=10, state="readonly").pack(side=tk.RIGHT)
        
        face_buttons = ttk.Frame(face_frame)
        face_buttons.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(face_buttons, text="Detect Current Frame", command=self.detect_faces_current_frame).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(face_buttons, text="Export Face Data", command=self.export_face_data).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        # Processing Range section
        process_frame = ttk.LabelFrame(scrollable_frame, text="Processing Range")
        process_frame.pack(fill=tk.X, pady=5, padx=2)
        
        ttk.Radiobutton(process_frame, text="Process entire video", variable=self.blur_entire_video, value=True, command=self.toggle_frame_range).pack(anchor=tk.W, padx=5, pady=2)
        ttk.Radiobutton(process_frame, text="Process specific range", variable=self.blur_entire_video, value=False, command=self.toggle_frame_range).pack(anchor=tk.W, padx=5, pady=2)
        
        range_input_frame = ttk.Frame(process_frame)
        range_input_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(range_input_frame, text="Start:").pack(side=tk.LEFT)
        self.start_frame_entry = ttk.Entry(range_input_frame, textvariable=self.start_frame, width=8, state="disabled")
        self.start_frame_entry.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(range_input_frame, text="End:").pack(side=tk.LEFT, padx=(5,0))
        self.end_frame_entry = ttk.Entry(range_input_frame, textvariable=self.end_frame, width=8, state="disabled")
        self.end_frame_entry.pack(side=tk.LEFT, padx=2)
    
    def setup_navigation_panel(self, parent):
        """Set up the navigation controls below the video"""
        # Frame slider
        slider_frame = ttk.Frame(parent)
        slider_frame.pack(fill=tk.X, padx=5, pady=(5,0))
        
        self.frame_slider = ttk.Scale(slider_frame, from_=0, to=100, orient=tk.HORIZONTAL, command=self.on_slider_change)
        self.frame_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        
        self.frame_counter = ttk.Label(slider_frame, text="0/0", width=10)
        self.frame_counter.pack(side=tk.RIGHT)
        
        # Video trimming
        trim_frame = ttk.Frame(parent)
        trim_frame.pack(fill=tk.X, padx=5, pady=(5,0))
        
        self.trim_check = ttk.Checkbutton(trim_frame, text="Enable video trimming", variable=self.trim_enabled, command=self.toggle_trim)
        self.trim_check.pack(side=tk.LEFT)
        
        trim_indicators = ttk.Frame(trim_frame)
        trim_indicators.pack(side=tk.RIGHT)
        
        ttk.Label(trim_indicators, text="In:").pack(side=tk.LEFT)
        self.trim_in_label = ttk.Label(trim_indicators, text="0", width=6)
        self.trim_in_label.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(trim_indicators, text="Out:").pack(side=tk.LEFT, padx=(5,0))
        self.trim_out_label = ttk.Label(trim_indicators, text="0", width=6)
        self.trim_out_label.pack(side=tk.LEFT, padx=2)
        
        # Trim timeline
        self.trim_canvas = tk.Canvas(parent, height=20, bg="lightgray")
        self.trim_canvas.pack(fill=tk.X, padx=5, pady=(5,0))
        
        # Navigation buttons
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, padx=5, pady=(5,0))
        
        ttk.Button(button_frame, text="◀◀ Previous", command=self.prev_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Next ▶▶", command=self.next_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="◀◀◀ -10 Frames", command=lambda: self.jump_frames(-10)).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="+10 Frames ▶▶▶", command=lambda: self.jump_frames(10)).pack(side=tk.LEFT, padx=2)
        
        # Bind trim canvas events
        self.trim_canvas.bind("<ButtonPress-1>", self.on_trim_click)
        self.trim_canvas.bind("<B1-Motion>", self.on_trim_drag)
        self.trim_canvas.bind("<ButtonRelease-1>", self.on_trim_release)

    def update_blur_strength(self, event=None):
        """Update blur strength value display"""
        value = self.blur_strength_var.get()
        # Ensure odd number for gaussian blur
        if value % 2 == 0:
            value += 1
            self.blur_strength_var.set(value)
        
        self.blur_strength = value
        self.strength_label.config(text=str(value))
    
    def toggle_face_detection(self):
        """Toggle face detection on/off"""
        self.auto_detect_faces = self.face_detect_var.get()
        if self.auto_detect_faces and not self.rtmpose_initialized:
            self.status_text.set("Face detection requires RTMPose which is not available")
            self.face_detect_var.set(False)
            self.auto_detect_faces = False
            return
            
        status = "enabled" if self.auto_detect_faces else "disabled"
        self.status_text.set(f"Automatic face detection {status}")
        self.show_current_frame()
    
    def toggle_crop(self):
        """Toggle crop mode on/off with proper validation"""
        # If enabling cropping, validate that region is set
        if self.crop_enabled.get():
            if self.crop_width <= 0 or self.crop_height <= 0:
                self.status_text.set("Please draw a crop region first")
                self.crop_enabled.set(False)
                return
            
            status = "enabled"
            if self.crop_type.get() == "mask":
                status += f" (masking outside with {self.crop_mask_type.get()})"
            self.status_text.set(f"Video cropping {status}")
            
        else:
            self.status_text.set("Video cropping disabled")
        
        self.show_current_frame()
    
    def toggle_rotation(self):
        """Toggle rotation on/off"""
        if self.rotation_enabled.get():
            self.status_text.set(f"Video rotation enabled ({self.rotation_angle.get()}°)")
        else:
            self.status_text.set("Video rotation disabled")
        self.show_current_frame()
    
    def set_rotation(self, angle):
        """Set rotation angle"""
        current = self.rotation_angle.get()
        if angle in [-90, 90]:  # Relative rotation
            new_angle = (current + angle) % 360
        else:  # Absolute rotation
            new_angle = angle
        
        self.rotation_angle.set(new_angle)
        self.rotation_enabled.set(True if new_angle != 0 else False)
        self.status_text.set(f"Rotation set to {new_angle}°")
        self.show_current_frame()
    
    def rotate_frame(self, frame, angle):
        """Rotate a frame by given angle in degrees"""
        if angle == 0:
            return frame
        
        height, width = frame.shape[:2]
        center = (width // 2, height // 2)
        
        # Get the rotation matrix
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Perform the rotation
        rotated = cv2.warpAffine(frame, rotation_matrix, (width, height), 
                               flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        return rotated
    
    def toggle_trim(self):
        """Toggle video trimming on/off"""
        if self.trim_enabled.get():
            if self.cap is None:
                self.status_text.set("Please open a video first")
                self.trim_enabled.set(False)
                return
                
            # Initialize trim range to full video
            self.trim_start_frame.set(0)
            self.trim_end_frame.set(self.total_frames - 1)
            self.update_trim_display()
            self.status_text.set("Video trimming enabled. Drag markers to set in/out points.")
        else:
            self.clear_trim_display()
            self.status_text.set("Video trimming disabled")
    
    def update_trim_display(self):
        """Update trim timeline display"""
        if not self.trim_enabled.get() or self.cap is None:
            return
            
        self.clear_trim_display()
        
        width = self.trim_canvas.winfo_width()
        height = self.trim_canvas.winfo_height()
        
        if width <= 1:  # Canvas not yet rendered
            self.root.after(100, self.update_trim_display)
            return
            
        # Draw background
        self.trim_canvas.create_rectangle(0, 0, width, height, fill="lightgray", outline="")
        
        # Calculate positions
        start_pos = (self.trim_start_frame.get() / max(1, self.total_frames - 1)) * width
        end_pos = (self.trim_end_frame.get() / max(1, self.total_frames - 1)) * width
        
        # Draw trim region
        self.trim_canvas.create_rectangle(start_pos, 0, end_pos, height, fill="lightblue", outline="")
        
        # Draw handles
        marker_width = 8
        self.trim_canvas.create_rectangle(
            start_pos - marker_width/2, 0, 
            start_pos + marker_width/2, height,
            fill="blue", outline="")
        
        self.trim_canvas.create_rectangle(
            end_pos - marker_width/2, 0, 
            end_pos + marker_width/2, height,
            fill="blue", outline="")
            
        # Update trim labels
        self.trim_in_label.config(text=str(self.trim_start_frame.get()))
        self.trim_out_label.config(text=str(self.trim_end_frame.get()))
    
    def clear_trim_display(self):
        """Clear trim display canvas"""
        self.trim_canvas.delete("all")
    
    def on_trim_click(self, event):
        """Handle trim timeline clicks"""
        if not self.trim_enabled.get() or self.cap is None:
            return
            
        width = self.trim_canvas.winfo_width()
        
        # Calculate clicked position as frame number
        frame_pos = int((event.x / width) * self.total_frames)
        frame_pos = max(0, min(frame_pos, self.total_frames - 1))
        
        # Determine if clicked on trim handle (within 5 pixels)
        start_pos = (self.trim_start_frame.get() / max(1, self.total_frames - 1)) * width
        end_pos = (self.trim_end_frame.get() / max(1, self.total_frames - 1)) * width
        
        if abs(event.x - start_pos) <= 5:
            # Clicked on start handle
            self.dragging_start = True
            self.dragging_end = False
        elif abs(event.x - end_pos) <= 5:
            # Clicked on end handle
            self.dragging_start = False
            self.dragging_end = True
        else:
            # Clicked elsewhere - go to that frame
            self.frame_index = frame_pos
            self.show_current_frame()
            self.dragging_start = False
            self.dragging_end = False
    
    def on_trim_drag(self, event):
        """Handle dragging trim handles"""
        if not self.trim_enabled.get() or not (self.dragging_start or self.dragging_end):
            return
            
        width = self.trim_canvas.winfo_width()
        
        # Calculate frame from position
        frame_pos = int((event.x / width) * self.total_frames)
        frame_pos = max(0, min(frame_pos, self.total_frames - 1))
        
        if self.dragging_start:
            # Ensure start doesn't go beyond end
            frame_pos = min(frame_pos, self.trim_end_frame.get() - 1)
            self.trim_start_frame.set(frame_pos)
        elif self.dragging_end:
            # Ensure end doesn't go below start
            frame_pos = max(frame_pos, self.trim_start_frame.get() + 1)
            self.trim_end_frame.set(frame_pos)
        
        self.update_trim_display()
    
    def on_trim_release(self, event):
        """Handle releasing trim handles"""
        self.dragging_start = False
        self.dragging_end = False
    
    def toggle_frame_range(self):
        """Toggle processing range entries"""
        if self.blur_entire_video.get():
            self.start_frame_entry.config(state="disabled")
            self.end_frame_entry.config(state="disabled")
        else:
            self.start_frame_entry.config(state="normal")
            self.end_frame_entry.config(state="normal")
    
    def on_slider_change(self, event):
        """Handle frame slider change"""
        if self.cap is None:
            return
        
        # Prevent recursive updates
        if hasattr(self, 'updating_slider') and self.updating_slider:
            return
            
        try:
            self.updating_slider = True
            frame_num = int(float(self.frame_slider.get()))
            if frame_num != self.frame_index:
                self.frame_index = max(0, min(frame_num, self.total_frames - 1))
                self.show_current_frame()
        finally:
            self.updating_slider = False
    
    def next_frame(self):
        """Go to next frame"""
        if self.cap is None:
            return
            
        if self.frame_index < self.total_frames - 1:
            self.frame_index += 1
            self.show_current_frame()
    
    def prev_frame(self):
        """Go to previous frame"""
        if self.cap is None:
            return
            
        if self.frame_index > 0:
            self.frame_index -= 1
            self.show_current_frame()
    
    def jump_frames(self, offset):
        """Jump multiple frames forward/backward"""
        if self.cap is None:
            return
            
        new_frame = max(0, min(self.frame_index + offset, self.total_frames - 1))
        if new_frame != self.frame_index:
            self.frame_index = new_frame
            self.show_current_frame()
    
    def update_shapes_listbox(self):
        """Update shapes listbox with current items"""
        self.shapes_listbox.delete(0, tk.END)
        for i, shape in enumerate(self.shapes):
            shape_type = shape[0]
            mask_type = shape[2]
            
            # Include frame range if specified
            if len(shape) >= 7:
                start, end = shape[5], shape[6]
                self.shapes_listbox.insert(tk.END, f"{i+1}. {shape_type} - {mask_type} (Frames {start}-{end})")
            else:
                self.shapes_listbox.insert(tk.END, f"{i+1}. {shape_type} - {mask_type}")
    
    def on_shape_selected(self, event):
        """Handle shape selection in listbox"""
        selection = self.shapes_listbox.curselection()
        if not selection:
            return
            
        idx = selection[0]
        if idx >= len(self.shapes):
            return
            
        shape = self.shapes[idx]
        
        # Set frame range entries
        if len(shape) >= 7:
            start, end = shape[5], shape[6]
        else:
            start, end = 0, self.total_frames - 1
            
        self.shape_start_frame.delete(0, tk.END)
        self.shape_start_frame.insert(0, str(start))
        
        self.shape_end_frame.delete(0, tk.END)
        self.shape_end_frame.insert(0, str(end))
        
        # Highlight the shape in the preview
        self.show_current_frame(highlight_shape_idx=idx)
    
    def set_shape_frame_range(self):
        """Set frame range for selected shape"""
        selection = self.shapes_listbox.curselection()
        if not selection:
            self.status_text.set("No shape selected")
            return
            
        idx = selection[0]
        if idx >= len(self.shapes):
            return
            
        try:
            start = int(self.shape_start_frame.get())
            end = int(self.shape_end_frame.get())
            
            # Validate range
            start = max(0, min(start, self.total_frames - 1))
            end = max(start, min(end, self.total_frames - 1))
            
            # Update shape
            shape_list = list(self.shapes[idx])
            if len(shape_list) < 7:
                shape_list.extend([0, self.total_frames - 1])
            
            shape_list[5] = start
            shape_list[6] = end
            
            self.shapes[idx] = tuple(shape_list)
            
            self.update_shapes_listbox()
            self.show_current_frame()
            self.status_text.set(f"Shape {idx+1} set to appear in frames {start}-{end}")
            
        except ValueError:
            self.status_text.set("Invalid frame numbers")
    
    def delete_selected_shape(self):
        """Delete selected shape"""
        selection = self.shapes_listbox.curselection()
        if not selection:
            return
            
        idx = selection[0]
        if idx < len(self.shapes):
            del self.shapes[idx]
            self.update_shapes_listbox()
            self.show_current_frame()
    
    def clear_shapes(self):
        """Clear all shapes"""
        self.shapes = []
        self.update_shapes_listbox()
        self.show_current_frame()
    
    def set_drawing_mode(self, mode):
        """Set drawing tool mode"""
        self.current_shape_type = mode
        self.status_text.set(f"Selected drawing mode: {mode}")
    
    def choose_color(self):
        """Open color picker for solid mask color"""
        color = colorchooser.askcolor(title="Choose mask color")
        if color[0]:
            r, g, b = [int(c) for c in color[0]]
            self.mask_color = (b, g, r)  # Convert to BGR for OpenCV
            self.status_text.set(f"Mask color set to RGB: {r},{g},{b}")
    
    def start_crop_drawing(self):
        """Start drawing crop region"""
        if self.current_frame is None:
            self.status_text.set("Please open a video first")
            return
            
        self.drawing_crop = True
        self.crop_x = self.crop_y = self.crop_width = self.crop_height = 0
        self.status_text.set("Click and drag to define crop region")
    
    def reset_crop(self):
        """Reset crop region"""
        self.crop_x = self.crop_y = self.crop_width = self.crop_height = 0
        self.crop_enabled.set(False)
        self.update_crop_info()
        self.show_current_frame()
    
    def update_crop_info(self):
        """Update crop dimension display"""
        if self.crop_width > 0 and self.crop_height > 0:
            self.crop_info_label.config(text=f"{self.crop_width}x{self.crop_height}")
        else:
            self.crop_info_label.config(text="Not set")
    
    def show_current_frame(self, highlight_shape_idx=None):
        """Display current frame with all effects"""
        if self.cap is None:
            return
            
        # Update slider position and frame counter
        if not hasattr(self, 'updating_slider') or not self.updating_slider:
            self.updating_slider = True
            self.frame_slider.set(self.frame_index)
            self.updating_slider = False
            
        self.frame_counter.config(text=f"{self.frame_index+1}/{self.total_frames}")
        
        # Seek to frame
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_index)
        ret, frame = self.cap.read()
        
        if not ret:
            self.status_text.set("Failed to read frame")
            return
            
        # Store original frame
        self.current_frame = frame.copy()
        
        # Process the frame with all effects
        processed = self.process_frame(frame)
        
        # Convert to RGB for display
        rgb_frame = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
        
        # Calculate scale factor to fit display
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        if canvas_width < 10 or canvas_height < 10:  # Canvas not yet rendered
            self.canvas.config(width=800, height=600)  # Set default size
            canvas_width, canvas_height = 800, 600
        
        frame_height, frame_width = rgb_frame.shape[:2]
        scale = min(canvas_width / frame_width, canvas_height / frame_height)
        
        # Don't allow upscaling
        if scale > 1.0:
            scale = 1.0
            
        # Calculate new dimensions
        new_width = int(frame_width * scale)
        new_height = int(frame_height * scale)
        
        # Resize frame
        scaled_frame = cv2.resize(rgb_frame, (new_width, new_height))
        
        # Store scale for coordinate conversion
        self.scale_factor = scale
        
        # Create PyTk image
        self.photo = ImageTk.PhotoImage(image=Image.fromarray(scaled_frame))
        
        # Clear canvas
        self.canvas.delete("all")
        
        # Center the image on canvas
        x_offset = max(0, (canvas_width - new_width) // 2)
        y_offset = max(0, (canvas_height - new_height) // 2)
        
        # Store offsets for coordinate conversion
        self.x_offset = x_offset
        self.y_offset = y_offset
        
        # Display the image
        self.canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=self.photo)
        
        # Draw visualization overlays
        self.draw_overlays(highlight_shape_idx)
        
        # Update trim display if enabled
        if self.trim_enabled.get():
            self.update_trim_display()
            
        # Update status with active elements
        active_shapes = sum(1 for s in self.shapes if len(s) < 7 or 
                           (s[5] <= self.frame_index <= s[6]))
        self.status_text.set(f"Frame {self.frame_index+1}/{self.total_frames} | " +
                           f"Active shapes: {active_shapes} | " +
                           f"Faces: {len(self.tracked_faces)}")
    
    def process_frame(self, frame):
        """Process frame with all active effects"""
        result = frame.copy()
        
        # Apply rotation if enabled
        if self.rotation_enabled.get() and self.rotation_angle.get() != 0:
            result = self.rotate_frame(result, self.rotation_angle.get())
        
        # Face detection/tracking
        if self.auto_detect_faces and self.rtmpose_initialized:
            # Re-detect periodically
            if self.frame_index % self.detection_frequency == 0 or not self.tracked_faces:
                self.tracked_faces = self.detect_faces(frame)
                
            if self.tracked_faces:
                face_mask = self.create_face_mask(frame)
                result = self.apply_mask_effect(result, face_mask, self.mask_type, 
                                              self.blur_strength, self.mask_color)
        
        # Apply manual shapes
        for shape in self.shapes:
            # Check if active for current frame
            if len(shape) >= 7:
                if self.frame_index < shape[5] or self.frame_index > shape[6]:
                    continue
                    
            shape_type, points, mask_type, strength, color = shape[:5]
            
            # Create shape mask
            height, width = frame.shape[:2]
            shape_mask = np.zeros((height, width), dtype=np.uint8)
            
            if shape_type == "rectangle":
                x1, y1 = points[0]
                x2, y2 = points[1]
                x_min, x_max = min(x1, x2), max(x1, x2)
                y_min, y_max = min(y1, y2), max(y1, y2)
                cv2.rectangle(shape_mask, (x_min, y_min), (x_max, y_max), 255, -1)
                
            elif shape_type in ("polygon", "freehand"):
                points_array = np.array(points, np.int32).reshape((-1, 1, 2))
                cv2.fillPoly(shape_mask, [points_array], 255)
            
            # Apply effect to this shape
            result = self.apply_mask_effect(result, shape_mask, mask_type, strength, color)
        
        # Apply crop preview if enabled
        if self.crop_enabled.get() and self.crop_width > 0 and self.crop_height > 0:
            # Always show preview regardless of frame range settings
            if self.crop_type.get() == "mask":
                # Create inverse mask (everything outside crop area)
                height, width = frame.shape[:2]
                crop_mask = np.ones((height, width), dtype=np.uint8) * 255
                
                x, y = self.crop_x, self.crop_y
                w, h = self.crop_width, self.crop_height
                
                # Clear mask in crop region (keep this area)
                crop_mask[y:y+h, x:x+w] = 0
                
                # Apply effect to outside area
                result = self.apply_mask_effect(
                    result, crop_mask, self.crop_mask_type.get(), 
                    self.blur_strength, self.mask_color
                )
        
        return result
    
    def draw_overlays(self, highlight_shape_idx=None):
        """Draw visualization overlays on canvas"""
        # Draw manual shapes outlines
        for i, shape in enumerate(self.shapes):
            # Skip if not visible in current frame
            if len(shape) >= 7 and (self.frame_index < shape[5] or self.frame_index > shape[6]):
                continue
                
            shape_type, points = shape[0], shape[1]
            
            # Set color - highlight selected shape
            color = "yellow" if i == highlight_shape_idx else "red"
            
            if shape_type == "rectangle":
                x1, y1 = points[0]
                x2, y2 = points[1]
                
                # Convert to canvas coordinates
                cx1, cy1 = self.img_to_canvas(x1, y1)
                cx2, cy2 = self.img_to_canvas(x2, y2)
                
                self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=color, width=2)
                
            elif shape_type in ("polygon", "freehand"):
                # Convert all points to canvas coordinates
                canvas_points = []
                for x, y in points:
                    cx, cy = self.img_to_canvas(x, y)
                    canvas_points.append(cx)
                    canvas_points.append(cy)
                    
                self.canvas.create_polygon(*canvas_points, fill="", outline=color, width=2)
        
        # Draw tracked faces
        for face_id, (x, y, w, h), _, _ in self.tracked_faces:
            # Convert to canvas coordinates
            cx1, cy1 = self.img_to_canvas(x, y)
            cx2, cy2 = self.img_to_canvas(x+w, y+h)
            
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="lime", width=2)
            self.canvas.create_text(cx1, cy1-10, text=f"ID:{face_id}", fill="lime", anchor=tk.W)
        
        # Draw crop region if set
        if self.crop_width > 0 and self.crop_height > 0:
            cx1, cy1 = self.img_to_canvas(self.crop_x, self.crop_y)
            cx2, cy2 = self.img_to_canvas(self.crop_x + self.crop_width, 
                                        self.crop_y + self.crop_height)
            
            # Dash pattern for rectangle
            dash_pattern = (5, 5)
            crop_color = "green" if self.crop_enabled.get() else "gray"
            
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2, 
                                       outline=crop_color, width=2, 
                                       dash=dash_pattern)
            
            # Add crop dimensions text
            self.canvas.create_text(cx1, cy1-10, 
                                  text=f"Crop: {self.crop_width}x{self.crop_height}", 
                                  fill=crop_color, anchor=tk.W)
    
    def img_to_canvas(self, x, y):
        """Convert image coordinates to canvas coordinates"""
        canvas_x = int(x * self.scale_factor) + self.x_offset
        canvas_y = int(y * self.scale_factor) + self.y_offset
        return canvas_x, canvas_y
    
    def canvas_to_img(self, canvas_x, canvas_y):
        """Convert canvas coordinates to image coordinates"""
        img_x = int((canvas_x - self.x_offset) / self.scale_factor)
        img_y = int((canvas_y - self.y_offset) / self.scale_factor)
        return img_x, img_y
    
    def on_mouse_down(self, event):
        """Handle mouse down event for drawing"""
        if self.current_frame is None:
            return
        
        # Convert canvas coordinates to image coordinates
        x, y = self.canvas_to_img(event.x, event.y)
        
        # Ensure coordinates are within image bounds
        img_h, img_w = self.current_frame.shape[:2]
        if x < 0 or x >= img_w or y < 0 or y >= img_h:
            return
        
        if self.drawing_crop:
            # Start crop drawing
            self.crop_x = x
            self.crop_y = y
            
            # Create temp rectangle on canvas
            cx, cy = self.img_to_canvas(x, y)
            self.temp_crop_rect = self.canvas.create_rectangle(
                cx, cy, cx, cy, outline="green", width=2, dash=(5,5))
            return
        
        if self.current_shape_type == "rectangle":
            self.drawing = True
            self.current_shape = [(x, y)]
            
            # Create temp rectangle on canvas
            cx, cy = self.img_to_canvas(x, y)
            self.temp_shape_id = self.canvas.create_rectangle(
                cx, cy, cx, cy, outline="red", width=2)
                
        elif self.current_shape_type == "polygon":
            if not self.drawing:
                self.drawing = True
                self.current_shape = [(x, y)]
                
                # Draw first point
                cx, cy = self.img_to_canvas(x, y)
                self.temp_shape_id = self.canvas.create_oval(
                    cx-3, cy-3, cx+3, cy+3, fill="red", outline="red")
            else:
                # Add point to polygon
                self.current_shape.append((x, y))
                
                # Draw line to previous point
                prev_x, prev_y = self.current_shape[-2]
                prev_cx, prev_cy = self.img_to_canvas(prev_x, prev_y)
                cx, cy = self.img_to_canvas(x, y)
                
                self.canvas.create_line(prev_cx, prev_cy, cx, cy, fill="red", width=2)
                self.canvas.create_oval(cx-3, cy-3, cx+3, cy+3, fill="red", outline="red")
                
        elif self.current_shape_type == "freehand":
            self.drawing = True
            self.current_shape = [(x, y)]
            
            # Draw first point
            cx, cy = self.img_to_canvas(x, y)
            self.temp_shape_id = self.canvas.create_oval(
                cx-3, cy-3, cx+3, cy+3, fill="red", outline="red")
    
    def on_mouse_move(self, event):
        """Handle mouse movement during drawing"""
        if not self.drawing and not self.drawing_crop:
            return
            
        # Convert canvas coordinates to image coordinates
        x, y = self.canvas_to_img(event.x, event.y)
        
        # Ensure coordinates are within image bounds
        img_h, img_w = self.current_frame.shape[:2]
        x = max(0, min(x, img_w-1))
        y = max(0, min(y, img_h-1))
        
        if self.drawing_crop:
            # Update crop rectangle
            cx, cy = self.img_to_canvas(x, y)
            start_x, start_y = self.img_to_canvas(self.crop_x, self.crop_y)
            self.canvas.coords(self.temp_crop_rect, start_x, start_y, cx, cy)
            return
            
        if self.current_shape_type == "rectangle":
            # Update rectangle
            cx, cy = self.img_to_canvas(x, y)
            start_x, start_y = self.img_to_canvas(self.current_shape[0][0], self.current_shape[0][1])
            self.canvas.coords(self.temp_shape_id, start_x, start_y, cx, cy)
            
        elif self.current_shape_type == "freehand":
            # Add point to freehand shape
            self.current_shape.append((x, y))
            
            # Draw line to previous point
            prev_x, prev_y = self.current_shape[-2]
            prev_cx, prev_cy = self.img_to_canvas(prev_x, prev_y)
            cx, cy = self.img_to_canvas(x, y)
            
            self.canvas.create_line(prev_cx, prev_cy, cx, cy, fill="red", width=2)
    
    def on_mouse_up(self, event):
        """Handle mouse release after drawing"""
        if not self.drawing and not self.drawing_crop:
            return
            
        # Convert canvas coordinates to image coordinates
        x, y = self.canvas_to_img(event.x, event.y)
        
        # Ensure coordinates are within image bounds
        img_h, img_w = self.current_frame.shape[:2]
        x = max(0, min(x, img_w-1))
        y = max(0, min(y, img_h-1))
        
        if self.drawing_crop:
            self.drawing_crop = False
            
            # Calculate crop dimensions
            width = abs(x - self.crop_x)
            height = abs(y - self.crop_y)
            
            # Ensure top-left is minimum coordinate
            if x < self.crop_x:
                self.crop_x = x
            if y < self.crop_y:
                self.crop_y = y
                
            # Set crop dimensions
            self.crop_width = width
            self.crop_height = height
            
            # Update info and enable crop
            self.update_crop_info()
            self.crop_enabled.set(True)
            
            # Refresh display
            self.show_current_frame()
            return
            
        if self.current_shape_type == "rectangle":
            self.drawing = False
            self.current_shape.append((x, y))
            
            # Add the rectangle with current settings
            self.shapes.append((
                "rectangle",
                self.current_shape,
                self.mask_type_var.get(),
                self.blur_strength,
                self.mask_color,
                self.frame_index,
                self.total_frames - 1
            ))
            
            self.current_shape = []
            self.update_shapes_listbox()
            self.show_current_frame()
            
        elif self.current_shape_type == "freehand":
            self.drawing = False
            
            # Add shape if it has enough points
            if len(self.current_shape) > 2:
                self.shapes.append((
                    "freehand",
                    self.current_shape,
                    self.mask_type_var.get(),
                    self.blur_strength,
                    self.mask_color,
                    self.frame_index,
                    self.total_frames - 1
                ))
                
                self.current_shape = []
                self.update_shapes_listbox()
                self.show_current_frame()
    
    def on_double_click(self, event):
        """Finish polygon on double-click"""
        if self.current_shape_type == "polygon" and self.drawing:
            self.drawing = False
            
            # Add polygon if it has at least 3 points
            if len(self.current_shape) >= 3:
                self.shapes.append((
                    "polygon",
                    self.current_shape,
                    self.mask_type_var.get(),
                    self.blur_strength,
                    self.mask_color,
                    self.frame_index,
                    self.total_frames - 1
                ))
                
                self.current_shape = []
                self.update_shapes_listbox()
                self.show_current_frame()
    
    def detect_faces(self, frame):
        """Detect and track faces in the frame"""
        if not self.rtmpose_initialized:
            return []
            
        try:
            # Get keypoints from RTMPose
            keypoints, scores = self.pose_tracker(frame)
            
            # Process detected people
            detections = []
            for person_idx, (person_kps, person_scores) in enumerate(zip(keypoints, scores)):
                # Extract face keypoints
                face_kps = []
                face_scores = []
                
                for idx in range(5):  # First 5 points for face
                    if idx < len(person_kps) and person_scores[idx] > 0.3:
                        face_kps.append((int(person_kps[idx][0]), int(person_kps[idx][1])))
                        face_scores.append(person_scores[idx])
                
                if len(face_kps) >= 2:
                    # Calculate bounding box
                    x_coords = [kp[0] for kp in face_kps]
                    y_coords = [kp[1] for kp in face_kps]
                    
                    x_min, x_max = min(x_coords), max(x_coords)
                    y_min, y_max = min(y_coords), max(y_coords)
                    
                    # Add padding
                    width = max(1, x_max - x_min)
                    height = max(1, y_max - y_min)
                    
                    padding_x = width * 0.5
                    padding_y = height * 0.7
                    
                    x = max(0, int(x_min - padding_x))
                    y = max(0, int(y_min - padding_y))
                    w = min(int(width + padding_x*2), frame.shape[1] - x)
                    h = min(int(height + padding_y*2), frame.shape[0] - y)
                    
                    # Calculate confidence
                    confidence = sum(face_scores) / len(face_scores) if face_scores else 0.0
                    
                    # Add to detections
                    detections.append(([x, y, w, h], confidence, "face"))
            
            # Use DeepSort if available
            if self.has_deepsort and detections:
                tracks = self.deepsort_tracker.update_tracks(detections, frame=frame)
                
                tracked_faces = []
                for track in tracks:
                    if track.is_confirmed():
                        track_id = track.track_id
                        tlwh = track.to_tlwh()
                        x, y, w, h = [int(v) for v in tlwh]
                        
                        tracked_faces.append([
                            track_id,
                            (x, y, w, h),
                            track.get_det_conf(),
                            self.frame_index
                        ])
                
                return tracked_faces
            else:
                # Basic tracking without DeepSort
                return [(i, (d[0][0], d[0][1], d[0][2], d[0][3]), d[1], self.frame_index) 
                       for i, d in enumerate(detections)]
                
        except Exception as e:
            print(f"Error in face detection: {e}")
            return []
    
    def create_face_mask(self, frame):
        """Create a mask for tracked faces"""
        height, width = frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        
        for face_id, (x, y, w, h), confidence, _ in self.tracked_faces:
            if self.mask_shape == "rectangle":
                cv2.rectangle(mask, (x, y), (x+w, y+h), 255, -1)
                
            elif self.mask_shape == "oval":
                center = (x + w // 2, y + h // 2)
                axes = (w // 2, h // 2)
                cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
                
                # Add forehead
                forehead_center = (center[0], y + h // 4)
                forehead_size = (w // 2, h // 2)
                cv2.ellipse(mask, forehead_center, forehead_size, 0, 0, 180, 255, -1)
                
            elif self.mask_shape == "precise":
                center_x = x + w // 2
                center_y = y + h // 2
                
                # Create face shape points
                face_poly = []
                
                # Top of head
                for angle in range(0, 180, 10):
                    angle_rad = np.radians(angle)
                    radius_x = w // 2
                    radius_y = int(h * 0.6)
                    px = center_x + int(radius_x * np.cos(angle_rad))
                    py = center_y - int(radius_y * np.sin(angle_rad))
                    face_poly.append((px, py))
                
                # Chin and jaw
                for angle in range(180, 360, 10):
                    angle_rad = np.radians(angle)
                    radius_x = int(w * 0.45)
                    radius_y = int(h * 0.5)
                    px = center_x + int(radius_x * np.cos(angle_rad))
                    py = center_y - int(radius_y * np.sin(angle_rad))
                    face_poly.append((px, py))
                
                # Fill polygon
                face_poly = np.array(face_poly, np.int32).reshape((-1, 1, 2))
                cv2.fillPoly(mask, [face_poly], 255)
        
        return mask
    
    def apply_mask_effect(self, frame, mask, mask_type, blur_strength=21, color=(0,0,0)):
        """Apply effect to masked area"""
        result = frame.copy()
        
        if mask_type == "blur":
            # Make sure strength is odd
            if blur_strength % 2 == 0:
                blur_strength += 1
                
            blurred = cv2.GaussianBlur(frame, (blur_strength, blur_strength), 0)
            result = np.where(mask[:, :, np.newaxis] == 255, blurred, result)
            
        elif mask_type == "pixelate":
            scale = max(1, blur_strength // 10)
            temp = cv2.resize(frame, (frame.shape[1] // scale, frame.shape[0] // scale), 
                             interpolation=cv2.INTER_LINEAR)
            pixelated = cv2.resize(temp, (frame.shape[1], frame.shape[0]), 
                                 interpolation=cv2.INTER_NEAREST)
            result = np.where(mask[:, :, np.newaxis] == 255, pixelated, result)
            
        elif mask_type == "solid":
            colored_mask = np.zeros_like(frame)
            colored_mask[:] = color
            result = np.where(mask[:, :, np.newaxis] == 255, colored_mask, result)
            
        elif mask_type == "black":
            result = np.where(mask[:, :, np.newaxis] == 255, 0, result)
            
        return result
    
    def detect_faces_current_frame(self):
        """Detect faces in current frame and add as shapes"""
        if self.current_frame is None:
            return
            
        faces = self.detect_faces(self.current_frame)
        
        for face_id, (x, y, w, h), _, _ in faces:
            if self.mask_shape == "rectangle":
                self.shapes.append((
                    "rectangle",
                    [(x, y), (x+w, y+h)],
                    self.mask_type_var.get(),
                    self.blur_strength,
                    self.mask_color,
                    self.frame_index,
                    self.total_frames - 1
                ))
            elif self.mask_shape == "oval":
                # Create oval points
                center_x, center_y = x + w // 2, y + h // 2
                rx, ry = w // 2, h // 2
                
                oval_points = []
                for angle in range(0, 360, 10):
                    rad = np.radians(angle)
                    px = center_x + int(rx * np.cos(rad))
                    py = center_y + int(ry * np.sin(rad))
                    oval_points.append((px, py))
                
                self.shapes.append((
                    "polygon",
                    oval_points,
                    self.mask_type_var.get(),
                    self.blur_strength,
                    self.mask_color,
                    self.frame_index,
                    self.total_frames - 1
                ))
            elif self.mask_shape == "precise":
                # Create precise face shape
                center_x = x + w // 2
                center_y = y + h // 2
                
                face_points = []
                
                # Top of head
                for angle in range(0, 180, 10):
                    angle_rad = np.radians(angle)
                    radius_x = w // 2
                    radius_y = int(h * 0.6)
                    px = center_x + int(radius_x * np.cos(angle_rad))
                    py = center_y - int(radius_y * np.sin(angle_rad))
                    face_points.append((px, py))
                
                # Chin and jaw
                for angle in range(180, 360, 10):
                    angle_rad = np.radians(angle)
                    radius_x = int(w * 0.45)
                    radius_y = int(h * 0.5)
                    px = center_x + int(radius_x * np.cos(angle_rad))
                    py = center_y - int(radius_y * np.sin(angle_rad))
                    face_points.append((px, py))
                
                self.shapes.append((
                    "polygon",
                    face_points,
                    self.mask_type_var.get(),
                    self.blur_strength,
                    self.mask_color,
                    self.frame_index,
                    self.total_frames - 1
                ))
        
        self.update_shapes_listbox()
        self.show_current_frame()
        self.status_text.set(f"Added {len(faces)} detected faces as shapes")
    
    def export_face_data(self):
        """Export face data to JSON"""
        if not self.tracked_faces or self.input_video is None:
            self.status_text.set("No faces to export")
            return
            
        input_filename = os.path.basename(self.input_video)
        base_name = os.path.splitext(input_filename)[0]
        
        face_data = {
            "video_file": self.input_video,
            "faces": {}
        }
        
        for face_id, (x, y, w, h), confidence, frame_idx in self.tracked_faces:
            face_data["faces"][str(face_id)] = {
                "bbox": [x, y, w, h],
                "confidence": float(confidence) if confidence is not None else 0.0,
                "frame": int(frame_idx)
            }
        
        if self.output_path:
            json_path = os.path.join(self.output_path, f"{base_name}_faces.json")
        else:
            json_path = f"{base_name}_faces.json"
            
        with open(json_path, 'w') as f:
            json.dump(face_data, f, indent=4)
            
        self.status_text.set(f"Exported face data to {json_path}")
    
    def open_video(self):
        """Open a video file"""
        video_path = filedialog.askopenfilename(filetypes=[
            ("Video files", "*.mp4;*.avi;*.mov;*.mkv;*.wmv"),
            ("All files", "*.*")
        ])
        
        if not video_path:
            return
            
        # Open the video
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            self.status_text.set("Failed to open video file")
            return
            
        # Store video info
        self.input_video = video_path
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.frame_index = 0
        
        # Reset state
        self.shapes = []
        self.tracked_faces = []
        self.crop_x = self.crop_y = self.crop_width = self.crop_height = 0
        self.crop_enabled.set(False)
        self.update_crop_info()
        
        # Reset trim
        self.trim_enabled.set(False)
        self.trim_start_frame.set(0)
        self.trim_end_frame.set(self.total_frames - 1)
        self.clear_trim_display()
        
        # Reset rotation
        self.rotation_angle.set(0)
        self.rotation_enabled.set(False)
        
        # Update slider range
        self.frame_slider.config(from_=0, to=self.total_frames-1)
        
        # Update frame range defaults
        self.start_frame.set(0)
        self.end_frame.set(self.total_frames-1)
        self.crop_start_frame.set(0)
        self.crop_end_frame.set(self.total_frames-1)
        
        # Reset trackers
        if self.rtmpose_initialized:
            self.pose_tracker.reset()
        if self.has_deepsort:
            self.deepsort_tracker.tracker.delete_all_tracks()
        
        # Get video properties
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        
        # Update shapes listbox
        self.update_shapes_listbox()
        
        # Show first frame
        self.show_current_frame()
        
        self.status_text.set(f"Opened video: {os.path.basename(video_path)} | " +
                           f"{width}x{height} | FPS: {fps:.2f} | Frames: {self.total_frames}")
    
    def set_output_path(self):
        """Set output directory"""
        path = filedialog.askdirectory()
        if path:
            self.output_path = path
            self.status_text.set(f"Output path set to: {path}")
    
    def get_video_writer(self, output_path, width, height, fps):
        """Create a video writer with appropriate codec"""
        _, ext = os.path.splitext(output_path)
        ext = ext.lower()
        
        # Map extensions to codecs
        codec_map = {
            '.mp4': 'avc1',   # H.264
            '.avi': 'XVID',
            '.mov': 'avc1',
            '.mkv': 'XVID',
            '.wmv': 'WMV2'
        }
        
        fourcc_str = codec_map.get(ext, 'avc1')  # Default to H.264
        
        # Try selected codec
        fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height), isColor=True)
        
        # If failed, try fallbacks
        if not out.isOpened():
            for codec in ['mp4v', 'XVID', 'avc1', 'H264']:
                if codec == fourcc_str:
                    continue  # Skip already tried codec
                    
                fourcc = cv2.VideoWriter_fourcc(*codec)
                out = cv2.VideoWriter(output_path, fourcc, fps, (width, height), isColor=True)
                
                if out.isOpened():
                    break
        
        return out
    
    def process_video(self):
        """Process video and apply all effects"""
        # Validate inputs
        if self.input_video is None or self.output_path is None:
            self.status_text.set("Please select input video and output path")
            return
            
        # Determine output filename
        input_filename = os.path.basename(self.input_video)
        base_name, ext = os.path.splitext(input_filename)
        output_filename = f"processed_{base_name}{ext}"
        output_path = os.path.join(self.output_path, output_filename)
        
        # Get video properties
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Determine output dimensions
        if self.crop_enabled.get() and self.crop_width > 0 and self.crop_height > 0 and self.crop_type.get() == "traditional":
            output_width = self.crop_width
            output_height = self.crop_height
        else:
            output_width = width
            output_height = height
            
        # Create video writer
        out = self.get_video_writer(output_path, output_width, output_height, fps)
        
        if not out.isOpened():
            self.status_text.set("Failed to create output video. Check output path and permissions.")
            return
            
        # Determine frame range
        if self.trim_enabled.get():
            start_frame = self.trim_start_frame.get()
            end_frame = self.trim_end_frame.get()
        elif not self.blur_entire_video.get():
            start_frame = self.start_frame.get()
            end_frame = self.end_frame.get()
        else:
            start_frame = 0
            end_frame = self.total_frames - 1
            
        # Initialize face tracking data
        face_tracking_data = {
            "video_file": self.input_video,
            "frames": {},
            "faces": {}
        }
        
        # Create progress window
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Processing Video")
        progress_window.geometry("400x150")
        progress_window.transient(self.root)
        progress_window.grab_set()  # Make modal
        
        progress_label = ttk.Label(progress_window, text="Processing video frames...")
        progress_label.pack(pady=10)
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_window, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X, padx=20, pady=10)
        
        status_label = ttk.Label(progress_window, text="Starting processing...")
        status_label.pack(pady=5)
        
        # Reset trackers
        if self.rtmpose_initialized:
            self.pose_tracker.reset()
        if self.has_deepsort:
            self.deepsort_tracker.tracker.delete_all_tracks()
            
        # Start processing
        total_frames = end_frame - start_frame + 1
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        processing_start = time.time()
        current_frame_idx = start_frame
        frame_count = 0
        errors = 0
        
        try:
            # Process each frame
            while current_frame_idx <= end_frame:
                # Read frame
                ret, frame = self.cap.read()
                if not ret:
                    break
                    
                # Update progress
                progress = ((current_frame_idx - start_frame) / total_frames) * 100
                progress_var.set(progress)
                
                # Update status periodically
                if frame_count % 10 == 0:
                    elapsed = time.time() - processing_start
                    fps_processing = max(1, frame_count) / elapsed
                    eta_seconds = (total_frames - frame_count) / fps_processing
                    
                    status_text = f"Frame {frame_count+1}/{total_frames} - " \
                               f"ETA: {int(eta_seconds//60)}m {int(eta_seconds%60)}s - " \
                               f"Speed: {fps_processing:.1f} fps"
                    status_label.config(text=status_text)
                    progress_window.update()
                
                # Process frame - apply all effects
                # Apply rotation first if enabled
                if self.rotation_enabled.get() and self.rotation_angle.get() != 0:
                    result_frame = self.rotate_frame(frame, self.rotation_angle.get())
                else:
                    result_frame = frame.copy()
                
                # Face detection and tracking
                if self.auto_detect_faces and self.rtmpose_initialized:
                    # Detect faces periodically
                    if frame_count % self.detection_frequency == 0 or not self.tracked_faces:
                        self.tracked_faces = self.detect_faces(frame)
                        
                    # Store tracking data
                    if self.tracked_faces:
                        frame_faces = []
                        for face_id, (x, y, w, h), confidence, _ in self.tracked_faces:
                            # Store face data for this frame
                            face_data = {
                                "face_id": face_id,
                                "bbox": [x, y, w, h],
                                "confidence": float(confidence) if confidence is not None else 0.0
                            }
                            frame_faces.append(face_data)
                            
                            # Store face across all frames
                            if str(face_id) not in face_tracking_data["faces"]:
                                face_tracking_data["faces"][str(face_id)] = {
                                    "frames": [current_frame_idx],
                                    "bbox": [x, y, w, h],
                                    "confidence": float(confidence) if confidence is not None else 0.0
                                }
                            else:
                                face_tracking_data["faces"][str(face_id)]["frames"].append(current_frame_idx)
                                face_tracking_data["faces"][str(face_id)]["bbox"] = [x, y, w, h]
                                
                        # Store frame data
                        face_tracking_data["frames"][str(current_frame_idx)] = {
                            "faces": frame_faces
                        }
                        
                        # Apply face masking
                        face_mask = self.create_face_mask(frame)
                        result_frame = self.apply_mask_effect(
                            result_frame, face_mask, self.mask_type,
                            self.blur_strength, self.mask_color
                        )
                
                # Apply manual shapes
                for shape in self.shapes:
                    # Check if active in this frame
                    if len(shape) >= 7:
                        shape_start, shape_end = shape[5], shape[6]
                        if current_frame_idx < shape_start or current_frame_idx > shape_end:
                            continue
                    
                    # Apply shape mask
                    shape_type, points, mask_type, strength, color = shape[:5]
                    
                    # Create mask
                    shape_mask = np.zeros((height, width), dtype=np.uint8)
                    
                    if shape_type == "rectangle":
                        x1, y1 = points[0]
                        x2, y2 = points[1]
                        x_min, x_max = min(x1, x2), max(x1, x2)
                        y_min, y_max = min(y1, y2), max(y1, y2)
                        cv2.rectangle(shape_mask, (x_min, y_min), (x_max, y_max), 255, -1)
                        
                    elif shape_type in ("polygon", "freehand"):
                        points_array = np.array(points, np.int32).reshape((-1, 1, 2))
                        cv2.fillPoly(shape_mask, [points_array], 255)
                    
                    # Apply effect
                    result_frame = self.apply_mask_effect(
                        result_frame, shape_mask, mask_type, strength, color
                    )
                
                # Apply crop if enabled
                if self.crop_enabled.get() and self.crop_width > 0 and self.crop_height > 0:
                    # Check if this frame should be cropped
                    frame_in_crop_range = True
                    if not self.crop_all_frames.get():
                        crop_start = self.crop_start_frame.get()
                        crop_end = self.crop_end_frame.get()
                        frame_in_crop_range = (crop_start <= current_frame_idx <= crop_end)
                        
                    if frame_in_crop_range:
                        if self.crop_type.get() == "traditional":
                            # Cut out the region
                            x, y = self.crop_x, self.crop_y
                            w, h = self.crop_width, self.crop_height
                            
                            # Ensure within bounds
                            x = max(0, min(x, width - 1))
                            y = max(0, min(y, height - 1))
                            w = min(w, width - x)
                            h = min(h, height - y)
                            
                            # Crop
                            result_frame = result_frame[y:y+h, x:x+w]
                        else:
                            # Mask outside region
                            crop_mask = np.ones((height, width), dtype=np.uint8) * 255
                            
                            # Define region to keep
                            x, y = self.crop_x, self.crop_y
                            w, h = self.crop_width, self.crop_height
                            
                            # Ensure within bounds
                            x = max(0, min(x, width - 1))
                            y = max(0, min(y, height - 1))
                            w = min(w, width - x)
                            h = min(h, height - y)
                            
                            # Clear mask in crop region
                            crop_mask[y:y+h, x:x+w] = 0
                            
                            # Apply effect to outside area
                            result_frame = self.apply_mask_effect(
                                result_frame, crop_mask, self.crop_mask_type.get(),
                                self.blur_strength, self.mask_color
                            )
                
                # Write frame
                try:
                    out.write(result_frame)
                except Exception as e:
                    errors += 1
                    print(f"Error writing frame {current_frame_idx}: {e}")
                
                current_frame_idx += 1
                frame_count += 1
            
            # Export face tracking data if available
            if self.auto_detect_faces and self.rtmpose_initialized and face_tracking_data["faces"]:
                json_path = os.path.join(self.output_path, f"{base_name}_faces.json")
                with open(json_path, 'w') as f:
                    json.dump(face_tracking_data, f, indent=4)
                
                self.status_text.set(f"Face tracking data saved to {json_path}")
        
        except Exception as e:
            self.status_text.set(f"Error during processing: {str(e)}")
            import traceback
            traceback.print_exc()
            
        finally:
            # Clean up
            out.release()
            progress_window.destroy()
            
            processing_time = time.time() - processing_start
            
            if errors > 0:
                self.status_text.set(f"Video processing completed with {errors} errors " +
                                  f"in {processing_time:.1f}s. Saved to {output_path}")
            else:
                self.status_text.set(f"Video processing completed in {processing_time:.1f}s. " +
                                  f"Saved to {output_path}")
            
            # Reset to first frame
            self.frame_index = 0
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.show_current_frame()


# Main
if __name__ == "__main__":
    root = tk.Tk()
    app = VideoBlurApp(root)
    root.geometry("1280x800")
    root.minsize(1024, 768)
    root.mainloop()