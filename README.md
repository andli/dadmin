# dadmin — A Minecraft RCON Admin app for all operating systems

A minimalist desktop app for administering a local Minecraft server via RCON. Helping you, the (d)admin, play survival mode with your kids without having to type `/give` all the bloody time. 😅

Right now the app supports giving _items_ (with _enchantments_) and applying _effects_.

The app is designed for localhost use and single-server setups.

**NB** the _dad_ can of course also be a mom. 👩‍💻 The pun is less effective that way though.

![Screenshot](screenshot.png "Screenshot")

## Features

- 🎮 Player selector with auto-refresh
- 🔍 Fuzzy search for items, effects and item enchantments
- 🧪 Give items or apply effects
- 🧭 Teleport players to other players or saved locations
- ⭐ Give XP levels or points

## Requirements

- A Minecraft server with RCON enabled (found in `server.properties`)
- `server_config.txt` with:

### Config

```
host=localhost
port=25575
password=<your pw>
```

## Optional Teleport Locations

Add custom destinations to the teleport dropdown by adding lines like the following to `server_config.txt`:

```
location_main_spawn=0 64 0
location_village=150 70 -45
```

Use the pattern `location_<name>=x y z`. Names are converted to readable labels automatically (for example `location_village_square` → `Village Square`). Coordinates can be separated by spaces or commas.

## Notes

- Item and effect data is loaded from JSON files in the `data/` directory, taken from https://github.com/PrismarineJS/minecraft-data/blob/master/data/pc/
- If you are missing items due to a Minecraft update, just replace the corresponding `/data` files or open an issue in this repo.
