import hashlib, os

zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "LordNineBot_v3.23.9_update.zip")
with open(zip_path, "rb") as f:
    h = hashlib.sha256(f.read())
size = os.path.getsize(zip_path)
print(f"SIZE={size}")
print(f"SHA256={h.hexdigest()}")
