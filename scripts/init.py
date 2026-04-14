"""Initialize the linkedin-auto-poster workspace."""
import os
import shutil

dirs = ["data", "drafts"]
for d in dirs:
    os.makedirs(d, exist_ok=True)

files = {
    "config.example.yaml": "config.yaml",
    ".env.example": ".env",
    "content-topics.example.yaml": "content-topics.yaml",
}
for src, dst in files.items():
    if not os.path.exists(dst) and os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"Created {dst} from {src}")
    elif os.path.exists(dst):
        print(f"Skipped {dst} (already exists)")

print("\nWorkspace initialized! Edit config.yaml and .env with your settings.")
