import tkinter as tk
from tkinter import ttk
import pyvisa
from datetime import datetime
from pathlib import Path

class OsciCommand:
    def __init__(self, backend="@py", timeout=2000):
        self.backend = backend
        self.timeout = timeout
        self.rm = None
        self.scope = None

    def find_rigol_instrument(self):
        """Scan USB VISA resources and return the first Rigol instrument found."""
        rm = pyvisa.ResourceManager("@py")
        resources = rm.list_resources()
        usb_resources = [r for r in resources if r.startswith("USB")]
        if not usb_resources:
            raise RuntimeError("No USB VISA resources found."
                                + "Check USB connection and udev rules.")
        print(f"Found {len(usb_resources)} USB resource(s):")

        best = None # (resource_string, inst, idn)
        for resource in usb_resources:
            print(f" Probing {resource} ...", end=" ", flush=True)
            try:
                inst = rm.open_resource(resource)
                inst.timeout = 1000
                idn = inst.query("*IDN?").strip()
                print(f"\nIDN: {idn}")
                if "RIGOL" in idn.upper():
                        if best is None:
                            best = (resource, inst, idn)
                        else:
                            inst.close()
                else:
                    inst.close()
            except Exception as exc:
                print(f"error ({exc})")
        if best is None:
            raise RuntimeError("No Rigol instrument found.")
        
        resource_str, inst, idn = best
        print(f"\nSelected: {resource_str}")
        print(f"IDN: {idn}")
        return inst

    def capture_screenshot(self):
        """Send screenshot command and return raw PNG bytes.
        Uses the IEEE-488.2 definite-length binary block format
        returned by the RIGOL :DISP:DATA? command.
        """
        scope = self.find_rigol_instrument(self)
        scope.timeout = 5000
        scope.write(":DISP:DATA? ON,0,PNG")

        # Read IEEE-488.2 binary block header: '#' + N (single digit)
        header = scope.read_bytes(2)
        if header[0:1] != b"#":
            raise RuntimeError(f"Unexpected header byte: {header!r}."
                                + "Expected '#'.")

        num_digits = int(header[1:2])
        if num_digits == 0:
            raise RuntimeError("Received indefinite-length block - not supported.")
        length_bytes = scope.read_bytes(num_digits)
        payload_length = int(length_bytes.decode())
        print(f"Receiving {payload_length} bytes of PNG data ...")

        png_data = scope.read_bytes(payload_length)
        if not png_data.startswith(b"\x89PNG"):
            raise RuntimeError(f"No PNG magic bytes: {png_data[:8]!r}")
        return png_data
    
    def ch1_VDiv(self):
        scope = self.find_rigol_instrument()
        try:
            return float(scope.query(':CHAN1:SCAL?'))
        except:
            return RuntimeError(f"No USB connected")
    
    def connect(self):
        """Connect to the first USB instrument."""
        self.rm = pyvisa.ResourceManager(self.backend)

        for resource in self.rm.list_resources():
            if resource.startswith("USB"):
                self.scope = self.rm.open_resource(resource)
                self.scope.timeout = self.timeout
                print(f"Connected to: {resource}")
                return
        #raise RuntimeError("No USB instrument found.")
    
    def disconnect(self):
        """Close the instrument and VISA resource manager."""
        if self.scope is not None:
            self.scope.close()
            self.scope = None

        if self.rm is not None:
            self.rm.close()
            self.rm = None

    def write(self, command):
        """Send a SCPI command."""
        self.scope.write(command)

    def query(self, command, timeout=None):
        """Send a SCPI query and return the response."""
        if timeout is not None:
            self.scope.timeout = timeout
        return self.scope.query(command).strip()
    
    def get_idn(self):
        """Return the instrument identification string."""
        return self.query("*IDN?")
        
    def run(self):
        """Start waveform acquisition."""
        self.write(":RUN")
        
    def stop(self):
        """Stop waveform acquisition."""
        self.write(":STOP")

    def __enter__(self): # to be used with the `with` statement
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    """def main():
        rm = pyvisa.ResourceManager("@py")
        scope = None
        try:
            scope = find_rigol_instrument(rm)
            png_data = capture_screenshot(scope)
            output_path = save_screenshot(png_data,
                                        output_dir=Path(__file__).parent)
            print(f"Saved {len(png_data)} bytes to {output_path}")
        finally:
            if scope:
                scope.close()
            rm.close()
        """

class Application:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Python GUI (Tkinter)")
        self.root.geometry("1280x720+50+50")

        self.root.status = "inactive"
        self.root.vdiv = [0.5, 1, 2, 4, 8, 16]

        self.osci = OsciCommand()
        self.create_widgets()

    def state_combo(self):
        if self.root.status == "inactive":
            return "disabled"
        elif self.root.status == "active":
            return "readonly"
        else:exit(code="status error")
    
    def button_connect_state(self):
        if self.root.status == "inactive":
            return "connect"
        elif self.root.status == "active":
            return "disconnect"
        else:exit(code="status error")

    def button_connect_action(self):
        if self.root.status == "inactive":
            self.osci.connect()
            return
        elif self.root.status == "active":
            self.osci.disconnect()
            return
        else:exit(code="status error")

    def instru_action(self):
        if self.root.status == "inactive":
            return "offline"
        elif self.root.status == "active":
            return self.osci.find_rigol_instrument()
        else:exit(code="status error")
    
    def green_red(self):
        if self.root.status == "inactive":
            return "red"
        elif self.root.status == "active":
            return "green"
        else:exit(code="status error")

    def create_widgets(self):

        self.root.columnconfigure((0,1), weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)

        content_frame_L = tk.Frame(
            self.root, bg="white smoke", padx=10, pady=10
        )

        content_frame_T = tk.Frame(
            self.root, bg="gainsboro", padx=10, pady=10
        )

        #Frame Top
        label_instru = tk.Label(
            content_frame_T, text = f"Instru:"
        )
        label_instru_content = tk.Label(
            content_frame_T, text = f"{self.instru_action()}", fg=self.green_red()
        )
        label_status = tk.Label(
            content_frame_T, text = f"Status:"
        )
        label_status_content = tk.Label(
            content_frame_T, text = {self.root.status}, fg=self.green_red()
        )
        button_connect = tk.Button(
            content_frame_T, text = f"{self.button_connect_state()}", command = self.button_connect_action()
        )

        #Frame Left
        #CH1
        label_CH1_VDiv = tk.Label(
            content_frame_L, text = f"V/Div:"
        )
        button_capture = ttk.Combobox(
            content_frame_L, values = self.root.vdiv, state = self.state_combo()
        )
        
        #Log
        lbl_log = tk.Label(
            content_frame_L, text="Logs:", font=("Arial", 15, "bold"), bg="gray50", fg="white", anchor="w"
            )

        #frameL config
        content_frame_L.grid(row=1, column=0, columnspan=1, sticky="nsew")
        content_frame_L.rowconfigure((0,1,2,3), weight=0)
        content_frame_L.rowconfigure((4,5), weight=1)
        content_frame_L.columnconfigure((0,1,2,3),weight=1)

        label_CH1_VDiv.grid(row=0,column=0, sticky="nw")
        button_capture.grid(row=0, column=1)
        lbl_log.grid(row=5,column=0, columnspan=4, sticky="ew")



        #frameT config
        content_frame_T.grid(row=0, column=0, columnspan=3, rowspan=1, sticky="nsew")
        label_instru.grid(row=0, column=0, pady=20)
        label_instru_content.grid(row=0,column=1)
        label_status.grid(row=0, column=2, )
        label_status_content.grid(row=0, column=3)
        button_connect.grid(row=0, column=4, padx=20)
        

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = Application()
    app.run()
