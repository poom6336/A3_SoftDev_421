import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
import pyvisa

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
            raise RuntimeError("No USB VISA resources found. Check USB connection and udev rules.")

        best = None 
        for resource in usb_resources:
            try:
                inst = rm.open_resource(resource)
                inst.timeout = 1000
                idn = inst.query("*IDN?").strip()
                if "RIGOL" in idn.upper():
                    if best is None:
                        best = (resource, inst, idn)
                    else:
                        inst.close()
                else:
                    inst.close()
            except Exception as exc:
                pass
                
        if best is None:
            raise RuntimeError("No Rigol instrument found.")
        
        resource_str, inst, idn = best
        return inst

    def connect(self):
        """Connect to the first USB instrument."""
        self.rm = pyvisa.ResourceManager(self.backend)
        resources = self.rm.list_resources()
        usb_resources = [r for r in resources if r.startswith("USB")]
        
        if not usb_resources:
            raise RuntimeError("No USB instrument found on scanning system.")
            
        for resource in usb_resources:
            self.scope = self.rm.open_resource(resource)
            self.scope.timeout = self.timeout
            return f"Connected to: {resource}"
    
    def disconnect(self):
        """Close the instrument and VISA resource manager."""
        if self.scope is not None:
            self.scope.close()
            self.scope = None
        if self.rm is not None:
            self.rm.close()
            self.rm = None

class Application:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Python GUI (Tkinter)")
        self.root.geometry("1280x720+50+50")

        self.root.status = "inactive"
        self.root.vdiv = [0.5, 1, 2, 4, 8, 16]

        self.osci = OsciCommand()
        self.create_widgets()

    def update_gui_states(self):
        """Helper to update visual states after connection actions."""
        #Text
        self.instru_var.set("Rigol Scope" if self.root.status == "active" else "offline")
        self.status_var.set(self.root.status)
        
        #Color
        color = "green" if self.root.status == "active" else "red"
        self.label_instru_content.config(fg=color)
        self.label_status_content.config(fg=color)
        
        btn_text = "disconnect" if self.root.status == "active" else "connect"
        self.button_connect.config(text=btn_text)
        
        combo_state = "readonly" if self.root.status == "active" else "disabled"
        self.button_capture.config(state=combo_state)

    def button_connect_action(self):
        if self.root.status == "inactive":
            self.log_info("Attempting connection to hardware...")
            try:
                success_msg = self.osci.connect()
                self.root.status = "active"
                self.log_info(success_msg if success_msg else "Connection established successfully.")
                self.update_gui_states()
            except Exception as e:
                self.log_error(f"Error:\n{str(e)}")
                self.root.status = "inactive"
                self.update_gui_states()
        elif self.root.status == "active":
            self.osci.disconnect()
            self.root.status = "inactive"
            self.log_info("Disconnected from instrument resources.")
            self.update_gui_states()

    def log_info(self, message):
        """Appends system info to the log box."""
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[INFO] {message}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def log_error(self, error_message):
        """Appends RuntimeErrors or connection blocks in red."""
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[ERROR] {error_message}\n", "error_style")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def create_widgets(self):
        self.root.columnconfigure((0, 1), weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)

        content_frame_L = tk.Frame(self.root, bg="white smoke", padx=10, pady=10)
        content_frame_T = tk.Frame(self.root, bg="gainsboro", padx=10, pady=10)


        self.instru_var = tk.StringVar(value="offline")
        self.status_var = tk.StringVar(value=self.root.status)

        # Frame T
        label_instru = tk.Label(content_frame_T, text="Instru:")
        self.label_instru_content = tk.Label(content_frame_T, textvariable=self.instru_var, fg="red")
        
        label_status = tk.Label(content_frame_T, text="Status:")
        self.label_status_content = tk.Label(content_frame_T, textvariable=self.status_var, fg="red")
        
        self.button_connect = tk.Button(
            content_frame_T, text="connect", command=self.button_connect_action
        )

        # Frame L
        label_CH1_VDiv = tk.Label(content_frame_L, text="V/Div:")
        self.button_capture = ttk.Combobox(
            content_frame_L, values=self.root.vdiv, state="disabled"
        )

        lbl_log = tk.Label(
            content_frame_L, text=" Logs:", font=("Arial", 12, "bold"), 
            bg="gray50", fg="white", anchor="w"
        )
        
        # log box
        self.log_box = scrolledtext.ScrolledText(
            content_frame_L, height=12, bg="#1e1e1e", fg="#d4d4d4", font=("Courier", 10)
        )
        self.log_box.tag_config("error_style", foreground="#ff6b6b")
        self.log_box.config(state="disabled")

        # Frame L config
        content_frame_L.grid(row=1, column=0, columnspan=1, sticky="nsew")
        content_frame_L.rowconfigure((0, 1, 2, 3), weight=0)
        content_frame_L.rowconfigure(4, weight=0)
        content_frame_L.rowconfigure(5, weight=1)
        content_frame_L.columnconfigure((0, 1, 2, 3), weight=1)

        label_CH1_VDiv.grid(row=0, column=0, sticky="nw", pady=5)
        self.button_capture.grid(row=0, column=1, sticky="nw", pady=5)
        
        lbl_log.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(20, 0))
        self.log_box.grid(row=5, column=0, columnspan=4, sticky="nsew", pady=(5, 0))

        # Frame T Config
        content_frame_T.grid(row=0, column=0, columnspan=3, rowspan=1, sticky="nsew")
        label_instru.grid(row=0, column=0, pady=20, padx=5)
        self.label_instru_content.grid(row=0, column=1, padx=5)
        label_status.grid(row=0, column=2, padx=5)
        self.label_status_content.grid(row=0, column=3, padx=5)
        self.button_connect.grid(row=0, column=4, padx=20)
        
        self.log_info("Application framework initialized. Ready for instrument hookup.")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = Application()
    app.run()
