import tkinter as tk
from tkinter import ttk, messagebox
import time
import serial
import serial.tools.list_ports


# ============================================================
# CONFIGURATION
# ============================================================

BAUD_RATE = 115200

# How frequently movement commands are sent
SEND_INTERVAL_MS = 50

# 1/16 microstepping
MICROSTEPS = 8

# Change these values in venipuncture_control.py
XY_MAX_SPEED = 24000
Z_MAX_SPEED = 5000

DEFAULT_SPEEDS = {
    "X": 24000,
    "Y": 24000,
    "Z": 5000
}


class ControllerApp:

    def __init__(self, root):

        self.root = root

        self.root.title(
            "Venipuncture Robot Controller"
        )

        self.root.geometry(
            "620x600"
        )

        self.root.minsize(
            540,
            500
        )


        # ----------------------------------------------------
        # SERIAL STATE
        # ----------------------------------------------------

        self.ser = None

        self.connected = False

        # True = controller locked
        # False = controller enabled
        self.stop_latched = True

        # Arduino RESET handshake
        self.reset_pending = False

        # Keyboard state
        self.held_keys = set()

        # Timing
        self.last_packet = 0.0
        self.last_status_request = 0.0

        # Position
        self.position = [0, 0, 0]

        # Speeds
        self.speeds = DEFAULT_SPEEDS.copy()


        # ----------------------------------------------------
        # TK VARIABLES
        # ----------------------------------------------------

        self.port_var = tk.StringVar(
            value="COM3"
        )

        self.status_var = tk.StringVar(
            value="Disconnected"
        )

        self.position_vars = [

            tk.StringVar(
                value="0 microsteps"
            ),

            tk.StringVar(
                value="0 microsteps"
            ),

            tk.StringVar(
                value="0 microsteps"
            ),
        ]


        self.speed_vars = {

            axis: tk.IntVar(
                value=value
            )

            for axis, value
            in self.speeds.items()
        }


        # ----------------------------------------------------
        # BUILD GUI
        # ----------------------------------------------------

        self.build_ui()


        # ----------------------------------------------------
        # KEYBOARD EVENTS
        # ----------------------------------------------------

        self.root.bind(
            "<KeyPress>",
            self.key_down
        )

        self.root.bind(
            "<KeyRelease>",
            self.key_up
        )

        self.root.bind(
            "<FocusOut>",
            self.clear_keys
        )


        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close_app
        )


        # ----------------------------------------------------
        # MAIN LOOP
        # ----------------------------------------------------

        self.root.after(
            SEND_INTERVAL_MS,
            self.update_loop
        )


    # ========================================================
    # GUI
    # ========================================================

    def build_ui(self):

        main = ttk.Frame(
            self.root,
            padding=14
        )

        main.pack(
            fill="both",
            expand=True
        )


        ttk.Label(
            main,
            text="3-Axis Motion Control",
            font=("Arial", 17, "bold")
        ).pack(
            anchor="w"
        )


        ttk.Label(
            main,
            text="X/Y positioning • Z needle actuator"
        ).pack(
            anchor="w",
            pady=(0, 12)
        )


        # ----------------------------------------------------
        # CONNECTION
        # ----------------------------------------------------

        connection = ttk.LabelFrame(
            main,
            text="USB Serial Connection",
            padding=10
        )

        connection.pack(
            fill="x",
            pady=5
        )


        ttk.Label(
            connection,
            text="Port:"
        ).grid(
            row=0,
            column=0,
            sticky="w"
        )


        self.port_combo = ttk.Combobox(
            connection,
            textvariable=self.port_var,
            values=self.get_ports(),
            width=16
        )

        self.port_combo.grid(
            row=0,
            column=1,
            padx=5
        )


        ttk.Button(
            connection,
            text="Refresh",
            command=self.refresh_ports
        ).grid(
            row=0,
            column=2,
            padx=3
        )


        self.connect_button = ttk.Button(
            connection,
            text="Connect",
            command=self.connect
        )

        self.connect_button.grid(
            row=0,
            column=3,
            padx=3
        )


        ttk.Label(
            connection,
            textvariable=self.status_var
        ).grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(8, 0)
        )


        # ----------------------------------------------------
        # KEYBOARD CONTROLS
        # ----------------------------------------------------

        controls = ttk.LabelFrame(
            main,
            text="Keyboard Controls",
            padding=10
        )

        controls.pack(
            fill="x",
            pady=8
        )


        ttk.Label(
            controls,
            text="W / ↑ : Y+       S / ↓ : Y−"
        ).pack(
            anchor="w"
        )


        ttk.Label(
            controls,
            text="A / ← : X−       D / → : X+"
        ).pack(
            anchor="w"
        )


        ttk.Label(
            controls,
            text="Q : Z− Retract     E : Z+ Advance"
        ).pack(
            anchor="w"
        )


        ttk.Label(
            controls,
            text="SPACE : Emergency Stop / Latch"
        ).pack(
            anchor="w"
        )


        ttk.Label(
            controls,
            text="Click this window before using keyboard controls.",
            foreground="gray"
        ).pack(
            anchor="w",
            pady=(5, 0)
        )


        # ----------------------------------------------------
        # SPEED
        # ----------------------------------------------------

        speeds = ttk.LabelFrame(
            main,
            text="Speed (microsteps/second)",
            padding=10
        )

        speeds.pack(
            fill="x",
            pady=5
        )


        self.speed_labels = {}


        for axis in ("X", "Y", "Z"):

            row = ttk.Frame(
                speeds
            )

            row.pack(
                fill="x"
            )


            ttk.Label(
                row,
                text=axis,
                width=4
            ).pack(
                side="left"
            )


            max_speed = (
                XY_MAX_SPEED
                if axis != "Z"
                else Z_MAX_SPEED
)


            scale = ttk.Scale(
                row,
                from_=5,
                to=max_speed,
                orient="horizontal",

                command=lambda val, a=axis:
                    self.speed_changed(
                        a,
                        val
                    )
            )


            scale.set(
                self.speeds[axis]
            )


            scale.pack(
                side="left",
                fill="x",
                expand=True,
                padx=8
            )


            self.speed_vars[axis].set(
                self.speeds[axis]
            )


            label = ttk.Label(
                row,
                text=str(
                    self.speeds[axis]
                ),
                width=5
            )


            label.pack(
                side="right"
            )


            self.speed_labels[axis] = label


        # ----------------------------------------------------
        # POSITION
        # ----------------------------------------------------

        positions = ttk.LabelFrame(
            main,
            text="Software Position Counters",
            padding=10
        )

        positions.pack(
            fill="x",
            pady=5
        )


        for axis, var in zip(
            ("X", "Y", "Z"),
            self.position_vars
        ):

            row = ttk.Frame(
                positions
            )

            row.pack(
                fill="x"
            )


            ttk.Label(
                row,
                text=f"{axis}:",
                width=5
            ).pack(
                side="left"
            )


            ttk.Label(
                row,
                textvariable=var
            ).pack(
                side="left"
            )


        # ----------------------------------------------------
        # ACTION BUTTONS
        # ----------------------------------------------------

        actions = ttk.Frame(
            main
        )

        actions.pack(
            fill="x",
            pady=10
        )


        ttk.Button(
            actions,
            text="Reset / Enable",
            command=self.reset_controller
        ).pack(
            side="left",
            expand=True,
            fill="x",
            padx=(0, 4)
        )


        ttk.Button(
            actions,
            text="STOP ALL",
            command=self.emergency_stop
        ).pack(
            side="left",
            expand=True,
            fill="x",
            padx=(4, 0)
        )


        # ----------------------------------------------------
        # SAFETY MESSAGE
        # ----------------------------------------------------

        ttk.Label(
            main,
            text=(
                "Use with the needle removed or a safe dummy load. "
                "Software stop is not a physical emergency stop."
            ),
            foreground="firebrick",
            wraplength=560
        ).pack(
            anchor="w",
            pady=(4, 0)
        )


    # ========================================================
    # SERIAL PORTS
    # ========================================================

    def get_ports(self):

        return [
            p.device
            for p
            in serial.tools.list_ports.comports()
        ]


    def refresh_ports(self):

        ports = self.get_ports()

        self.port_combo["values"] = ports


        if (
            ports
            and self.port_var.get()
            not in ports
        ):

            self.port_var.set(
                ports[0]
            )


    # ========================================================
    # CONNECT
    # ========================================================

    def connect(self):

        if self.connected:

            self.disconnect()

            return


        port = self.port_var.get().strip()


        if not port:

            messagebox.showerror(
                "Port required",
                "Select a serial port."
            )

            return


        try:

            self.ser = serial.Serial(

                port,
                BAUD_RATE,

                timeout=0.01,

                write_timeout=0.1
            )


            # ------------------------------------------------
            # Arduino UNO automatically resets when serial
            # connection is opened.
            # ------------------------------------------------

            time.sleep(2)


            # Clear startup messages
            self.ser.reset_input_buffer()


            self.connected = True

            self.stop_latched = True

            self.reset_pending = False

            self.held_keys.clear()


            self.status_var.set(
                f"Connected to {port}; LOCKED"
            )


            self.connect_button.config(
                text="Disconnect"
            )


            # ------------------------------------------------
            # Automatically send RESET
            # ------------------------------------------------

            self.root.after(
                100,
                self.reset_controller
            )


        except (
            serial.SerialException,
            OSError
        ) as exc:

            self.ser = None

            messagebox.showerror(
                "Connection failed",
                str(exc)
            )


    # ========================================================
    # DISCONNECT
    # ========================================================

    def disconnect(self):

        self.held_keys.clear()


        if self.ser:

            try:

                self.send_line(
                    "STOP"
                )

                time.sleep(0.05)

                self.ser.close()

            except (
                serial.SerialException,
                OSError
            ):

                pass


        self.ser = None

        self.connected = False

        self.stop_latched = True

        self.reset_pending = False


        self.connect_button.config(
            text="Connect"
        )


        self.status_var.set(
            "Disconnected"
        )


    # ========================================================
    # SEND SERIAL COMMAND
    # ========================================================

    def send_line(self, text):

        if (
            not self.connected
            or not self.ser
        ):

            return False


        try:

            self.ser.write(
                (
                    text + "\n"
                ).encode("ascii")
            )

            return True


        except (
            serial.SerialException,
            OSError
        ):

            self.status_var.set(
                "Serial error"
            )

            self.disconnect()

            return False


    # ========================================================
    # RESET CONTROLLER
    # ========================================================

    def reset_controller(self):

        if not self.connected:

            return


        self.held_keys.clear()


        self.reset_pending = True

        self.stop_latched = True


        if self.send_line("RESET"):

            self.status_var.set(
                "RESET sent; waiting for Arduino..."
            )


    # ========================================================
    # EMERGENCY STOP
    # ========================================================

    def emergency_stop(self):

        self.held_keys.clear()

        self.stop_latched = True

        self.reset_pending = False


        if self.connected:

            self.send_line(
                "STOP"
            )


        self.status_var.set(
            "STOP LATCHED"
        )


    # ========================================================
    # SPEED
    # ========================================================

    def speed_changed(
        self,
        axis,
        value
    ):

        speed = int(
            float(value)
        )


        self.speeds[axis] = speed


        self.speed_vars[axis].set(
            speed
        )


        self.speed_labels[axis].config(
            text=str(speed)
        )


        # Send new speed to Arduino
        # only when connected and enabled.

        if (
            self.connected
            and not self.stop_latched
        ):

            self.send_line(
                f"S,"
                f"{self.speeds['X']},"
                f"{self.speeds['Y']},"
                f"{self.speeds['Z']}"
            )


    # ========================================================
    # CLEAR KEYS
    # ========================================================

    def clear_keys(
        self,
        event=None
    ):

        self.held_keys.clear()


    # ========================================================
    # KEY DOWN
    # ========================================================

    def key_down(
        self,
        event
    ):

        key = event.keysym.lower()


        # ----------------------------------------------------
        # SPACE = EMERGENCY STOP
        # ----------------------------------------------------

        if key == "space":

            self.emergency_stop()

            return "break"


        # ----------------------------------------------------
        # MOTION KEYS
        # ----------------------------------------------------

        if key in (
            "w",
            "a",
            "s",
            "d",
            "q",
            "e",
            "up",
            "down",
            "left",
            "right"
        ):

            if (
                self.connected
                and not self.stop_latched
            ):

                self.held_keys.add(
                    key
                )


            return "break"


    # ========================================================
    # KEY UP
    # ========================================================

    def key_up(
        self,
        event
    ):

        key = event.keysym.lower()

        self.held_keys.discard(
            key
        )


    # ========================================================
    # GET DIRECTIONS
    # ========================================================

    def get_directions(self):

        keys = self.held_keys


        # X
        x = (
            int(
                bool(
                    keys & {"d", "right"}
                )
            )
            -
            int(
                bool(
                    keys & {"a", "left"}
                )
            )
        )


        # Y
        y = (
            int(
                bool(
                    keys & {"w", "up"}
                )
            )
            -
            int(
                bool(
                    keys & {"s", "down"}
                )
            )
        )


        # Z
        z = (
            int(
                "e" in keys
            )
            -
            int(
                "q" in keys
            )
        )


        return x, y, z


    # ========================================================
    # SERIAL INPUT PROCESSING
    # ========================================================

    def process_serial_line(
        self,
        line
    ):

        if not line:

            return


        # ----------------------------------------------------
        # RESET SUCCESS
        # ----------------------------------------------------

        if line == "RESET_OK":

            self.reset_pending = False

            self.stop_latched = False


            self.status_var.set(
                "ENABLED; all axes stationary"
            )


            # Send current speed configuration
            self.send_line(
                f"S,"
                f"{self.speeds['X']},"
                f"{self.speeds['Y']},"
                f"{self.speeds['Z']}"
            )


            return


        # ----------------------------------------------------
        # STOP
        # ----------------------------------------------------

        if line == "STOPPED":

            self.reset_pending = False

            self.stop_latched = True


            self.status_var.set(
                "STOP LATCHED"
            )


            return


        # ----------------------------------------------------
        # POSITION
        # ----------------------------------------------------

        if line.startswith("POS,"):

            values = line.split(",")


            if len(values) == 4:

                try:

                    self.position = [

                        int(values[1]),

                        int(values[2]),

                        int(values[3]),
                    ]


                    for var, value in zip(
                        self.position_vars,
                        self.position
                    ):

                        var.set(
                            f"{value} microsteps"
                        )


                except ValueError:

                    pass


            return


        # ----------------------------------------------------
        # SPEED OK
        # ----------------------------------------------------

        if line == "SPEED_OK":

            return


        # ----------------------------------------------------
        # UNKNOWN / ERROR
        # ----------------------------------------------------

        if line.startswith("ERR,"):

            self.status_var.set(
                f"Arduino: {line}"
            )


    # ========================================================
    # MAIN UPDATE LOOP
    # ========================================================

    def update_loop(self):

        if self.connected:

            # ------------------------------------------------
            # READ SERIAL
            # ------------------------------------------------

            try:

                while (
                    self.ser
                    and self.ser.in_waiting
                ):

                    line = (
                        self.ser.readline()
                        .decode(
                            "ascii",
                            errors="ignore"
                        )
                        .strip()
                    )


                    self.process_serial_line(
                        line
                    )


            except (
                ValueError,
                serial.SerialException,
                OSError
            ):

                self.disconnect()

                self.root.after(
                    SEND_INTERVAL_MS,
                    self.update_loop
                )

                return


            # ------------------------------------------------
            # TIMING
            # ------------------------------------------------

            now = time.monotonic()


            # ------------------------------------------------
            # MOVEMENT COMMAND
            # ------------------------------------------------

            if (
                now - self.last_packet
                >=
                SEND_INTERVAL_MS / 1000
            ):

                x, y, z = (
                    self.get_directions()
                )


                # Never move while latched
                if self.stop_latched:

                    x = 0
                    y = 0
                    z = 0


                self.send_line(
                    f"M,{x},{y},{z}"
                )


                self.last_packet = now


            # ------------------------------------------------
            # STATUS REQUEST
            # ------------------------------------------------

            if (
                now - self.last_status_request
                >= 0.5
            ):

                self.send_line(
                    "STATUS"
                )


                self.last_status_request = now


        # ----------------------------------------------------
        # SCHEDULE NEXT LOOP
        # ----------------------------------------------------

        self.root.after(
            SEND_INTERVAL_MS,
            self.update_loop
        )


    # ========================================================
    # CLOSE APPLICATION
    # ========================================================

    def close_app(self):

        self.disconnect()

        self.root.destroy()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = ControllerApp(
        root
    )

    root.mainloop()