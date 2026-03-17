# LordNine Bot — Release & Update Guide

Hướng dẫn cho developer khi release phiên bản mới.

---

## Quy trình release bản mới

### Bước 1: Cập nhật version

Sửa **duy nhất 1 file** — `version.py`:

```python
APP_VERSION = "3.16.0"  # Đổi version ở đây
```

> ⚠️ **KHÔNG** hardcode version ở bất kỳ file nào khác. Tất cả đều import từ `version.py`.

---

### Bước 2: Build exe + update.zip

```bash
python build_exe.py
```

Kết quả:
- `dist/LordNineBot/LordNineBot.exe` — App chạy trực tiếp
- `dist/LordNineBot_v{version}_update.zip` — File update cho auto-update
- Console in ra **SHA256 hash** và **file size** — lưu lại!

---

### Bước 3: Build installer (nếu cần gửi bản cài mới)

```bash
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

> Nhớ cập nhật version trong `installer.iss` (dòng `AppVersion=` và `OutputBaseFilename=`).

Kết quả: `installer_output/LordNineBotSetup_v{version}.exe`

---

### Bước 4: Upload lên GitHub Releases

1. Vào GitHub repo → **Releases** → **Draft a new release**
2. Tag: `v3.16.0`
3. Upload file: `dist/LordNineBot_v3.16.0_update.zip`
4. Viết changelog

---

### Bước 5: Cập nhật Vercel env vars

Vào [Vercel Dashboard](https://vercel.com) → Project → **Settings** → **Environment Variables**

Cập nhật các biến sau:

| Variable | Giá trị | Ví dụ |
|----------|---------|-------|
| `LATEST_VERSION` | Version mới | `3.16.0` |
| `DOWNLOAD_URL` | URL file zip trên GitHub Releases | `https://github.com/<user>/<repo>/releases/download/v3.16.0/LordNineBot_v3.16.0_update.zip` |
| `UPDATE_SIZE` | Kích thước file zip (bytes) | `72307986` |
| `UPDATE_SHA256` | SHA-256 hash (từ console build) | `662fcb84b7ab...` |
| `CHANGELOG` | Nội dung changelog (dùng `\n` cho xuống dòng) | `• Fix bugs\n• New feature` |

Sau đó **redeploy**:

```bash
vercel --prod
```

---

### Bước 6: Xác nhận

Mở app → Tab **Output** → Nhấn **⬇ Check Update** → Phải hiện popup update.

---

## Cấu trúc hệ thống update

```
version.py          ← Single source of truth cho version
updater.py          ← Client-side: check, download, apply update
api/check-update.py ← Vercel API: trả version mới nhất cho client
build_exe.py        ← Build script: tạo exe + update.zip + SHA256
installer.iss       ← Inno Setup: tạo installer .exe
```

## Flow khi khách hàng update

```
App mở → User nhấn "Check Update"
    → Gọi GET /api/check-update?v=3.15.6
    → Server trả: {latest: "3.16.0", download_url: "...", sha256: "..."}
    → Hiện popup changelog + nút "Update Now"
    → Download zip + verify SHA-256
    → Extract + tạo script swap
    → App tắt → swap files → App mở lại
    → User data (config, trackers, macros, loops, license) được giữ nguyên
```

## Lưu ý quan trọng

- **Luôn test build** trước khi release: chạy `dist/LordNineBot/LordNineBot.exe` trực tiếp
- **Không xóa user data** khi update — xem danh sách preserve trong `updater.py`
- **Nếu thêm file data mới** cần preserve, cập nhật list trong `updater.py` → `USER_DATA` và `preserve_files`
- **SHA-256 là bắt buộc** — nếu hash sai, client sẽ từ chối bản update
- **Version format**: `MAJOR.MINOR.PATCH` (ví dụ: `3.16.0`)
