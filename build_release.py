import zipfile
import shutil
from pathlib import Path
import datetime

# Paths
project_root = Path(__file__).parent
dist_dir = project_root / "dist"
build_dir = project_root / "dadmin-dist"
data_dir = project_root / "data"
output_name = f"dadmin-v{datetime.datetime.now().strftime('%Y%m%d')}.zip"
output_zip = project_root / output_name

# Clean build dir
if build_dir.exists():
    shutil.rmtree(build_dir)
build_dir.mkdir()

# Ensure data dir exists
if not data_dir.exists():
    data_dir.mkdir(parents=True)
    (data_dir / "items.json").write_text("[]")
    (data_dir / "effects.json").write_text("[]")

# Ensure example config exists
config_path = project_root / "server_config.txt"
if not config_path.exists():
    config_path.write_text("host=localhost\nport=25575\npassword=changeme")

# Ensure README exists
readme_path = project_root / "README.md"
if not readme_path.exists():
    readme_path.write_text("# dadmin\n\nMinecraft RCON admin GUI.")

# Copy essentials
shutil.copy(dist_dir / "dadmin.exe", build_dir / "dadmin.exe")
shutil.copy(config_path, build_dir / "server_config-example.txt")
shutil.copy(readme_path, build_dir / "README.md")
shutil.copytree(data_dir, build_dir / "data")

# Optional icon handling
icon_path = project_root / "icon.ico"
if icon_path.exists():
    shutil.copy(icon_path, build_dir / "icon.ico")

# Zip it
with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
    for path in build_dir.rglob("*"):
        zipf.write(path, path.relative_to(build_dir.parent))

print(f"✅ Created {output_zip}")
