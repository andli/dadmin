# dadmin — A Minecraft RCON Admin GUI

A minimalist dark-themed desktop GUI for administering a local Minecraft server via RCON. Helping you, the dadmin, not having to type `/give` all the bloody time.

Right now the app supports giving _items_ and applying _effects_.

The app is designed for localhost use and single-server setups.

## Features

- 🔍 Fuzzy search for items and effects
- 🎮 Player selector with auto-refresh
- 🧪 Give items or apply effects via dropdown

## Requirements

- Python 3.10+
- A Minecraft server with RCON enabled (`server.properties`)
- `server_config.txt` with:
  ```
  host=localhost
  port=25575
  password=your_rcon_password
  ```

## Setup

1. (Optional) Create a virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:
   ```bash
   python dadmin.py
   ```

## Notes

- Item and effect data is loaded from JSON files in the `data/` directory, taken from https://github.com/PrismarineJS/minecraft-data/blob/master/data/pc/

## License

MIT
