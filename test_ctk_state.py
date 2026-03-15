import customtkinter as ctk

root = ctk.CTk()
root.geometry("400x300")
entries = []
for i in range(3):
    e = ctk.CTkEntry(root, placeholder_text=f"Entry {i}...")
    e.insert(0, f"text {i}")
    e.pack(pady=5)
    entries.append(e)

# Simulate the blur handler from the app
def blur(event=None):
    try:
        clicked = event.widget
        if not isinstance(clicked, ctk.CTkEntry):
            root.focus_set()
    except:
        pass
root.bind_all("<Button-1>", blur, add="+")

def lock():
    for e in entries:
        e.configure(state="disabled")
    print("LOCKED")

def unlock():
    for e in entries:
        e.configure(state="normal")
    print("UNLOCKED - try clicking entries")

ctk.CTkButton(root, text="Lock", command=lock).pack(pady=2)
ctk.CTkButton(root, text="Unlock", command=unlock).pack(pady=2)
root.mainloop()
