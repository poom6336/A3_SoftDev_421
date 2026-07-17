import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext  
import pyvisa
import traceback                 

class OsciCommand:
    def __init__(self, backend="@py", timeout=3000):
        self.backend = backend
        self.timeout = timeout
        self.rm = None
        self.scope = None

    def connect(self):
        """Automatically search for connected VISA instruments and connect to the first one."""
        self.rm = pyvisa.ResourceManager(self.backend)
        resources = self.rm.list_resources()
        
        valid_resources = [r for r in resources if r.startswith(("USB", "GPIB", "TCPIP"))]
        
        if not valid_resources:
            raise RuntimeError("No connected instruments found. Check physical connection/drivers.")
            
        # Connect to the first instrument
        target_resource = valid_resources[0]
        self.scope = self.rm.open_resource(target_resource)
        self.scope.timeout = self.timeout
        
        try:
            idn = self.scope.query("*IDN?").strip()
            return f"Connected to: {target_resource}\nDevice IDN: {idn}"
        except Exception:
            return f"Connected to: {target_resource} (Failed to fetch *IDN?)"
    
    def disconnect(self):
        """Close the instrument and VISA resource manager cleanly."""
        if self.scope is not None:
            try:
                self.scope.close()
            except:
                pass
            self.scope = None
        if self.rm is not None:
            try:
                self.rm.close()
            except:
                pass
            self.rm = None

    def execute_scpi(self, command: str):
        """Determine if command or query, execute, handle errors, and return result."""
        if not self.scope:
            raise RuntimeError("Instrument is offline. Connect first.")
        
        command = command.strip()
        if not command:
            return "Empty command ignored."

        try:
            # Seperate between operations and queries
            if "?" in command:
                response = self.scope.query(command)
                return f"[QUERY] {command}\n[RESPONSE] {response.strip()}"
            else:
                self.scope.write(command)
                return f"[CMD] {command} (Executed successfully)"
        except Exception as e:
            raise RuntimeError(f"SCPI Error executing '{command}': {str(e)}")
        
    

class Application:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Oscilloscope SCPI Controller")
        self.root.geometry("1280x720+50+50")
        self.root.geometry("1100x600")

        self.root.status = "inactive"
        self.osci = OsciCommand()
        self.create_widgets()

    def update_gui_states(self):
        """Updates UI visual states depending on connection state."""
        self.instru_var.set("Oscilloscope" if self.root.status == "active" else "offline")
        self.status_var.set(self.root.status.upper())
        
        color = "#2ed573" if self.root.status == "active" else "#ff4757"
        self.label_status_content.config(fg=color)
        
        btn_text = "Disconnect" if self.root.status == "active" else "Connect"
        self.button_connect.config(text=btn_text)
        
        # Enable SCPI only when connected
        scpi_state = "normal" if self.root.status == "active" else "disabled"
        self.entry_scpi.config(state=scpi_state)
        self.button_send.config(state=scpi_state)

    def button_connect_action(self):
        if self.root.status == "inactive":
            self.log_info("Scanning for connected instruments...")
            try:
                success_msg = self.osci.connect()
                self.root.status = "active"
                self.log_info(success_msg)
                self.update_gui_states()
            except Exception as e:
                self.log_error(f"Connection Failure:\n{str(e)}")
                self.root.status = "inactive"
                self.update_gui_states()
        elif self.root.status == "active":
            self.osci.disconnect()
            self.root.status = "inactive"
            self.log_info("Disconnected from instrument resources.")
            self.update_gui_states()

    def send_scpi_action(self):
        cmd = self.entry_scpi.get()
        if not cmd.strip():
            return
        try:
            res = self.osci.execute_scpi(cmd)
            self.log_info(res)
            self.entry_scpi.delete(0, tk.END)
        except Exception as e:
            self.log_error(str(e))

    def clear_log_action(self):
        """Clears the console response window."""
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state="disabled")

    def log_info(self, message):
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[INFO] {message}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def log_error(self, error_message):
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[ERROR] {error_message}\n", "error_style")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def create_widgets(self):
        # Row/Column weights
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)

        self.instru_var = tk.StringVar(value="offline")
        self.status_var = tk.StringVar(value=self.root.status.upper())

        # Frame Top
        content_frame_T = tk.Frame(self.root, bg="#2f3542", padx=15, pady=15)
        content_frame_T.grid(row=0, column=0, columnspan=2, sticky="nsew")
        
        label_instru = tk.Label(content_frame_T, text="Instrument:", fg="white", bg="#2f3542", font=("Arial", 11, "bold"))
        self.label_instru_content = tk.Label(content_frame_T, textvariable=self.instru_var, fg="#a4b0be", bg="#2f3542", font=("Arial", 11))
        
        label_status = tk.Label(content_frame_T, text="Status:", fg="white", bg="#2f3542", font=("Arial", 11, "bold"))
        self.label_status_content = tk.Label(content_frame_T, textvariable=self.status_var, fg="#ff4757", bg="#2f3542", font=("Arial", 11, "bold"))
        
        self.button_connect = tk.Button(content_frame_T, text="Connect", command=self.button_connect_action, bg="#747d8c", fg="white", padx=10)

        label_instru.pack(side="left", padx=5)
        self.label_instru_content.pack(side="left", padx=15)
        label_status.pack(side="left", padx=5)
        self.label_status_content.pack(side="left", padx=15)
        self.button_connect.pack(side="right", padx=10)

        # Frame Left
        content_frame_L = tk.Frame(self.root, bg="#f1f2f6", padx=15, pady=15)
        content_frame_L.grid(row=1, column=0, sticky="nsew")
        content_frame_L.columnconfigure(0, weight=1)
        content_frame_L.columnconfigure(1, weight=0)

        lbl_scpi = tk.Label(content_frame_L, text="Enter SCPI Command / Query:", bg="#f1f2f6", font=("Arial", 11, "bold"))
        lbl_scpi.grid(row=0, column=0, columnspan=2, sticky="nw", pady=(0, 5))

        self.entry_scpi = tk.Entry(content_frame_L, font=("Courier", 12), state="disabled")
        self.entry_scpi.grid(row=1, column=0, sticky="ew", padx=(0, 10), ipady=4)
        
        self.entry_scpi.bind("<Return>", lambda event: self.send_scpi_action())

        self.button_send = tk.Button(content_frame_L, text="Send", command=self.send_scpi_action, bg="#1e90ff", fg="white", state="disabled", width=10)
        self.button_send.grid(row=1, column=1, sticky="e")

        lbl_tip = tk.Label(content_frame_L, text="Tip: Commands containing '?' are treated automatically as queries.", fg="#747d8c", bg="#f1f2f6", font=("Arial", 9, "italic"))
        lbl_tip.grid(row=2, column=0, columnspan=2, sticky="nw", pady=5)

        # Frame Right
        content_frame_R = tk.Frame(self.root, bg="#e4e7eb", padx=15, pady=15)
        content_frame_R.grid(row=1, column=1, sticky="nsew")
        content_frame_R.columnconfigure(0, weight=1)
        content_frame_R.rowconfigure(1, weight=1)

        lbl_log = tk.Label(content_frame_R, text="Instrument Logs & Responses:", font=("Arial", 11, "bold"), bg="#e4e7eb", anchor="w")
        lbl_log.grid(row=0, column=0, sticky="nw", pady=(0, 5))

        button_clear = tk.Button(content_frame_R, text="Clear Window", command=self.clear_log_action, bg="#a4b0be", font=("Arial", 9))
        button_clear.grid(row=0, column=1, sticky="ne", pady=(0, 5))
        
        self.log_box = scrolledtext.ScrolledText(content_frame_R, bg="#1e1e1e", fg="#d4d4d4", font=("Courier", 10), wrap=tk.WORD)
        self.log_box.tag_config("error_style", foreground="#ff6b6b")
        self.log_box.config(state="disabled")
        self.log_box.grid(row=1, column=0, columnspan=2, sticky="nsew")

        self.log_info("Application initialized. Press 'Connect' to discover hardware instruments.")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = Application()
    app.run()
