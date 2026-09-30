import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import time
import serial
import serial.tools.list_ports

# ============================================================
# CONFIGURATION
# ============================================================
BAUD_RATE = 115200
SEND_INTERVAL_MS = 50
XY_MAX_SPEED = 24000
Z_MAX_SPEED = 5000
DEFAULT_SPEEDS = {"X": 24000, "Y": 24000, "Z": 5000}

# Light Mode Theme Settings
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

class VenipunctureDashboard(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color="#f8fafc") # Soft off-white main background

        self.title("Robotic Venipuncture System")
        self.geometry("1000x700")
        self.minsize(900, 600)

        # Serial & Motion State[cite: 1]
        self.ser = None
        self.connected = False
        self.stop_latched = True
        self.reset_pending = False
        self.held_keys = set()
        self.last_packet = 0.0
        self.last_status_request = 0.0
        self.position = [0, 0, 0]
        self.speeds = DEFAULT_SPEEDS.copy()
        self.auto_state = 0 
        
        # Grid Layout (1 Row, 2 Columns: Sidebar & Main)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.build_sidebar()
        self.build_main_area()
        self.bind_keys()
        self.after(SEND_INTERVAL_MS, self.update_loop)

    # ========================================================
    # UI CONSTRUCTION
    # ========================================================
    def build_sidebar(self):
        # Slate-blue tinted sidebar
        self.sidebar = ctk.CTkFrame(self, width=260, corner_radius=0, fg_color="#e2e8f0")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1) # Spacer

        # Title
        ctk.CTkLabel(self.sidebar, text="Venipuncture\nController", font=ctk.CTkFont(size=24, weight="bold"), text_color="#0f172a").grid(row=0, column=0, padx=20, pady=(30, 20))

        # Connection Card (White)
        conn_frame = ctk.CTkFrame(self.sidebar, fg_color="#ffffff", corner_radius=8, border_width=1, border_color="#cbd5e1")
        conn_frame.grid(row=1, column=0, padx=15, pady=10, sticky="ew")
        
        ctk.CTkLabel(conn_frame, text="Hardware Connection", font=ctk.CTkFont(size=14, weight="bold"), text_color="#334155").pack(pady=(10, 5))
        
        self.port_var = ctk.StringVar(value="COM3")
        self.port_combo = ctk.CTkComboBox(conn_frame, variable=self.port_var, values=self.get_ports(), fg_color="#f1f5f9", text_color="#0f172a")
        self.port_combo.pack(padx=15, pady=5, fill="x")
        
        btn_row = ctk.CTkFrame(conn_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=(5, 10))
        ctk.CTkButton(btn_row, text="Refresh", width=70, fg_color="#3b82f6", hover_color="#2563eb", command=self.refresh_ports).pack(side="left", expand=True, padx=(0, 5))
        self.connect_btn = ctk.CTkButton(btn_row, text="Connect", width=70, fg_color="#3b82f6", hover_color="#2563eb", command=self.connect)
        self.connect_btn.pack(side="right", expand=True, padx=(5, 0))

        # Status Indicators (White)
        status_frame = ctk.CTkFrame(self.sidebar, fg_color="#ffffff", corner_radius=8, border_width=1, border_color="#cbd5e1")
        status_frame.grid(row=2, column=0, padx=15, pady=10, sticky="ew")
        
        self.status_lbl = ctk.CTkLabel(status_frame, text="Disconnected", text_color="#dc2626", font=ctk.CTkFont(weight="bold"))
        self.status_lbl.pack(pady=10)

        # Critical Controls (Bottom of Sidebar)
        self.reset_btn = ctk.CTkButton(self.sidebar, text="RESET / ENABLE", height=45, fg_color="#0f172a", hover_color="#334155", command=self.reset_controller)
        self.reset_btn.grid(row=6, column=0, padx=15, pady=(10, 5), sticky="ew")
        
        self.estop_btn = ctk.CTkButton(self.sidebar, text="EMERGENCY STOP", height=45, fg_color="#dc2626", hover_color="#b91c1c", text_color="white", font=ctk.CTkFont(weight="bold"), command=self.emergency_stop)
        self.estop_btn.grid(row=7, column=0, padx=15, pady=(5, 20), sticky="ew")

    def build_main_area(self):
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        self.tabview = ctk.CTkTabview(self.main_frame, corner_radius=10, fg_color="#ffffff", segmented_button_fg_color="#e2e8f0", segmented_button_selected_color="#ffffff", segmented_button_selected_hover_color="#f8fafc", text_color="#0f172a")
        self.tabview.pack(fill="both", expand=True)

        self.tab_pilot = self.tabview.add("Manual Pilot")
        self.tab_auto = self.tabview.add("Autonomous Mode")

        self.build_pilot_tab()
        self.build_auto_tab()

    def build_pilot_tab(self):
        # HUD for Position
        hud_frame = ctk.CTkFrame(self.tab_pilot, fg_color="transparent")
        hud_frame.pack(fill="x", pady=(10, 20))
        hud_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        self.pos_vars = {}
        colors = ["#2563eb", "#16a34a", "#7c3aed"] # Darker blue, green, purple for light mode

        for i, axis in enumerate(["X", "Y", "Z"]):
            card = ctk.CTkFrame(hud_frame, fg_color="#ffffff", corner_radius=10, border_width=1, border_color="#e2e8f0")
            card.grid(row=0, column=i, padx=10, sticky="ew")
            
            ctk.CTkLabel(card, text=f"{axis} AXIS", font=ctk.CTkFont(size=12, weight="bold"), text_color=colors[i]).pack(pady=(15, 0))
            self.pos_vars[axis] = ctk.StringVar(value="0")
            ctk.CTkLabel(card, textvariable=self.pos_vars[axis], font=ctk.CTkFont(size=32, weight="bold"), text_color="#0f172a").pack(pady=(0, 15))

        # Speed Controls
        speed_frame = ctk.CTkFrame(self.tab_pilot, corner_radius=10, fg_color="#f1f5f9", border_width=1, border_color="#e2e8f0")
        speed_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(speed_frame, text="Speed Configuration (Microsteps/sec)", font=ctk.CTkFont(weight="bold"), text_color="#334155").pack(pady=(15, 10))
        
        for axis in ["X", "Y", "Z"]:
            row = ctk.CTkFrame(speed_frame, fg_color="transparent")
            row.pack(fill="x", padx=30, pady=10)
            
            ctk.CTkLabel(row, text=f"{axis}:", width=30, font=ctk.CTkFont(weight="bold"), text_color="#0f172a").pack(side="left")
            max_spd = XY_MAX_SPEED if axis != "Z" else Z_MAX_SPEED
            slider = ctk.CTkSlider(row, from_=5, to=max_spd, command=lambda val, a=axis: self.speed_changed(a, val))
            slider.set(self.speeds[axis])
            slider.pack(side="left", fill="x", expand=True, padx=20)

        ctk.CTkLabel(self.tab_pilot, text="Keyboard Controls: W/A/S/D for X/Y  |  Q/E for Z Actuator  |  SPACE for E-Stop", text_color="#64748b").pack(side="bottom", pady=20)

    def build_auto_tab(self):
        self.tab_auto.grid_columnconfigure(0, weight=3)
        self.tab_auto.grid_columnconfigure(1, weight=2)
        self.tab_auto.grid_rowconfigure(0, weight=1)

        # Camera Feed Box (Kept Dark for screen illusion)
        self.cam_frame = ctk.CTkFrame(self.tab_auto, corner_radius=10, fg_color="#1e293b")
        self.cam_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.cam_label = ctk.CTkLabel(self.cam_frame, text="[ SYSTEM IDLE ]\nAwaiting Sequence Start", text_color="#94a3b8", font=ctk.CTkFont(size=18))
        self.cam_label.pack(expand=True)

        # Sequence Panel
        self.ctrl_frame = ctk.CTkFrame(self.tab_auto, corner_radius=10, fg_color="#f1f5f9", border_width=1, border_color="#e2e8f0")
        self.ctrl_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        ctk.CTkLabel(self.ctrl_frame, text="Injection Sequence", font=ctk.CTkFont(size=18, weight="bold"), text_color="#0f172a").pack(pady=20)

        self.btn_scan = ctk.CTkButton(self.ctrl_frame, text="1. Run Vein Detection", height=40, text_color="white", command=self.auto_step_1)
        self.btn_scan.pack(fill="x", padx=25, pady=10)

        self.btn_confirm_site = ctk.CTkButton(self.ctrl_frame, text="2. Approve Target & Align", height=40, state="disabled", text_color="white", command=self.auto_step_2)
        self.btn_confirm_site.pack(fill="x", padx=25, pady=10)

        self.btn_insert = ctk.CTkButton(self.ctrl_frame, text="3. CONFIRM INSERTION", height=45, fg_color="#dc2626", hover_color="#b91c1c", text_color="white", font=ctk.CTkFont(weight="bold"), state="disabled", command=self.auto_step_3)
        self.btn_insert.pack(fill="x", padx=25, pady=10)

        self.btn_retract = ctk.CTkButton(self.ctrl_frame, text="4. Safe Retract", height=40, state="disabled", text_color="white", command=self.auto_step_4)
        self.btn_retract.pack(fill="x", padx=25, pady=10)

    # ========================================================
    # AUTO MODE LOGIC
    # ========================================================
    def auto_step_1(self):
        self.cam_label.configure(text="[ CAMERA ACTIVE ]\nTracking Algorithms Running...", text_color="#38bdf8")
        self.btn_scan.configure(state="disabled")
        self.btn_confirm_site.configure(state="normal")
        self.auto_state = 1

    def auto_step_2(self):
        if messagebox.askyesno("Alignment", "Gantry will move to coordinate X/Y. Clear path?"):
            self.send_line("M,1,1,0") 
            self.after(2000, lambda: self.send_line("M,0,0,0"))
            self.cam_label.configure(text="[ ALIGNED ]\nTarget Acquired. Ready for Z-axis.", text_color="#34d399")
            self.btn_confirm_site.configure(state="disabled")
            self.btn_insert.configure(state="normal")
            self.auto_state = 2

    def auto_step_3(self):
        if messagebox.askyesno("CRITICAL", "Confirm needle insertion?"):
            self.send_line("M,0,0,1")
            self.after(1000, lambda: self.send_line("M,0,0,0"))
            self.cam_label.configure(text="[ INSERTED ]\nProcedure in progress.", text_color="#f87171")
            self.btn_insert.configure(state="disabled")
            self.btn_retract.configure(state="normal")
            self.auto_state = 3

    def auto_step_4(self):
        self.send_line("M,0,0,-1")
        self.after(1000, lambda: self.send_line("M,0,0,0"))
        self.cam_label.configure(text="[ SYSTEM IDLE ]\nRetracted Safely.", text_color="#94a3b8")
        self.btn_retract.configure(state="disabled")
        self.btn_scan.configure(state="normal")
        self.auto_state = 0

    # ========================================================
    # HARDWARE COMMUNICATION & CONTROL[cite: 1]
    # ========================================================
    def get_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]

    def refresh_ports(self):
        ports = self.get_ports()
        self.port_combo.configure(values=ports)
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])

    def connect(self):
        if self.connected:
            self.disconnect()
            return
        try:
            self.ser = serial.Serial(self.port_var.get(), BAUD_RATE, timeout=0.01, write_timeout=0.1)
            time.sleep(2)
            self.ser.reset_input_buffer()
            self.connected, self.stop_latched, self.reset_pending = True, True, False
            self.held_keys.clear()
            self.status_lbl.configure(text="Connected (LOCKED)", text_color="#d97706")
            self.connect_btn.configure(text="Disconnect")
            self.after(100, self.reset_controller)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def disconnect(self):
        self.held_keys.clear()
        if self.ser:
            self.send_line("STOP")
            self.ser.close()
        self.ser, self.connected, self.stop_latched = None, False, True
        self.connect_btn.configure(text="Connect")
        self.status_lbl.configure(text="Disconnected", text_color="#dc2626")

    def send_line(self, text):
        if not self.connected or not self.ser: return False
        try:
            self.ser.write((text + "\n").encode("ascii"))
            return True
        except:
            self.disconnect()
            return False

    def reset_controller(self):
        if not self.connected: return
        self.held_keys.clear()
        self.reset_pending, self.stop_latched = True, True
        if self.send_line("RESET"):
            self.status_lbl.configure(text="Awaiting Reset...", text_color="#d97706")

    def emergency_stop(self, event=None):
        self.held_keys.clear()
        self.stop_latched, self.reset_pending = True, False
        if self.connected: self.send_line("STOP")
        self.status_lbl.configure(text="STOP LATCHED", text_color="#dc2626")

    def speed_changed(self, axis, value):
        self.speeds[axis] = int(float(value))
        if self.connected and not self.stop_latched:
            self.send_line(f"S,{self.speeds['X']},{self.speeds['Y']},{self.speeds['Z']}")

    # ========================================================
    # KEYBOARD EVENTS & UPDATE LOOP[cite: 1]
    # ========================================================
    def bind_keys(self):
        self.bind("<KeyPress>", self.key_down)
        self.bind("<KeyRelease>", self.key_up)
        self.bind("<FocusOut>", lambda e: self.held_keys.clear())

    def key_down(self, event):
        key = event.keysym.lower()
        if key == "space":
            self.emergency_stop()
            return "break"
        if key in ("w", "a", "s", "d", "q", "e", "up", "down", "left", "right") and self.connected and not self.stop_latched:
            self.held_keys.add(key)
            return "break"

    def key_up(self, event):
        self.held_keys.discard(event.keysym.lower())

    def update_loop(self):
        if self.connected:
            try:
                while self.ser and self.ser.in_waiting:
                    line = self.ser.readline().decode("ascii", errors="ignore").strip()
                    self.process_serial_line(line)
            except:
                self.disconnect()

            now = time.monotonic()
            if now - self.last_packet >= SEND_INTERVAL_MS / 1000:
                keys = self.held_keys
                x = int(bool(keys & {"d", "right"})) - int(bool(keys & {"a", "left"}))
                y = int(bool(keys & {"w", "up"})) - int(bool(keys & {"s", "down"}))
                z = int("e" in keys) - int("q" in keys)

                if self.stop_latched: x, y, z = 0, 0, 0
                
                if self.auto_state == 0: 
                    self.send_line(f"M,{x},{y},{z}")
                self.last_packet = now

            if now - self.last_status_request >= 0.5:
                self.send_line("STATUS")
                self.last_status_request = now

        self.after(SEND_INTERVAL_MS, self.update_loop)

    def process_serial_line(self, line):
        if not line: return
        if line == "RESET_OK":
            self.reset_pending, self.stop_latched = False, False
            self.status_lbl.configure(text="SYSTEM READY", text_color="#15803d")
            self.send_line(f"S,{self.speeds['X']},{self.speeds['Y']},{self.speeds['Z']}")
        elif line == "STOPPED":
            self.reset_pending, self.stop_latched = False, True
            self.status_lbl.configure(text="STOP LATCHED", text_color="#dc2626")
        elif line.startswith("POS,"):
            vals = line.split(",")
            if len(vals) == 4:
                try:
                    for i, axis in enumerate(["X", "Y", "Z"]):
                        self.pos_vars[axis].set(vals[i+1])
                except ValueError: pass

if __name__ == "__main__":
    app = VenipunctureDashboard()
    app.mainloop()