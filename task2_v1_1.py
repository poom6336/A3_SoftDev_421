import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
import pyvisa
import traceback
import struct
import zlib
import base64
from pathlib import Path

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
        
        # Filter for typical instrument connections (USB, GPIB, TCPIP)
        valid_resources = [r for r in resources if r.startswith(("USB", "GPIB", "TCPIP"))]
        
        if not valid_resources:
            raise RuntimeError("No connected instruments found. Check physical connection/drivers.")
            
        # Attempt connection to the first discovered instrument
        target_resource = valid_resources[0]
        self.scope = self.rm.open_resource(target_resource)
        self.scope.timeout = self.timeout
        
        # Query *IDN? to verify identity
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
            # Automatic separation between write operations and read queries
            if "?" in command:
                response = self.scope.query(command)
                return f"[QUERY] {command}\n[RESPONSE] {response.strip()}"
            else:
                self.scope.write(command)
                return f"[CMD] {command} (Executed successfully)"
        except Exception as e:
            raise RuntimeError(f"SCPI Error executing '{command}': {str(e)}")

    def fix_png_crc(self, png_data):
        """Fixes the MSO1104Z's bad internal checksums that crash Tkinter."""
        signature = b"\x89PNG\r\n\x1a\n"
        if not png_data.startswith(signature):
            return png_data

        fixed_data = bytearray(signature)
        offset = 8
        
        while offset < len(png_data):
            if offset + 4 > len(png_data):
                break
            length = struct.unpack(">I", png_data[offset:offset+4])[0]
            
            if offset + 8 + length > len(png_data):
                break
            chunk_type = png_data[offset+4:offset+8]
            chunk_data = png_data[offset+8:offset+8+length]
            
            crc_input = chunk_type + chunk_data
            correct_crc = zlib.crc32(crc_input) & 0xFFFFFFFF
            
            fixed_data.extend(png_data[offset:offset+8+length])
            fixed_data.extend(struct.pack(">I", correct_crc))
            
            offset += 12 + length
            if chunk_type == b"IEND":
                break
                
        return bytes(fixed_data)

    def capture_screenshot(self):
        """Send screenshot command, safely read data, crop, and fix CRCs."""
        if not self.scope:
            raise RuntimeError("Instrument is offline.")
            
        self.scope.timeout = 10000
        self.scope.write(":DISP:DATA? ON,0,PNG")

        header = self.scope.read_bytes(2)
        if header[0:1] != b"#":
            raise RuntimeError(f"Unexpected header byte: {header!r}. Expected '#'.")

        num_digits = int(header[1:2])
        if num_digits == 0:
            raise RuntimeError("Received indefinite-length block - not supported.")
            
        length_bytes = self.scope.read_bytes(num_digits)
        payload_length = int(length_bytes.decode())

        raw_data = self.scope.read_bytes(payload_length)

        try:
            self.scope.timeout = 200
            self.scope.read_raw()
        except Exception:
            pass 
            
        self.scope.timeout = 10000

        start_idx = raw_data.find(b"\x89PNG")
        if start_idx == -1:
            raise RuntimeError("No PNG magic bytes found in instrument response.")
            
        iend_idx = raw_data.rfind(b"IEND")
        if iend_idx == -1:
            raise RuntimeError("Incomplete PNG received (Missing IEND chunk).")
            
        end_idx = iend_idx + 8 
        clean_png = raw_data[start_idx:end_idx]
        perfect_png = self.fix_png_crc(clean_png)
        
        return perfect_png


class Application:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Oscilloscope SCPI Controller")
        self.root.geometry("1450x750")

        self.root.status = "inactive"
        self.osci = OsciCommand()
        self.live_img = None
        
        self.create_widgets()
        self.update_live_capture()

    def update_gui_states(self):
        """Updates UI visual states depending on connection state."""
        self.instru_var.set("Oscilloscope" if self.root.status == "active" else "offline")
        self.status_var.set(self.root.status.upper())
        
        color = "#2ed573" if self.root.status == "active" else "#ff4757"
        self.label_status_content.config(fg=color)
        
        btn_text = "Disconnect" if self.root.status == "active" else "Connect"
        self.button_connect.config(text=btn_text)
        
        scpi_state = "normal" if self.root.status == "active" else "disabled"
        self.entry_scpi.config(state=scpi_state)
        self.button_send.config(state=scpi_state)
        
        if self.root.status != "active":
            self.image_label.config(image="", text="Live Display Offline (Disconnected)")

    def update_live_capture(self):
        """Automatically captures, saves, and updates the display label."""
        if self.root.status == "active":
            try:
                raw_png = self.osci.capture_screenshot()
                b64_data = base64.b64encode(raw_png)
                
                self.live_img = tk.PhotoImage(data=b64_data)
                self.image_label.config(image=self.live_img, text="")
            except Exception as e:
                self.log_error(f"Live Display Error: {str(e)}")
        
        self.root.after(1000, self.update_live_capture)

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
        # row/col config
        self.root.columnconfigure(0, weight=1) # L
        self.root.columnconfigure(1, weight=2) # R
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)

        self.instru_var = tk.StringVar(value="offline")
        self.status_var = tk.StringVar(value=self.root.status.upper())

        # Frame T
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

        # --- Left Panel: SCPI Control & Logs (Frame L) ---
        content_frame_L = tk.Frame(self.root, bg="#f1f2f6", padx=15, pady=15)
        content_frame_L.grid(row=1, column=0, sticky="nsew")
        content_frame_L.columnconfigure(0, weight=1)
        content_frame_L.columnconfigure(1, weight=0)
        content_frame_L.rowconfigure(4, weight=1) # Makes the log box expand vertically

        lbl_scpi = tk.Label(content_frame_L, text="Enter SCPI Command / Query:", bg="#f1f2f6", font=("Arial", 11, "bold"))
        lbl_scpi.grid(row=0, column=0, columnspan=2, sticky="nw", pady=(0, 5))

        self.entry_scpi = tk.Entry(content_frame_L, font=("Courier", 12), state="disabled")
        self.entry_scpi.grid(row=1, column=0, sticky="ew", padx=(0, 10), ipady=4)
        self.entry_scpi.bind("<Return>", lambda event: self.send_scpi_action())

        self.button_send = tk.Button(content_frame_L, text="Send", command=self.send_scpi_action, bg="#1e90ff", fg="white", state="disabled", width=10)
        self.button_send.grid(row=1, column=1, sticky="e")

        lbl_tip = tk.Label(content_frame_L, text="Tip: Commands containing '?' are treated automatically as queries.", fg="#747d8c", bg="#f1f2f6", font=("Arial", 9, "italic"))
        lbl_tip.grid(row=2, column=0, columnspan=2, sticky="nw", pady=(5, 20))

        # Logs Section (Bottom Left)
        lbl_log = tk.Label(content_frame_L, text="Instrument Logs & Responses:", font=("Arial", 11, "bold"), bg="#f1f2f6", anchor="w")
        lbl_log.grid(row=3, column=0, sticky="sw", pady=(0, 5))

        button_clear = tk.Button(content_frame_L, text="Clear Logs", command=self.clear_log_action, bg="#a4b0be", font=("Arial", 9))
        button_clear.grid(row=3, column=1, sticky="se", pady=(0, 5))
        
        self.log_box = scrolledtext.ScrolledText(content_frame_L, bg="#1e1e1e", fg="#d4d4d4", font=("Courier", 10), wrap=tk.WORD)
        self.log_box.tag_config("error_style", foreground="#ff6b6b")
        self.log_box.config(state="disabled")
        self.log_box.grid(row=4, column=0, columnspan=2, sticky="nsew")

        # --- Right Panel: Live Capture Display (Frame R) ---
        content_frame_R = tk.Frame(self.root, bg="#e4e7eb", padx=15, pady=15)
        content_frame_R.grid(row=1, column=1, sticky="nsew")
        content_frame_R.columnconfigure(0, weight=1)
        content_frame_R.rowconfigure(1, weight=1) # Makes the image fill space

        lbl_live = tk.Label(content_frame_R, text="Live Screen Capture:", font=("Arial", 11, "bold"), bg="#e4e7eb", anchor="w")
        lbl_live.grid(row=0, column=0, sticky="nw", pady=(0, 5))

        # Display Box for Saved PNG Images
        self.image_label = tk.Label(content_frame_R, text="Live Display Offline (Disconnected)", bg="#1e1e1e", fg="#d4d4d4", font=("Arial", 11))
        self.image_label.grid(row=1, column=0, sticky="nsew")

        self.log_info("Application initialized. Press 'Connect' to discover hardware instruments.")


    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = Application()
    app.run()
