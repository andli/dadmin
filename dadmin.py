import os, json, re, sys, socket
import tkinter as tk
from tkinter import messagebox
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


def test_connection(host, port, timeout=5):
    """Test if a TCP connection can be established to the given host and port"""
    try:
        # Resolve hostname to IP
        ip = socket.gethostbyname(host)
        print(f"🔍 Resolved {host} to {ip}")

        # Test TCP connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()

        if result == 0:
            print(f"✅ Port {port} is open and accepting connections on {host}")
            return True, "Connection successful"
        else:
            print(f"❌ Port {port} is closed or not responding on {host}")
            return False, f"Port {port} is not accessible"

    except socket.gaierror as e:
        error_msg = f"DNS resolution failed for {host}: {str(e)}"
        print(f"❌ {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Connection test failed: {str(e)}"
        print(f"❌ {error_msg}")
        return False, error_msg


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
        host = self.config["host"]
        port = int(self.config["port"])

        print(f"🔌 Attempting RCON connection to {host}:{port}")

        # First, test if the port is accessible
        can_connect, test_msg = test_connection(host, port)

        try:
            if not can_connect:
                # Port is not accessible, provide detailed error
                detailed_error = (
                    f"Cannot connect to {host}:{port}\n\n"
                    f"Diagnostic: {test_msg}\n\n"
                    f"Common causes:\n"
                    f"• Minecraft server is not running\n"
                    f"• RCON is not enabled (enable-rcon=true)\n"
                    f"• Wrong RCON password  (rcon.password=1111)\n"
                    f"• Wrong RCON port (check rcon.port in server.properties)\n"
                    f"• Firewall blocking the port\n"
                    f"• Server binding to different interface"
                )
                print(f"❌ Connection failed: {test_msg}")
                messagebox.showerror("RCON Connection Failed", detailed_error)
                return None

            # Port is accessible, try RCON connection
            mcr = MCRcon(host, self.config["password"], port)
            mcr.connect()
            print("✅ RCON connection established.")
            return mcr

        except Exception as e:
            print("❌ RCON authentication/protocol error:")
            print(e)

            # Provide specific error guidance
            error_str = str(e).lower()
            if "authentication failed" in error_str or "invalid password" in error_str:
                detailed_error = (
                    f"RCON Authentication Failed\n\n"
                    f"Error: {str(e)}\n\n"
                    f"Make sure that the following settings are set in server.properties:\n"
                    f"enable-rcon=true\n"
                    f"rcon.password=1111\n"
                    f"rcon.port=25575\n\n"
                    f"Check:\n"
                    f"• RCON password in server.properties matches server_config.txt\n"
                    f"• Password in server_config.txt: '{self.config['password']}'\n"
                    f"• Server may need restart after changing RCON settings"
                )
            elif "connection refused" in error_str:
                detailed_error = (
                    f"Connection Refused by Server\n\n"
                    f"Error: {str(e)}\n\n"
                    f"Make sure that the following settings are set in server.properties:\n"
                    f"enable-rcon=true\n"
                    f"rcon.password=1111\n"
                    f"rcon.port=25575\n\n"
                    f"Check:\n"
                    f"• RCON is enabled (enable-rcon=true in server.properties)\n"
                    f"• RCON port matches (rcon.port={port} in server.properties)\n"
                    f"• Server has been restarted after enabling RCON"
                )
            else:
                detailed_error = (
                    f"RCON Connection Error\n\n"
                    f"Error: {str(e)}\n\n"
                    f"The port is accessible but RCON failed.\n"
                    f"Check your RCON configuration in server.properties."
                )

            messagebox.showerror("RCON Error", detailed_error)
            return None

    def reconnect_rcon(self):
        """Attempt to reconnect to RCON server"""
        print("🔄 Attempting to reconnect to RCON...")
        self.server_status_label.config(text="Connecting... ⏳", bootstyle="warning")
        self.reconnect_btn.config(state="disabled")

        # Try to reconnect
        self.mcr = self.connect_rcon()

        # Update UI based on connection result
        if self.mcr:
            self.server_status_label.config(text="Connected ✅", bootstyle="success")
            print("✅ Reconnection successful!")
        else:
            self.server_status_label.config(text="Disconnected ❌", bootstyle="danger")
            print("❌ Reconnection failed")

        self.reconnect_btn.config(state="normal")

    def schedule_player_refresh(self):
        self.update_players()
        self.root.after(5000, self.schedule_player_refresh)  # every 5 seconds

    def setup_gui(self):
        # Configure root grid weights
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=0)  # Bottom panel (fixed height)
        self.root.grid_rowconfigure(2, weight=0)  # Status bar (fixed height)
        self.root.grid_columnconfigure(0, weight=1)

        # Main container for top panels
        main_frame = tb.Frame(self.root, padding=15)
        main_frame.grid(row=0, column=0, sticky="nsew")

        # Configure main frame grid weights
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)

        # Left panel - Main controls
        left_frame = tb.LabelFrame(main_frame, text="Commands", padding=15)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        tb.Label(left_frame, text="Item/Effect:").grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )

        self.search_entry = tb.Entry(left_frame)
        self.search_entry.grid(row=0, column=1, pady=(0, 5))
        self.search_entry.bind("<KeyRelease>", self.update_fuzzy_list)

        self.type_var = tb.StringVar(value="item")
        tb.OptionMenu(left_frame, self.type_var, "item", "item", "effect").grid(
            row=0, column=2, pady=(0, 5)
        )

        self.result_tree = Treeview(
            left_frame,
            columns=("label",),
            show="",  # ⬅️ hide column headers
            height=5,
            bootstyle="dark",
        )
        self.result_tree.configure(selectmode="browse", takefocus=False)
        self.result_tree.column("label", anchor="w", stretch=True, width=250)
        self.result_tree.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0, 10))

        tb.Label(left_frame, text="Player:").grid(
            row=2, column=0, sticky="w", pady=(0, 5)
        )
        self.player_box = tb.Combobox(
            left_frame, textvariable=self.player_var, values=[]
        )
        self.player_box.grid(row=2, column=1, columnspan=2, sticky="we", pady=(0, 5))

        tb.Label(left_frame, text="Amount/Duration:").grid(
            row=3, column=0, sticky="w", pady=(0, 5)
        )
        self.amount_entry = tb.Entry(left_frame)
        self.amount_entry.grid(row=3, column=1, columnspan=2, pady=(0, 5))

        # Checkbox for applying enchantments
        self.apply_enchants_var = tb.BooleanVar(value=False)
        self.apply_enchants_check = tb.Checkbutton(
            left_frame,
            text="Apply enchantments from list",
            variable=self.apply_enchants_var,
        )
        self.apply_enchants_check.grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(5, 5)
        )

        self.send_button = tb.Button(
            left_frame, text="Send Command", command=self.send_command
        )
        self.send_button.grid(row=5, column=0, columnspan=3, pady=(10, 0))

        # Right panel - Enchantment Manager
        right_frame = tb.LabelFrame(main_frame, text="Enchantment Manager", padding=15)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # Configure right frame grid
        right_frame.grid_rowconfigure(2, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # Enchantment search
        tb.Label(right_frame, text="Add Enchantment:", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )

        enchant_search_frame = tb.Frame(right_frame)
        enchant_search_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        enchant_search_frame.grid_columnconfigure(0, weight=1)

        self.enchant_search_entry = tb.Entry(enchant_search_frame)
        self.enchant_search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.enchant_search_entry.bind("<KeyRelease>", self.update_enchant_suggestions)
        self.enchant_search_entry.bind("<Return>", self.add_selected_enchantment)

        # Level entry
        tb.Label(enchant_search_frame, text="Lvl:").grid(row=0, column=1, padx=(5, 2))
        self.enchant_level_entry = tb.Entry(enchant_search_frame, width=5)
        self.enchant_level_entry.grid(row=0, column=2, padx=(0, 5))
        self.enchant_level_entry.insert(0, "1")

        add_enchant_btn = tb.Button(
            enchant_search_frame,
            text="Add",
            command=self.add_selected_enchantment,
            width=8,
        )
        add_enchant_btn.grid(row=0, column=3)

        # Enchantment suggestions dropdown
        self.enchant_suggestions = Treeview(
            right_frame,
            columns=("label",),
            show="",
            height=3,
            bootstyle="dark",
        )
        self.enchant_suggestions.configure(selectmode="browse", takefocus=False)
        self.enchant_suggestions.column("label", anchor="w", stretch=True, width=200)
        self.enchant_suggestions.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.enchant_suggestions.bind(
            "<Double-Button-1>", self.add_selected_enchantment
        )

        # Selected enchantments list
        tb.Label(
            right_frame, text="Selected Enchantments:", font=("", 10, "bold")
        ).grid(row=3, column=0, sticky="w", pady=(10, 5))

        # Scrollable enchantments list with remove buttons
        enchant_list_frame = tb.Frame(right_frame)
        enchant_list_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        enchant_list_frame.grid_rowconfigure(0, weight=1)
        enchant_list_frame.grid_columnconfigure(0, weight=1)

        self.enchant_listbox_frame = tb.Frame(enchant_list_frame)
        self.enchant_listbox_frame.grid(row=0, column=0, sticky="nsew")
        self.enchant_listbox_frame.grid_columnconfigure(0, weight=1)

        # Clear all button
        clear_all_btn = tb.Button(
            right_frame,
            text="Clear All Enchantments",
            command=self.clear_all_enchantments,
            bootstyle="danger-outline",
        )
        clear_all_btn.grid(row=5, column=0, sticky="ew", pady=(5, 0))

        # Bottom panel - Server Info
        bottom_frame = tb.LabelFrame(self.root, text="Server Info", padding=15)
        bottom_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        bottom_frame.grid_columnconfigure(0, weight=1)
        bottom_frame.grid_columnconfigure(1, weight=1)
        bottom_frame.grid_columnconfigure(2, weight=2)

        # Server status
        status_frame = tb.Frame(bottom_frame)
        status_frame.grid(row=0, column=0, sticky="w")

        tb.Label(status_frame, text="Status:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        # Set initial status based on connection state
        if self.mcr:
            status_text = "Connected ✅"
            status_style = "success"
        else:
            status_text = "Disconnected ❌"
            status_style = "danger"

        self.server_status_label = tb.Label(
            status_frame, text=status_text, bootstyle=status_style
        )
        self.server_status_label.grid(row=0, column=1, sticky="w", padx=(5, 0))

        # Add reconnect button
        self.reconnect_btn = tb.Button(
            status_frame,
            text="Reconnect",
            command=self.reconnect_rcon,
            bootstyle="info-outline",
        )
        self.reconnect_btn.grid(row=0, column=2, sticky="w", padx=(10, 0))

        # Quick commands
        quick_frame = tb.Frame(bottom_frame)
        quick_frame.grid(row=0, column=1, sticky="ew", padx=(20, 0))

        tb.Button(
            quick_frame,
            text="Day",
            command=lambda: self.send_quick_command("/time set day"),
        ).grid(row=0, column=0, padx=(0, 2), pady=1)
        tb.Button(
            quick_frame,
            text="Night",
            command=lambda: self.send_quick_command("/time set night"),
        ).grid(row=0, column=1, padx=2, pady=1)
        tb.Button(
            quick_frame,
            text="Clear",
            command=lambda: self.send_quick_command("/weather clear"),
        ).grid(row=0, column=2, padx=2, pady=1)
        tb.Button(
            quick_frame,
            text="Rain",
            command=lambda: self.send_quick_command("/weather rain"),
        ).grid(row=0, column=3, padx=(2, 0), pady=1)

        # Online players
        players_frame = tb.Frame(bottom_frame)
        players_frame.grid(row=0, column=2, sticky="ew", padx=(20, 0))
        players_frame.grid_columnconfigure(1, weight=1)

        tb.Label(players_frame, text="Players:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.players_display = tb.Label(players_frame, text="Loading...", anchor="w")
        self.players_display.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        # Status bar at bottom
        self.status = tb.Label(
            self.root, text="", anchor="w", padding=(10, 2), bootstyle="dark"
        )
        self.status.grid(row=2, column=0, sticky="we", pady=(5, 5))

        # Initialize enchantment list
        self.selected_enchantments = []
        self.enchantment_widgets = []

    def update_players(self):
        try:
            if self.mcr is None:
                # No RCON connection available
                if hasattr(self, "server_status_label"):
                    self.server_status_label.config(
                        text="Disconnected ❌", bootstyle="danger"
                    )
                if hasattr(self, "players_display"):
                    self.players_display.config(text="No Connection")
                return

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

            # Update the compact player display in bottom panel
            if players:
                player_text = f"({len(players)}) {', '.join(players[:3])}"
                if len(players) > 3:
                    player_text += f", +{len(players) - 3} more"
            else:
                player_text = "(0) No players online"

            if hasattr(self, "players_display"):
                self.players_display.config(text=player_text)

            # Restore previous selection if still present
            if previous in players:
                self.player_var.set(previous)
            elif players:
                self.player_var.set(players[0])
            else:
                self.player_var.set("")

        except Exception as e:
            print("Error updating players:", e)
            # Update server status to show connection issue
            if hasattr(self, "server_status_label"):
                self.server_status_label.config(
                    text="Connection Error ❌", bootstyle="danger"
                )
            if hasattr(self, "players_display"):
                self.players_display.config(text="Connection Error")

    def send_quick_command(self, command):
        """Send a quick command to the server"""
        try:
            if self.mcr is None:
                self.set_status("❌ No server connection", "danger", duration=3000)
                return

            print(f"Sending quick command: {command}")
            response = self.mcr.command(command)
            self.set_status(f"✅ Command sent: {command}", "success")
        except Exception as e:
            self.set_status(f"❌ Error: {str(e)}", "danger", duration=5000)

    def update_enchant_suggestions(self, event=None):
        """Update the enchantment suggestions list based on search input"""
        query = self.enchant_search_entry.get().strip()
        self.enchant_suggestions.delete(*self.enchant_suggestions.get_children())

        if not query:
            return

        # Get enchantment data
        enchantments = TYPED_DATA.get("enchantment", [])
        labels = [label for label, _ in enchantments]

        # Find fuzzy matches
        results = process.extractBests(
            query, labels, scorer=fuzz.partial_ratio, limit=5
        )

        for label, score in results:
            if score > 30:  # Only show reasonable matches
                self.enchant_suggestions.insert("", "end", values=(label,))

    def add_selected_enchantment(self, event=None):
        """Add the selected enchantment to the list"""
        # Get selected enchantment from suggestions
        selected = self.enchant_suggestions.selection()
        if selected:
            enchant_name = self.enchant_suggestions.item(selected[0], "values")[0]
        else:
            # Try to use the search text directly
            enchant_name = self.enchant_search_entry.get().strip()
            if not enchant_name:
                return

        # Get level
        try:
            level = int(self.enchant_level_entry.get())
            if level < 1:
                level = 1
        except ValueError:
            level = 1

        # Check if enchantment already exists in list
        for existing_enchant, existing_level in self.selected_enchantments:
            if existing_enchant.lower() == enchant_name.lower():
                self.set_status(f"⚠️ {enchant_name} already in list", "warning")
                return

        # Add to list
        self.selected_enchantments.append((enchant_name, level))
        self.update_enchantment_display()

        # Clear search
        self.enchant_search_entry.delete(0, tk.END)
        self.enchant_level_entry.delete(0, tk.END)
        self.enchant_level_entry.insert(0, "1")
        self.enchant_suggestions.delete(*self.enchant_suggestions.get_children())

        self.set_status(f"✅ Added {enchant_name} (Level {level})", "success")

    def update_enchantment_display(self):
        """Update the display of selected enchantments"""
        # Clear existing widgets
        for widget_frame in self.enchantment_widgets:
            widget_frame.destroy()
        self.enchantment_widgets.clear()

        # Add enchantment entries
        for i, (enchant_name, level) in enumerate(self.selected_enchantments):
            enchant_frame = tb.Frame(self.enchant_listbox_frame)
            enchant_frame.grid(row=i, column=0, sticky="ew", pady=1)
            enchant_frame.grid_columnconfigure(0, weight=1)

            # Enchantment label
            label_text = f"{enchant_name} (Level {level})"
            enchant_label = tb.Label(enchant_frame, text=label_text, anchor="w")
            enchant_label.grid(row=0, column=0, sticky="ew", padx=(0, 5))

            # Remove button
            remove_btn = tb.Button(
                enchant_frame,
                text="✕",
                command=lambda idx=i: self.remove_enchantment(idx),
                width=3,
                bootstyle="danger-outline",
            )
            remove_btn.grid(row=0, column=1)

            self.enchantment_widgets.append(enchant_frame)

    def remove_enchantment(self, index):
        """Remove an enchantment from the list"""
        if 0 <= index < len(self.selected_enchantments):
            removed = self.selected_enchantments.pop(index)
            self.update_enchantment_display()
            self.set_status(f"✅ Removed {removed[0]}", "success")

    def clear_all_enchantments(self):
        """Clear all selected enchantments"""
        if self.selected_enchantments:
            self.selected_enchantments.clear()
            self.update_enchantment_display()
            self.set_status("✅ Cleared all enchantments", "success")
        else:
            self.set_status("⚠️ No enchantments to clear", "warning")

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
            if self.mcr is None:
                self.set_status("❌ No server connection", "danger", duration=3000)
                return

            if self.type_var.get() == "item":
                # Check if we should apply enchantments
                if self.apply_enchants_var.get() and self.selected_enchantments:
                    # Build enchantment NBT data
                    enchant_data = []
                    enchant_map = dict(TYPED_DATA.get("enchantment", []))

                    for enchant_name, level in self.selected_enchantments:
                        # Try to resolve enchantment name
                        enchant_id = enchant_map.get(
                            enchant_name,
                            f"minecraft:{enchant_name.lower().replace(' ', '_')}",
                        )
                        enchant_data.append(f'{{id:"{enchant_id}",lvl:{level}s}}')

                    enchantments_nbt = f"{{Enchantments:[{','.join(enchant_data)}]}}"
                    cmd = f"/give {player} {resolved}{enchantments_nbt} {amount}"
                else:
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
    # Launch GUI first
    root = tb.Window(themename="darkly")  # or "superhero", "cyborg", etc.
    root.geometry("1000x650")  # Set initial window size for the expanded layout
    root.minsize(950, 600)  # Set minimum window size to prevent cramping

    # Set application icon with error handling
    try:
        if sys.platform.startswith("win"):
            icon_path = "icon.ico"
            if os.path.exists(icon_path):
                root.iconbitmap(icon_path)
            else:
                print(f"⚠️ Warning: Icon file not found at {os.path.abspath(icon_path)}")
        else:
            icon_path = "icon.png"
            if os.path.exists(icon_path):
                root.iconphoto(False, tk.PhotoImage(file=icon_path))
            else:
                print(f"⚠️ Warning: Icon file not found at {os.path.abspath(icon_path)}")
    except Exception as e:
        print(f"⚠️ Warning: Could not load application icon: {e}")
        # Continue without icon - not a critical error

    # Create the app - it will handle RCON connection internally
    app = MinecraftAdminApp(root)
    root.mainloop()
