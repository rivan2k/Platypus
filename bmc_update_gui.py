import tkinter as tk
from tkinter import filedialog, messagebox
import BMC_update_script as bmc



def browse_file():
    filepath = filedialog.askopenfilename()
    if filepath:
        entry_file.config(state='normal')
        entry_file.delete(0, tk.END)
        entry_file.insert(0, filepath)

def fw_update():
    bmc_ip = entry_ip.get()
    bmc_user = entry_user.get()
    bmc_pass = entry_pass.get()
    fw_file = entry_file.get()

    if not all([bmc_ip, bmc_pass, bmc_user, fw_file]):
        label_output.config(text="All fields are required.", fg="red")
        return
    
    
    
    token = bmc.get_token(bmc_ip, bmc_user, bmc_pass)

    if not token:
        label_output.config(text="Failed to obtain authentication token", fg="red")
        return
    
    response_text = bmc.fw_update(fw_file, bmc_ip, token)

    label_output.config(text=response_text, fg="green")



# GUI Setup
win = tk.Tk()
win.title("BMC Firmware Update")

label_ip = tk.Label(win, text="BMC IP:")
label_ip.grid(row=0, column=0, padx=5, pady=5)
entry_ip = tk.Entry(win)
entry_ip.grid(row=0, column=1, padx=5, pady=5)

label_user = tk.Label(win, text="Username:")
label_user.grid(row=1, column=0, padx=5, pady=5)
entry_user = tk.Entry(win)
entry_user.grid(row=1, column=1, padx=5, pady=5)

label_pass = tk.Label(win, text="Password:")
label_pass.grid(row=2, column=0, padx=5, pady=5)
entry_pass = tk.Entry(win, show="*")
entry_pass.grid(row=2, column=1, padx=5, pady=5)

label_file = tk.Label(win, text="Firmware File:")
label_file.grid(row=3, column=0, padx=5, pady=5)
entry_file = tk.Entry(win, state="readonly")
entry_file.grid(row=3, column=1, padx=5, pady=5)
button_browse = tk.Button(win, text="Browse", command=browse_file)
button_browse.grid(row=3, column=2, padx=5, pady=5)

button_update = tk.Button(win, text="Update Firmware", command=fw_update)
button_update.grid(row=4, columnspan=2, padx=5, pady=5)

label_output = tk.Label(win, text="", wraplength=400, justify="left")
label_output.grid(row=5, column=0, columnspan=3, padx=10, pady=10)

win.mainloop()
