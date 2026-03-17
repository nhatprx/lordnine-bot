# LordNine Bot — Release Guide

Hướng dẫn đầy đủ cho developer khi release phiên bản mới.

---

## Yêu cầu

- **Python** (đã cài dependencies)
- **npx vercel** (Vercel CLI qua npx)
- **git** (push access tới repo)
- **GitHub token** (lưu trong git credential store — `git push` phải hoạt động)

---

## Quy trình Release (5 bước)

### Bước 1: Cập nhật version

Sửa **duy nhất 1 file** — `version.py`:

```python
APP_VERSION = "3.20.0"  # Đổi version ở đây
```

> ⚠️ **KHÔNG** hardcode version ở file khác. Tất cả đều import từ `version.py`.

---

### Bước 2: Build exe + update.zip

```bash
python build_exe.py
```

Kết quả:
- `dist/LordNineBot/LordNineBot.exe` — App chạy trực tiếp
- `dist/LordNineBot_v{version}_update.zip` — File update cho auto-update
- Console in ra **SHA256 hash** và **file size** — **lưu lại!**

> 💡 Test thử `dist/LordNineBot/LordNineBot.exe` trước khi release.

---

### Bước 3: Commit + Push + Tạo GitHub Release

```bash
# Commit changes
git add .
git commit -m "v3.20.0: <mô tả changes>"
git push origin master
```

**Tạo GitHub Release** (cần script vì repo là **private**):

```python
# Chạy script tạo release + upload zip tự động:
python _create_release.py
```

Hoặc tạo thủ công:
1. Vào https://github.com/nhatpse/lordnine-bot/releases/new
2. Tag: `v3.20.0`
3. Upload: `dist/LordNineBot_v3.20.0_update.zip`
4. Publish

> ⚠️ **Repo là PRIVATE** — client không thể download trực tiếp từ GitHub URL.
> Download đi qua Vercel proxy `/api/download` (dùng `GITHUB_TOKEN`).

---

### Bước 4: Update Vercel env vars

Cần cập nhật 5 env vars trên Vercel project `lordnine-update`:

```powershell
# Xóa env cũ và thêm mới (PowerShell)
npx vercel env rm LATEST_VERSION production -y
npx vercel env rm UPDATE_SIZE production -y
npx vercel env rm UPDATE_SHA256 production -y
npx vercel env rm DOWNLOAD_URL production -y
npx vercel env rm CHANGELOG production -y
```

Sau đó thêm giá trị mới — **QUAN TRỌNG: dùng pipe để tránh trailing newline**:

```powershell
# Thay giá trị phù hợp:
echo 3.20.0| npx vercel env add LATEST_VERSION production
echo 72368112| npx vercel env add UPDATE_SIZE production
echo abc123def456...| npx vercel env add UPDATE_SHA256 production
echo https://github.com/nhatpse/lordnine-bot/releases/download/v3.20.0/LordNineBot_v3.20.0_update.zip| npx vercel env add DOWNLOAD_URL production
echo Fix bugs va improvements| npx vercel env add CHANGELOG production
```

> ⚠️ **Không có khoảng trắng giữa giá trị và `|`** — tránh trailing newline.
> API đã có `.strip()` để tự clean, nhưng tốt nhất vẫn pipe sạch.

| Variable | Ví dụ | Nguồn |
|----------|-------|-------|
| `LATEST_VERSION` | `3.20.0` | `version.py` |
| `UPDATE_SIZE` | `72368112` | Console output từ `build_exe.py` |
| `UPDATE_SHA256` | `c4c3307d67a5...` | Console output từ `build_exe.py` |
| `DOWNLOAD_URL` | `https://github.com/nhatpse/lordnine-bot/releases/download/v3.20.0/LordNineBot_v3.20.0_update.zip` | GitHub Release URL |
| `CHANGELOG` | `Fix lag 20 accounts` | Tự viết |

---

### Bước 5: Redeploy Vercel

```bash
npx vercel --prod
```

---

### Bước 6: Xác nhận

Mở app cũ → Tab **Output** → **⬇ Check Update** → Phải hiện popup update + download thành công.

---

## Kiến trúc hệ thống Update

```
version.py              ← Single source of truth cho version
build_exe.py            ← Build script: tạo exe + update.zip + SHA256
updater.py              ← Client-side: check, download, apply update

api/check-update.py     ← Vercel API: trả version + proxy download URL
api/download.py         ← Vercel API: proxy download từ private GitHub repo
api/validate-license.py ← Vercel API: validate license key + HWID
```

### Flow khi client update

```
App mở → User nhấn "Check Update"
  → GET /api/check-update?v=3.19.9
  → Server trả: {latest: "3.20.0", download_url: "/api/download", sha256: "..."}
  → Client gọi GET /api/download
  → Vercel dùng GITHUB_TOKEN lấy temp S3 URL từ GitHub API
  → Client download zip từ S3 URL (không cần auth)
  → Verify SHA-256 → Extract → Swap files → Restart app
```

> 💡 **Tại sao cần proxy?** Vì repo là **private**, direct GitHub release URLs trả 404.
> Proxy `/api/download` dùng `GITHUB_TOKEN` (Vercel env var) để lấy temporary S3 link.

---

## Troubleshooting

| Vấn đề | Nguyên nhân | Fix |
|--------|-------------|-----|
| Download 404 | Repo private + direct URL | Kiểm tra `GITHUB_TOKEN` env var trên Vercel |
| SHA-256 mismatch | Build lại hoặc sai hash | Chạy lại `build_exe.py`, copy hash mới |
| Update not showing | Version env chưa update | Kiểm tra `LATEST_VERSION` trên Vercel |
| "Not configured" | Env vars trống | Kiểm tra tất cả 5 env vars trên Vercel |
| Trailing newline in env | PowerShell `echo` | API đã có `.strip()`, hoặc pipe không space: `echo value\| npx vercel env add` |

## Lưu ý quan trọng

- **Luôn test build** trước khi upload: chạy `dist/LordNineBot/LordNineBot.exe`
- **SHA-256 là bắt buộc** — nếu hash sai, client từ chối update
- **GITHUB_TOKEN** trên Vercel phải có quyền đọc releases của repo
- **Không xóa user data** khi update — xem `preserve_files` trong `updater.py`
- Nếu thêm file data mới cần preserve, cập nhật list trong `updater.py`
