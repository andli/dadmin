import os, json, re, sys
import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.widgets import Treeview
from mcrcon import MCRcon
from fuzzywuzzy import fuzz, process


# Load config
def load_config():
    config = {}
    with open("server_config.txt") as f:
        for line in f:
            key, val = line.strip().split("=")
            config[key] = val
    return config


def load_data():
    data = {}
    for typename in ["item", "effect", "enchantment"]:  # Add more types here as needed
        filename = f"{typename}s.json"
        path = os.path.join("data", filename)
        try:
            with open(path, "r") as f:
                raw = json.load(f)
                data[typename] = [
                    (entry["displayName"], f"minecraft:{entry['name'].lower()}")
                    for entry in raw
                    if "name" in entry and "displayName" in entry
                ]
        except FileNotFoundError:
            print(f"Warning: {filename} not found.")
            data[typename] = []
    return data


TYPED_DATA = load_data()


class MinecraftAdminApp:
    def __init__(self, root, mcr=None):
        self.player_var = tb.StringVar()
        self.root = root
        self.root.title("Minecraft server DADmin")
        self.config = load_config()
        self.mcr = mcr or self.connect_rcon()
        self.setup_gui()
        self.current_players = []
        self.schedule_player_refresh()

    def connect_rcon(self):
        try:
            mcr = MCRcon(
                self.config["host"], self.config["password"], int(self.config["port"])
            )
            mcr.connect()
            return mcr
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
            self.root.quit()
            return None

    def schedule_player_refresh(self):
        self.update_players()
        self.root.after(5000, self.schedule_player_refresh)  # every 5 seconds

    def setup_gui(self):
        frame = tb.Frame(self.root, padding=10)
        frame.grid()

        tb.Label(frame, text="Item/Effect:").grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )

        self.search_entry = tb.Entry(frame)
        self.search_entry.grid(row=0, column=1, pady=(0, 5))
        self.search_entry.bind("<KeyRelease>", self.update_fuzzy_list)

        self.type_var = tb.StringVar(value="item")
        tb.OptionMenu(frame, self.type_var, "item", "item", "effect").grid(
            row=0, column=2, pady=(0, 5)
        )

        self.result_tree = Treeview(
            frame,
            columns=("label",),
            show="",  # ⬅️ hide column headers
            height=5,
            bootstyle="dark",
        )
        self.result_tree.configure(selectmode="browse", takefocus=False)
        self.result_tree.column("label", anchor="w", stretch=True, width=250)
        self.result_tree.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0, 10))

        tb.Label(frame, text="Player:").grid(row=2, column=0, sticky="w", pady=(0, 5))
        self.player_box = tb.Combobox(frame, textvariable=self.player_var, values=[])
        self.player_box.grid(row=2, column=1, columnspan=2, sticky="we", pady=(0, 5))

        tb.Label(frame, text="Amount/Duration:").grid(
            row=3, column=0, sticky="w", pady=(0, 5)
        )
        self.amount_entry = tb.Entry(frame)
        self.amount_entry.grid(row=3, column=1, columnspan=2, pady=(0, 5))

        self.send_button = tb.Button(
            frame, text="Send Command", command=self.send_command
        )
        self.send_button.grid(row=4, column=0, columnspan=3, pady=(10, 0))

        self.status = tb.Label(
            self.root, text="", anchor="w", padding=(10, 2), bootstyle="dark"
        )
        self.status.grid(row=1, column=0, sticky="we", pady=(5, 5))

    def update_players(self):
        try:
            resp = self.mcr.command("list")

            match = re.search(r"online: (.*)", resp)
            if match:
                player_str = match.group(1).strip()
                players = [p.strip() for p in player_str.split(",") if p.strip()]
            else:
                players = []

            if players == self.current_players:
                return

            self.current_players = players

            previous = self.player_var.get()
            self.player_box["values"] = players

            # Restore previous selection if still present
            if previous in players:
                self.player_var.set(previous)
            elif players:
                self.player_var.set(players[0])
            else:
                self.player_var.set("")

        except Exception as e:
            print("Error updating players:", e)

    def update_fuzzy_list(self, event=None):
        query = self.search_entry.get().strip()
        self.result_tree.delete(*self.result_tree.get_children())

        current_type = self.type_var.get()
        entries = TYPED_DATA.get(current_type, [])
        labels = [label for label, _ in entries]
        entry_map = dict(entries)

        results = process.extractBests(
            query, labels, scorer=fuzz.partial_ratio, limit=5
        )

        for label, _ in results:
            id_value = entry_map[label]
            self.result_tree.insert("", "end", values=(label,))

    def send_command(self):
        selected = self.result_tree.selection()
        if not selected:
            selection = ""
        else:
            selection = self.result_tree.item(selected[0], "values")[0]
        player = self.player_var.get()
        amount = self.amount_entry.get()

        if not selection or not player or not amount.isdigit():
            self.set_status("⚠️ Fill all fields before sending", "warning")

            return

        entry_map = dict(TYPED_DATA.get(self.type_var.get(), []))
        resolved = entry_map.get(selection, selection)

        try:
            if self.type_var.get() == "item":
                cmd = f"/give {player} {resolved} {amount}"
            else:
                cmd = f"/effect give {player} {resolved} {amount} 0 true"

            print("Sending command:", cmd)
            response = self.mcr.command(cmd)
            self.set_status("✅ Command sent", "success")
        except Exception as e:
            self.set_status(f"❌ {str(e)}", "danger", duration=5000)

    def set_status(self, text, style="secondary", duration=3000):
        self.status.config(text=text, bootstyle=style)
        self.root.after(
            duration, lambda: self.status.config(text="", bootstyle="secondary")
        )


if __name__ == "__main__":
    try:
        config = load_config()
        mcr = MCRcon(config["host"], config["password"], int(config["port"]))
        mcr.connect()
        print("✅ RCON connection established.")
    except Exception as e:
        print("❌ Could not connect to Minecraft server via RCON:")
        print(e)
        exit(1)

    # Launch GUI
    root = tb.Window(themename="darkly")  # or "superhero", "cyborg", etc.

    if sys.platform.startswith("win"):
        root.iconbitmap(os.path.abspath("icon.ico"))
    else:
        root.iconphoto(False, tk.PhotoImage(file="icon.png"))

    app = MinecraftAdminApp(root)
    root.mainloop()
