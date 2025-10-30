import os, json, re, sys, socket
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.widgets import Treeview
from mcrcon import MCRcon
from fuzzywuzzy import fuzz, process

# Debug flag - set to True for verbose output
DEBUG = False


# Load config
def load_config():
    config = {}
    config_found = True

    try:
        with open("server_config.txt") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line:
                    key, val = line.split("=", 1)
                    config[key] = val
    except FileNotFoundError:
        if DEBUG:
            print("❌ server_config.txt not found!")
            print("Please create server_config.txt with your server settings.")
        config_found = False
    except Exception as e:
        if DEBUG:
            print(f"❌ Error reading config: {e}")
        config_found = False

    config["_config_found"] = config_found
    return config


def load_locations_from_config(config):
    """Extract named teleport locations from the configuration"""
    locations = {}

    for key, value in config.items():
        if not key.startswith("location_"):
            continue

        raw_name = key[len("location_") :]
        if not raw_name:
            continue

        # Convert configuration key to human readable name
        display_name = raw_name.replace("_", " ").title()

        # Allow coordinates to be separated by space or comma
        cleaned = value.replace(",", " ").split()
        if len(cleaned) < 3:
            if DEBUG:
                print(
                    f"⚠️ Ignoring location '{key}' - expected 3 coordinates, got '{value}'"
                )
            continue

        coords = " ".join(cleaned[:3])
        locations[display_name] = coords

    if not locations:
        # Provide a sensible default spawn location (overworld spawn)
        locations["Main Spawn"] = "0 64 0"

    return locations


def test_connection(host, port, timeout=5):
    """Test if a TCP connection can be established to the given host and port"""
    try:
        # Resolve hostname to IP
        ip = socket.gethostbyname(host)
        if DEBUG:
            print(f"🔍 Resolved {host} to {ip}")

        # Test TCP connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()

        if result == 0:
            if DEBUG:
                print(f"✅ Port {port} is open and accepting connections on {host}")
            return True, "Connection successful"
        else:
            if DEBUG:
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


def camel_to_snake_case(name):
    """Convert CamelCase to snake_case for Minecraft IDs"""
    import re

    # Insert underscore before uppercase letters (except the first one)
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    # Insert underscore before uppercase letters preceded by lowercase letters or digits
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def load_data():
    data = {}
    for typename in ["item", "effect", "enchantment"]:  # Add more types here as needed
        filename = f"{typename}s.json"
        path = os.path.join("data", filename)
        try:
            with open(path, "r") as f:
                raw = json.load(f)
                if typename == "effect":
                    # For effects, include type information (good/bad)
                    data[typename] = [
                        (
                            entry["displayName"],
                            f"minecraft:{camel_to_snake_case(entry['name'])}",
                            entry.get("type", "good"),
                        )
                        for entry in raw
                        if "name" in entry and "displayName" in entry
                    ]
                else:
                    # For items and enchantments, keep the old format
                    data[typename] = [
                        (
                            entry["displayName"],
                            f"minecraft:{camel_to_snake_case(entry['name'])}",
                        )
                        for entry in raw
                        if "name" in entry and "displayName" in entry
                    ]
        except FileNotFoundError:
            print(f"Warning: {filename} not found.")
            data[typename] = []
    return data


TYPED_DATA = load_data()


def get_minecraft_id(display_name, data_type):
    """Helper function to get minecraft ID from display name"""
    entries = TYPED_DATA.get(data_type, [])
    entry_map = {entry[0]: entry[1] for entry in entries}
    return entry_map.get(
        display_name, f"minecraft:{display_name.lower().replace(' ', '_')}"
    )


def fuzzy_search_data(query, data_type, limit=10, min_score=30):
    """Generic fuzzy search function for any data type"""
    entries = TYPED_DATA.get(data_type, [])
    labels = [entry[0] for entry in entries]

    results = process.extractBests(
        query, labels, scorer=fuzz.partial_ratio, limit=limit
    )
    return [(label, score) for label, score in results if score > min_score]


def execute_rcon_command(
    mcr, command, success_message="Command executed", return_response=False
):
    """Execute an RCON command with proper error handling"""
    if mcr is None:
        return False, "❌ No server connection"

    try:
        if DEBUG:
            print(f"Sending command: {command}")
        response = mcr.command(command)
        if DEBUG:
            print(f"Server response: {response}")

        if return_response:
            return True, response
        else:
            return True, f"✅ {success_message}"
    except Exception as e:
        return False, f"❌ {str(e)}"


def validate_command_inputs(name, player, amount_or_duration):
    """Validate common command inputs (name, player, numeric value)"""
    if not name or not player or not amount_or_duration.isdigit():
        return False
    return True


class MinecraftAdminApp:
    def __init__(self, root, mcr=None):
        self.player_var = tb.StringVar()
        self.root = root
        self.root.title("Minecraft server DADmin")
        self.config = load_config()
        self.known_locations = load_locations_from_config(self.config)
        self.current_players = []
        self.teleport_destination_map = {}
        self.mcr = mcr or self.connect_rcon()
        self.setup_gui()

        # Show error if config file was not found
        if not self.config.get("_config_found", True):
            self.set_status(
                "❌ No server_config.txt found! Click Settings to create configuration.",
                "danger",
                duration=15000,
            )

        self.schedule_player_refresh()

    def connect_rcon(self):
        # Check if config was loaded successfully
        if not self.config.get("_config_found", False):
            if DEBUG:
                print("❌ Cannot connect: No configuration file found")
            return None

        # Check if required settings are present
        required_settings = ["host", "port", "password"]
        missing_settings = [
            setting for setting in required_settings if not self.config.get(setting)
        ]
        if missing_settings:
            if DEBUG:
                print(
                    f"❌ Cannot connect: Missing required settings: {', '.join(missing_settings)}"
                )
            return None

        host = self.config["host"]
        port = int(self.config["port"])

        if DEBUG:
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
                if DEBUG:
                    print(f"❌ Connection failed: {test_msg}")
                messagebox.showerror("RCON Connection Failed", detailed_error)
                return None

            # Port is accessible, try RCON connection
            mcr = MCRcon(host, self.config["password"], port)
            mcr.connect()
            if DEBUG:
                print("✅ RCON connection established.")
            return mcr

        except Exception as e:
            if DEBUG:
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
        if DEBUG:
            print("🔄 Attempting to reconnect to RCON...")
        self.server_status_label.config(text="Connecting... ⏳", bootstyle="warning")
        self.reconnect_btn.config(state="disabled")

        # Try to reconnect
        self.mcr = self.connect_rcon()

        # Update UI based on connection result
        if self.mcr:
            self.server_status_label.config(text="Connected ✅", bootstyle="success")
            if DEBUG:
                print("✅ Reconnection successful!")
        else:
            self.server_status_label.config(text="Disconnected ❌", bootstyle="danger")
            if DEBUG:
                print("❌ Reconnection failed")

        self.reconnect_btn.config(state="normal")

    def save_config(self, config):
        """Save configuration to file"""
        try:
            with open("server_config.txt", "w") as f:
                for key, value in config.items():
                    # Skip internal flags
                    if not key.startswith("_"):
                        f.write(f"{key}={value}\n")
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def open_settings(self):
        """Open the server settings dialog"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Server Settings")
        settings_window.geometry("500x450")
        settings_window.resizable(False, False)
        settings_window.transient(self.root)
        settings_window.grab_set()

        # Center the window
        settings_window.update_idletasks()
        x = (settings_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (settings_window.winfo_screenheight() // 2) - (450 // 2)
        settings_window.geometry(f"500x450+{x}+{y}")

        # Create ttkbootstrap frame
        main_frame = tb.Frame(settings_window, padding=20)
        main_frame.pack(fill="both", expand=True)

        # Title
        tb.Label(
            main_frame, text="Minecraft Server Configuration", font=("", 14, "bold")
        ).pack(pady=(0, 20))

        # Configuration fields
        config_frame = tb.Frame(main_frame)
        config_frame.pack(fill="x", pady=(0, 20))

        # Host
        tb.Label(config_frame, text="Host:").grid(row=0, column=0, sticky="w", pady=5)
        host_var = tb.StringVar(value=self.config.get("host", ""))
        host_entry = tb.Entry(config_frame, textvariable=host_var, width=30)
        host_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=5)

        # Port
        tb.Label(config_frame, text="Port:").grid(row=1, column=0, sticky="w", pady=5)
        port_var = tb.StringVar(value=self.config.get("port", ""))
        port_entry = tb.Entry(config_frame, textvariable=port_var, width=30)
        port_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=5)

        # Password
        tb.Label(config_frame, text="Password:").grid(
            row=2, column=0, sticky="w", pady=5
        )
        password_var = tb.StringVar(value=self.config.get("password", ""))
        password_entry = tb.Entry(config_frame, textvariable=password_var, width=30)
        password_entry.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=5)

        config_frame.grid_columnconfigure(1, weight=1)

        # Info text
        info_text = (
            "These settings correspond to your server.properties file:\n\n"
            "enable-rcon=true\n"
            "rcon.port=25575\n"
            "rcon.password=your_password\n\n"
            "Make sure to restart your server after changing RCON settings."
        )
        info_label = tb.Label(
            main_frame,
            text=info_text,
            justify="left",
            foreground="#888888",
            font=("", 9),
            wraplength=400,
        )
        info_label.pack(fill="x", pady=(0, 20))

        # Buttons
        button_frame = tb.Frame(main_frame)
        button_frame.pack(fill="x")

        def test_connection_dialog():
            """Test the connection with current settings"""
            temp_config = {
                "host": host_var.get().strip(),
                "port": port_var.get().strip(),
                "password": password_var.get(),
            }

            if not temp_config["host"] or not temp_config["port"]:
                messagebox.showerror("Error", "Host and Port are required!")
                return

            try:
                port_num = int(temp_config["port"])
            except ValueError:
                messagebox.showerror("Error", "Port must be a number!")
                return

            # Test full RCON connection including authentication
            try:
                # First test if port is accessible
                can_connect, port_msg = test_connection(temp_config["host"], port_num)
                if not can_connect:
                    messagebox.showerror("Connection Test", f"❌ {port_msg}")
                    return

                # Test actual RCON authentication
                test_mcr = MCRcon(
                    temp_config["host"], temp_config["password"], port_num
                )
                test_mcr.connect()

                # Try a simple command to verify authentication works
                response = test_mcr.command("list")
                test_mcr.disconnect()

                messagebox.showinfo(
                    "Connection Test",
                    "✅ RCON connection and authentication successful!",
                )

            except Exception as e:
                error_msg = str(e).lower()
                if (
                    "authentication failed" in error_msg
                    or "invalid password" in error_msg
                ):
                    messagebox.showerror(
                        "Connection Test",
                        "❌ RCON authentication failed!\n\nCheck your password.",
                    )
                else:
                    messagebox.showerror(
                        "Connection Test", f"❌ Connection failed:\n{str(e)}"
                    )

        def save_and_close():
            """Save settings and close dialog"""
            new_config = dict(self.config)
            new_config["host"] = host_var.get().strip()
            new_config["port"] = port_var.get().strip()
            new_config["password"] = password_var.get()

            if not new_config["host"] or not new_config["port"]:
                messagebox.showerror("Error", "Host and Port are required!")
                return

            try:
                int(new_config["port"])
            except ValueError:
                messagebox.showerror("Error", "Port must be a number!")
                return

            if self.save_config(new_config):
                # Reload configuration from file to ensure consistency
                self.config = load_config()
                self.known_locations = load_locations_from_config(self.config)
                if hasattr(self, "teleport_source_box"):
                    self.refresh_teleport_options()

                # Update status to show we're reconnecting
                if hasattr(self, "server_status_label"):
                    self.server_status_label.config(
                        text="Connecting... ⏳", bootstyle="warning"
                    )

                # Attempt to reconnect with new settings
                self.mcr = self.connect_rcon()

                # Update server status based on connection result
                if hasattr(self, "server_status_label"):
                    if self.mcr:
                        self.server_status_label.config(
                            text="Connected ✅", bootstyle="success"
                        )
                        connection_msg = "Settings saved and connected successfully!"
                    else:
                        self.server_status_label.config(
                            text="Disconnected ❌", bootstyle="danger"
                        )
                        connection_msg = (
                            "Settings saved but connection failed. Check your settings."
                        )

                messagebox.showinfo("Settings", connection_msg)
                settings_window.destroy()
            else:
                messagebox.showerror("Error", "Failed to save settings!")

        tb.Button(
            button_frame,
            text="Test Connection",
            command=test_connection_dialog,
            bootstyle="info",
        ).pack(side="left", padx=(0, 10))
        tb.Button(
            button_frame, text="Save", command=save_and_close, bootstyle="success"
        ).pack(side="left", padx=(0, 10))
        tb.Button(
            button_frame,
            text="Cancel",
            command=settings_window.destroy,
            bootstyle="secondary",
        ).pack(side="left")

    def schedule_player_refresh(self):
        self.update_players()
        self.root.after(5000, self.schedule_player_refresh)  # every 5 seconds

    def setup_gui(self):
        # Configure root grid weights
        self.root.grid_rowconfigure(0, weight=0)  # Player selection (fixed height)
        self.root.grid_rowconfigure(1, weight=1)  # Main panels (expandable)
        self.root.grid_rowconfigure(2, weight=0)  # Bottom panel (fixed height)
        self.root.grid_rowconfigure(3, weight=0)  # Status bar (fixed height)
        self.root.grid_columnconfigure(0, weight=1)

        # === PLAYER SELECTION AT TOP ===
        player_frame = tb.LabelFrame(self.root, text="Target Player", padding=15)
        player_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        player_frame.grid_columnconfigure(1, weight=1)

        tb.Label(player_frame, text="Player:", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.player_box = tb.Combobox(
            player_frame, textvariable=self.player_var, values=[], width=30
        )
        self.player_box.grid(row=0, column=1, sticky="ew")

        # === MAIN CONTENT AREA ===
        main_frame = tb.Frame(self.root, padding=15)
        main_frame.grid(row=1, column=0, sticky="nsew")

        # Configure main frame grid - two rows, effects on top, items below
        main_frame.grid_rowconfigure(0, weight=0)  # Effects (fixed height)
        main_frame.grid_rowconfigure(1, weight=1)  # Items + enchantments (expandable)
        main_frame.grid_columnconfigure(0, weight=1)

        # === EFFECTS SECTION ===
        effects_frame = tb.LabelFrame(main_frame, text="Give Effect", padding=15)
        effects_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        effects_frame.grid_columnconfigure(1, weight=1)

        tb.Label(effects_frame, text="Effect:").grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )
        self.effect_search_entry = tb.Entry(effects_frame)
        self.effect_search_entry.grid(
            row=0, column=1, sticky="ew", pady=(0, 5), padx=(5, 10)
        )
        self.effect_search_entry.bind("<KeyRelease>", self.update_effect_list)

        tb.Label(effects_frame, text="Duration (sec):").grid(
            row=0, column=2, sticky="w", pady=(0, 5), padx=(0, 5)
        )
        self.effect_duration_entry = tb.Entry(effects_frame, width=10)
        self.effect_duration_entry.grid(row=0, column=3, pady=(0, 5), padx=(0, 10))
        self.effect_duration_entry.insert(0, "30")

        self.give_effect_button = tb.Button(
            effects_frame,
            text="Give Effect",
            command=self.send_effect_command,
            bootstyle="success",
        )
        self.give_effect_button.grid(row=0, column=4, pady=(0, 5))

        # Effects suggestions
        self.effect_result_tree = Treeview(
            effects_frame,
            columns=("label",),
            show="",
            height=3,
            bootstyle="dark",
        )
        self.effect_result_tree.configure(selectmode="browse", takefocus=False)
        self.effect_result_tree.column("label", anchor="w", stretch=True, width=300)
        # Add color tags for good/bad effects
        self.effect_result_tree.tag_configure(
            "good_effect", foreground="#4CAF50"
        )  # Green for good effects
        self.effect_result_tree.tag_configure(
            "bad_effect", foreground="#F44336"
        )  # Red for bad effects
        self.effect_result_tree.grid(
            row=1, column=0, columnspan=5, sticky="ew", pady=(5, 0)
        )
        self.effect_result_tree.bind("<Double-Button-1>", self.send_effect_command)

        # === ITEMS SECTION (with enchantments on the right) ===
        items_container = tb.Frame(main_frame)
        items_container.grid(row=1, column=0, sticky="nsew")
        items_container.grid_rowconfigure(0, weight=1)
        # Force equal column widths with uniform configuration
        items_container.grid_columnconfigure(0, weight=1, uniform="col")
        items_container.grid_columnconfigure(1, weight=1, uniform="col")

        # Left side - Item selection
        items_frame = tb.LabelFrame(items_container, text="Give Item", padding=15)
        items_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2.5))
        items_frame.grid_rowconfigure(2, weight=1)  # Items list is now on row 2
        items_frame.grid_columnconfigure(1, weight=1)

        tb.Label(items_frame, text="Item:").grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )
        self.item_search_entry = tb.Entry(items_frame)
        self.item_search_entry.grid(
            row=0, column=1, sticky="ew", pady=(0, 5), padx=(5, 0), columnspan=3
        )
        self.item_search_entry.bind("<KeyRelease>", self.update_item_list)

        # Second row for amount and checkbox
        tb.Label(items_frame, text="Amount:").grid(
            row=1, column=0, sticky="w", pady=(0, 5)
        )
        self.item_amount_entry = tb.Entry(items_frame, width=8)
        self.item_amount_entry.grid(
            row=1, column=1, sticky="w", pady=(0, 5), padx=(5, 10)
        )
        self.item_amount_entry.insert(0, "1")

        # Checkbox for applying enchantments
        self.apply_enchants_var = tb.BooleanVar(value=False)
        self.apply_enchants_check = tb.Checkbutton(
            items_frame,
            text="Apply enchantments from list",
            variable=self.apply_enchants_var,
        )
        self.apply_enchants_check.grid(
            row=1, column=2, sticky="w", pady=(0, 5), padx=(10, 0), columnspan=2
        )

        # Items suggestions list
        self.item_result_tree = Treeview(
            items_frame,
            columns=("label",),
            show="",
            bootstyle="dark",
        )
        self.item_result_tree.configure(selectmode="browse", takefocus=False)
        self.item_result_tree.column("label", anchor="w", stretch=True, width=300)
        self.item_result_tree.grid(
            row=2, column=0, columnspan=4, sticky="nsew", pady=(10, 10)
        )
        self.item_result_tree.bind("<Double-Button-1>", self.send_item_command)

        self.give_item_button = tb.Button(
            items_frame,
            text="Give Item",
            command=self.send_item_command,
            bootstyle="primary",
        )
        self.give_item_button.grid(row=3, column=0, columnspan=4, pady=(0, 0))

        # Right side - Enchantment Manager
        enchant_frame = tb.LabelFrame(
            items_container, text="Enchantment Manager", padding=15
        )
        enchant_frame.grid(row=0, column=1, sticky="nsew", padx=(2.5, 0))

        # Configure enchant frame grid
        enchant_frame.grid_rowconfigure(
            4, weight=1
        )  # Make selected enchantments list expandable
        enchant_frame.grid_columnconfigure(0, weight=1)

        # Enchantment search
        tb.Label(enchant_frame, text="Add Enchantment:", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )

        enchant_search_frame = tb.Frame(enchant_frame)
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
            enchant_frame,
            columns=("label",),
            show="",
            height=3,
            bootstyle="dark",
        )
        self.enchant_suggestions.configure(selectmode="browse", takefocus=False)
        self.enchant_suggestions.column("label", anchor="w", stretch=True, width=200)
        self.enchant_suggestions.grid(
            row=2, column=0, sticky="ew", pady=(0, 10), ipady=0
        )
        self.enchant_suggestions.bind(
            "<Double-Button-1>", self.add_selected_enchantment
        )

        # Selected enchantments list
        tb.Label(
            enchant_frame, text="Selected Enchantments:", font=("", 10, "bold")
        ).grid(row=3, column=0, sticky="w", pady=(10, 5))

        # Scrollable enchantments list with remove buttons
        enchant_list_frame = tb.Frame(enchant_frame)
        enchant_list_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        enchant_list_frame.grid_rowconfigure(0, weight=1)
        enchant_list_frame.grid_columnconfigure(0, weight=1)

        self.enchant_listbox_frame = tb.Frame(enchant_list_frame)
        self.enchant_listbox_frame.grid(row=0, column=0, sticky="nsew")
        self.enchant_listbox_frame.grid_columnconfigure(0, weight=1)

        # Clear all button
        clear_all_btn = tb.Button(
            enchant_frame,
            text="Clear All Enchantments",
            command=self.clear_all_enchantments,
            bootstyle="danger-outline",
        )
        clear_all_btn.grid(row=5, column=0, sticky="ew", pady=(5, 0))

        # === BOTTOM PANEL - SERVER INFO ===
        bottom_frame = tb.LabelFrame(self.root, text="Server Info", padding=15)
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(10, 15))
        bottom_frame.grid_columnconfigure(0, weight=1)
        bottom_frame.grid_columnconfigure(1, weight=1)
        bottom_frame.grid_columnconfigure(2, weight=2)
        bottom_frame.grid_rowconfigure(0, weight=0)
        bottom_frame.grid_rowconfigure(1, weight=0)
        bottom_frame.grid_rowconfigure(2, weight=0)

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

        # Add settings button
        self.settings_btn = tb.Button(
            status_frame,
            text="Settings",
            command=self.open_settings,
            bootstyle="secondary-outline",
        )
        self.settings_btn.grid(row=0, column=3, sticky="w", padx=(5, 0))

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

        # Teleport controls
        teleport_frame = tb.Frame(bottom_frame)
        teleport_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        teleport_frame.grid_columnconfigure(2, weight=1)
        teleport_frame.grid_columnconfigure(4, weight=1)

        tb.Label(teleport_frame, text="Teleport:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        tb.Label(teleport_frame, text="From:").grid(row=0, column=1, sticky="w")

        self.teleport_source_var = tb.StringVar()
        self.teleport_source_box = tb.Combobox(
            teleport_frame,
            textvariable=self.teleport_source_var,
            values=[],
            state="readonly",
            width=18,
        )
        self.teleport_source_box.grid(row=0, column=2, sticky="ew", padx=(5, 10))

        tb.Label(teleport_frame, text="To:").grid(row=0, column=3, sticky="w")

        self.teleport_dest_var = tb.StringVar()
        self.teleport_dest_box = tb.Combobox(
            teleport_frame,
            textvariable=self.teleport_dest_var,
            values=[],
            state="readonly",
            width=24,
        )
        self.teleport_dest_box.grid(row=0, column=4, sticky="ew", padx=(5, 10))

        self.teleport_button = tb.Button(
            teleport_frame,
            text="Teleport",
            command=self.send_teleport_command,
            bootstyle="info",
        )
        self.teleport_button.grid(row=0, column=5, sticky="w")

        # XP controls
        xp_frame = tb.Frame(bottom_frame)
        xp_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        xp_frame.grid_columnconfigure(2, weight=0)
        xp_frame.grid_columnconfigure(3, weight=0)

        tb.Label(xp_frame, text="Give XP:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        tb.Label(xp_frame, text="Amount:").grid(row=0, column=1, sticky="w")

        self.xp_amount_var = tb.StringVar(value="5")
        self.xp_amount_entry = tb.Entry(
            xp_frame, textvariable=self.xp_amount_var, width=8
        )
        self.xp_amount_entry.grid(row=0, column=2, sticky="w", padx=(5, 10))

        tb.Label(xp_frame, text="Type:").grid(row=0, column=3, sticky="w")
        self.xp_type_var = tb.StringVar(value="Levels")
        self.xp_type_box = tb.Combobox(
            xp_frame,
            textvariable=self.xp_type_var,
            values=["Levels", "Points"],
            state="readonly",
            width=10,
        )
        self.xp_type_box.grid(row=0, column=4, sticky="w", padx=(5, 10))
        self.xp_type_box.current(0)

        self.xp_button = tb.Button(
            xp_frame,
            text="Give XP",
            command=self.send_xp_command,
            bootstyle="success-outline",
        )
        self.xp_button.grid(row=0, column=5, sticky="w")

        # Status bar at bottom
        self.status = tb.Label(
            self.root, text="", anchor="w", padding=(10, 2), bootstyle="dark"
        )
        self.status.grid(row=3, column=0, sticky="we", pady=(5, 5))

        # Initialize enchantment list
        self.selected_enchantments = []
        self.enchantment_widgets = []
        self.refresh_teleport_options()

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

            success, resp = execute_rcon_command(
                self.mcr, "list", "Player list retrieved", return_response=True
            )
            if not success:
                # Handle connection error gracefully
                if hasattr(self, "server_status_label"):
                    self.server_status_label.config(
                        text="Connection Error ❌", bootstyle="danger"
                    )
                if hasattr(self, "players_display"):
                    self.players_display.config(text="Connection Error")
                return

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

            # Update teleport comboboxes with latest player list
            if hasattr(self, "teleport_source_box"):
                self.refresh_teleport_options()

        except Exception as e:
            if DEBUG:
                print("Error updating players:", e)
            # Update server status to show connection issue
            if hasattr(self, "server_status_label"):
                self.server_status_label.config(
                    text="Connection Error ❌", bootstyle="danger"
                )
            if hasattr(self, "players_display"):
                self.players_display.config(text="Connection Error")

    def refresh_teleport_options(self):
        """Refresh teleport source and destination combobox options"""
        if not hasattr(self, "teleport_source_box"):
            return

        players = list(self.current_players)

        # Update source player list
        current_source = self.teleport_source_var.get()
        self.teleport_source_box["values"] = players
        if current_source in players:
            self.teleport_source_var.set(current_source)
        elif players:
            self.teleport_source_var.set(players[0])
        else:
            self.teleport_source_var.set("")

        # Update destination options (players + named locations)
        current_dest = self.teleport_dest_var.get()
        self.teleport_destination_map = {}
        destination_options = []

        for name in players:
            label = f"Player: {name}"
            destination_options.append(label)
            self.teleport_destination_map[label] = ("player", name, name)

        for display_name, coords in self.known_locations.items():
            label = f"{display_name} ({coords})"
            destination_options.append(label)
            self.teleport_destination_map[label] = ("location", coords, display_name)

        self.teleport_dest_box["values"] = destination_options

        if current_dest in self.teleport_destination_map:
            self.teleport_dest_var.set(current_dest)
        else:
            fallback_option = None
            source_player = self.teleport_source_var.get()

            for option in destination_options:
                option_type, option_value, _ = self.teleport_destination_map[option]
                if option_type == "player" and option_value == source_player:
                    continue
                fallback_option = option
                break

            if fallback_option is None and destination_options:
                fallback_option = destination_options[0]

            if fallback_option:
                self.teleport_dest_var.set(fallback_option)
            else:
                self.teleport_dest_var.set("")

    def send_teleport_command(self):
        """Teleport one player to another player or a known location"""
        if self.mcr is None:
            self.set_status("❌ No server connection", "danger", duration=5000)
            return

        source_player = self.teleport_source_var.get().strip()
        destination_label = self.teleport_dest_var.get().strip()

        if not source_player:
            self.set_status("⚠️ Select a player to teleport", "warning")
            return

        if destination_label not in self.teleport_destination_map:
            self.set_status("⚠️ Select a teleport destination", "warning")
            return

        dest_type, dest_value, dest_display = self.teleport_destination_map[destination_label]

        if dest_type == "player" and dest_value == source_player:
            self.set_status(
                "⚠️ Destination player must be different from source", "warning"
            )
            return

        if dest_type == "player":
            cmd = f"/tp {source_player} {dest_value}"
            success_message = f"Teleported {source_player} to {dest_value}"
        else:
            cmd = f"/tp {source_player} {dest_value}"
            success_message = f"Teleported {source_player} to {dest_display}"

        success, message = execute_rcon_command(self.mcr, cmd, success_message)
        if success:
            self.set_status(message, "success")
        else:
            self.set_status(message, "danger", duration=5000)

    def send_xp_command(self):
        """Give experience points or levels to the selected player"""
        if self.mcr is None:
            self.set_status("❌ No server connection", "danger", duration=5000)
            return

        player = self.player_var.get().strip()
        amount_str = self.xp_amount_var.get().strip()
        xp_type_label = self.xp_type_var.get()

        if not player:
            self.set_status("⚠️ Select a player first", "warning")
            return

        try:
            amount = int(amount_str)
        except ValueError:
            self.set_status("⚠️ XP amount must be a whole number", "warning")
            return

        if amount <= 0:
            self.set_status("⚠️ XP amount must be greater than zero", "warning")
            return

        xp_type_value = "levels" if xp_type_label.lower().startswith("level") else "points"

        cmd = f"/xp add {player} {amount} {xp_type_value}"
        success_message = f"Gave {amount} {xp_type_value} to {player}"

        success, message = execute_rcon_command(self.mcr, cmd, success_message)
        if success:
            self.set_status(message, "success")
        else:
            self.set_status(message, "danger", duration=5000)

    def send_quick_command(self, command):
        """Send a quick command to the server"""
        success, message = execute_rcon_command(
            self.mcr, command, f"Command sent: {command}"
        )

        if success:
            self.set_status(message, "success")
        else:
            self.set_status(message, "danger", duration=5000)

    def update_enchant_suggestions(self, event=None):
        """Update the enchantment suggestions list based on search input"""
        query = self.enchant_search_entry.get().strip()
        self.enchant_suggestions.delete(*self.enchant_suggestions.get_children())

        if not query:
            return

        results = fuzzy_search_data(query, "enchantment", limit=5)
        for label, score in results:
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

    def update_effect_list(self, event=None):
        """Update the effect suggestions list based on search input"""
        query = self.effect_search_entry.get().strip()
        self.effect_result_tree.delete(*self.effect_result_tree.get_children())

        if not query:
            return

        # Create effect type lookup for visual indicators
        entries = TYPED_DATA.get("effect", [])
        effect_type_map = {entry[0]: entry[2] for entry in entries}

        results = fuzzy_search_data(query, "effect", limit=5)
        for label, score in results:
            effect_type = effect_type_map.get(label, "good")
            # Add visual indicators: ✅ for good effects, ❌ for bad effects
            if effect_type == "good":
                display_text = f"✅ {label}"
                tag = "good_effect"
            else:
                display_text = f"❌ {label}"
                tag = "bad_effect"

            self.effect_result_tree.insert(
                "", "end", values=(display_text,), tags=(tag,)
            )

    def update_item_list(self, event=None):
        """Update the item suggestions list based on search input"""
        query = self.item_search_entry.get().strip()
        self.item_result_tree.delete(*self.item_result_tree.get_children())

        if not query:
            return

        results = fuzzy_search_data(query, "item", limit=10)
        for label, score in results:
            self.item_result_tree.insert("", "end", values=(label,))

    def send_effect_command(self, event=None):
        """Send an effect command to the server"""
        # Get selected effect - require selection from search results
        selected = self.effect_result_tree.selection()
        if not selected:
            self.set_status(
                "⚠️ Please select an effect from the search results", "warning"
            )
            return

        display_name = self.effect_result_tree.item(selected[0], "values")[0]
        # Remove the ✅/❌ icons from the display name
        effect_name = display_name.replace("✅ ", "").replace("❌ ", "")

        player = self.player_var.get()
        duration = self.effect_duration_entry.get()

        if not validate_command_inputs(effect_name, player, duration):
            self.set_status("⚠️ Fill all fields before sending", "warning")
            return

        # Resolve effect name to minecraft ID
        resolved = get_minecraft_id(effect_name, "effect")

        cmd = f"/effect give {player} {resolved} {duration} 0 true"
        success, message = execute_rcon_command(
            self.mcr, cmd, f"Effect given: {effect_name} to {player}"
        )

        if success:
            self.set_status(message, "success")
        else:
            self.set_status(message, "danger", duration=5000)

    def send_item_command(self, event=None):
        """Send an item command to the server"""
        # Get selected item - require selection from search results
        selected = self.item_result_tree.selection()
        if not selected:
            self.set_status(
                "⚠️ Please select an item from the search results", "warning"
            )
            return

        item_name = self.item_result_tree.item(selected[0], "values")[0]

        player = self.player_var.get()
        amount = self.item_amount_entry.get()

        if not validate_command_inputs(item_name, player, amount):
            self.set_status("⚠️ Fill all fields before sending", "warning")
            return

        # Resolve item name to minecraft ID
        resolved = get_minecraft_id(item_name, "item")

        try:
            if self.mcr is None:
                self.set_status("❌ No server connection", "danger", duration=3000)
                return

            # Check if we should apply enchantments
            if self.apply_enchants_var.get() and self.selected_enchantments:
                # Build modern data component format
                if DEBUG:
                    print(
                        f"DEBUG: Applying {len(self.selected_enchantments)} enchantments:"
                    )

                component_enchants = []
                for enchant_name, level in self.selected_enchantments:
                    # Get minecraft ID and remove 'minecraft:' prefix for component format
                    minecraft_id = get_minecraft_id(enchant_name, "enchantment")
                    clean_name = minecraft_id.replace("minecraft:", "")
                    if DEBUG:
                        print(f"  - {enchant_name} -> {clean_name} (level {level})")
                    component_enchants.append(f"{clean_name}:{level}")

                # Modern data component syntax: item[enchantments={enchant:level}]
                cmd = f"/give {player} {resolved}[enchantments={{{','.join(component_enchants)}}}] {amount}"
                if DEBUG:
                    print(f"DEBUG: Using data component format: {cmd}")
            else:
                cmd = f"/give {player} {resolved} {amount}"

            success, response = execute_rcon_command(
                self.mcr, cmd, "Item command sent", return_response=True
            )
            if not success:
                self.set_status(response, "danger", duration=5000)
                return

            # Simple fallback: if data component format failed, try without enchantments
            if (
                (
                    "Expected" in response
                    or "Invalid" in response
                    or "Unknown" in response
                )
                and self.apply_enchants_var.get()
                and self.selected_enchantments
            ):
                if DEBUG:
                    print(
                        "DEBUG: Data component format failed, giving item without enchantments..."
                    )
                basic_cmd = f"/give {player} {resolved} {amount}"
                success, response = execute_rcon_command(
                    self.mcr,
                    basic_cmd,
                    "Item given without enchantments",
                    return_response=True,
                )
                if not success:
                    self.set_status(response, "danger", duration=5000)
                    return
                self.set_status(
                    f"⚠️ Item given without enchantments: {item_name} to {player}",
                    "warning",
                )
                return

            enchant_text = (
                f" with {len(self.selected_enchantments)} enchantments"
                if self.apply_enchants_var.get() and self.selected_enchantments
                else ""
            )
            self.set_status(
                f"✅ Item given: {item_name} x{amount} to {player}{enchant_text}",
                "success",
            )
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
    root.geometry("1200x700")  # Set initial window size for the new layout
    root.minsize(900, 600)  # Allow narrower windows while keeping layout usable

    # Set application icon with PyInstaller compatibility
    def get_resource_path(relative_path):
        """Get absolute path to resource, works for dev and for PyInstaller"""
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    try:
        if sys.platform.startswith("win"):
            icon_path = get_resource_path("icon.ico")
            if os.path.exists(icon_path):
                root.iconbitmap(icon_path)
                root.wm_iconbitmap(icon_path)
            else:
                # Fallback: try in current directory
                if os.path.exists("icon.ico"):
                    root.iconbitmap("icon.ico")
                    root.wm_iconbitmap("icon.ico")
                else:
                    print(
                        f"⚠️ Warning: Icon file not found at {icon_path} or current directory"
                    )
        else:
            icon_path = get_resource_path("icon.png")
            if os.path.exists(icon_path):
                icon_image = tk.PhotoImage(file=icon_path)
                root.iconphoto(False, icon_image)
            else:
                # Fallback: try in current directory
                if os.path.exists("icon.png"):
                    icon_image = tk.PhotoImage(file="icon.png")
                    root.iconphoto(False, icon_image)
                else:
                    print(
                        f"⚠️ Warning: Icon file not found at {icon_path} or current directory"
                    )
    except Exception as e:
        print(f"⚠️ Warning: Could not load application icon: {e}")
        # Continue without icon - not a critical error

    # Create the app - it will handle RCON connection internally
    app = MinecraftAdminApp(root)
    root.mainloop()
