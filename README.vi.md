> Bản dịch tiếng Việt từ [README.md](README.md). Không sửa trực tiếp — sửa bản tiếng Anh rồi tạo lại.

# vunm-youtube-mcp

Model Context Protocol (MCP) server cá nhân bằng Python (dùng `fastmcp`), kết nối an toàn với tài khoản YouTube của chính bạn qua **Google Cloud OAuth 2.0**.

Server này giải quyết bài toán: trao quyền cho trợ lý AI (Antigravity, Claude Desktop, Cursor, Cline...) tự động **phân tích chỉ số kênh**, **quản lý và cập nhật thông tin video (SEO)**, **trích xuất phụ đề (transcript)** và **đọc bình luận** mà không phụ thuộc vào các repo trôi nổi của bên thứ ba.

---

## 1. Tính Năng & Danh Sách Công Cụ (Tools)

| Tên Tool | Nhóm chức năng | Mô tả chi tiết |
| :--- | :--- | :--- |
| `youtube_channel_stats` | Thống kê kênh | Xem tổng quan kênh (Subscribers, Views, Video count, custom URL). |
| `youtube_analytics_report` | Phân tích sâu | Truy vấn YouTube Analytics API theo khoảng ngày: Watch time, Retention, Lượt xem, Tăng/giảm sub. |
| `youtube_video_analytics` | Phân tích video | Xem chi tiết retention, watch time, shares cho từng video cụ thể. |
| `youtube_list_videos` | Quản lý video | Liệt kê danh sách video mới đăng (gồm cả Public, Unlisted, Private) với mức tốn quota siêu tiết kiệm (1 unit). |
| `youtube_get_video` | Chi tiết video | Đọc trọn bộ metadata (Title, Description, Tags, Category, Privacy). |
| `youtube_update_video` | Chỉnh sửa video | Cập nhật Tiêu đề, Mô tả, Thẻ từ khóa (Tags), Chế độ hiển thị trên YouTube Studio. |
| `youtube_get_transcript` | Phụ đề & Nội dung | Trích xuất phụ đề (tiếng Việt/Anh) có timestamp để AI tóm tắt nội dung mà không tốn quota API. |
| `youtube_get_comments` | Tương tác | Đọc danh sách bình luận mới nhất của video để phân loại cảm xúc/soạn câu trả lời. |

---

## 2. Chuẩn Bị Thông Tin Đăng Nhập (Google Cloud OAuth)

Vì đây là ứng dụng chạy local trên máy của bạn, bạn cần tạo OAuth Client ID từ chính Google Cloud Console của mình:

### Bước 2.1: Bật API
1. Truy cập [Google Cloud Console](https://console.cloud.google.com/).
2. Tạo một Project mới (ví dụ: `vunm-youtube-tools`).
3. Vào mục **APIs & Services $\rightarrow$ Library**, tìm và bấm **Enable** cho 2 API sau:
   - **YouTube Data API v3**
   - **YouTube Analytics API**

### Bước 2.2: Cấu hình Màn hình chấp thuận (OAuth Consent Screen)
1. Vào **APIs & Services $\rightarrow$ OAuth consent screen**.
2. Chọn loại **External** rồi bấm **Create**.
3. Điền tên ứng dụng (ví dụ: `vunm-youtube-mcp`) và email liên hệ của bạn.
4. Ở bước **Scopes**: Bạn có thể bỏ qua hoặc thêm `.../auth/youtube` và `.../auth/yt-analytics.readonly`.
5. Ở bước **Test users** (Rất quan trọng): Bấm **Add Users** và nhập chính địa chỉ Gmail sở hữu kênh YouTube của bạn.
6. Lưu lại.

### Bước 2.3: Tạo Credentials
1. Vào **APIs & Services $\rightarrow$ Credentials**.
2. Bấm **Create Credentials $\rightarrow$ OAuth client ID**.
3. Chọn Application type: **Desktop app**.
4. Đặt tên (ví dụ: `vunm-youtube-mcp-client`) rồi bấm **Create**.
5. Bấm nút **Download JSON** để tải file về máy.
6. Đổi tên file tải về thành `client_secret.json` và lưu vào thư mục:
   ```
   vunm-youtube-mcp/credentials/client_secret.json
   ```
   *(Thư mục `credentials/` đã được cấu hình trong `.gitignore` để không bao giờ bị commit lên Git).*

---

## 3. Cài Đặt & Xác Thực Lần Đầu

### Bước 3.1: Tạo môi trường ảo & Cài dependencies
Mở Terminal tại thư mục `vunm-youtube-mcp`:
```bash
cd /path/to/vunm-youtube-mcp

# Tạo môi trường ảo Python (khuyên dùng Python 3.10+)
python3 -m venv .venv

# Kích hoạt môi trường và cài đặt
source .venv/bin/activate
pip install -r requirements.txt
```

### Bước 3.2: Xác thực tài khoản (Chỉ cần làm 1 lần)
Chạy script kiểm tra và cấp quyền:
```bash
python authenticate.py
```
- Trình duyệt web sẽ tự động mở trang đăng nhập Google.
- Chọn tài khoản Google sở hữu kênh YouTube của bạn.
- Khi thấy cảnh báo *"Google hasn't verified this app"*, bấm **Advanced $\rightarrow$ Go to vunm-youtube-mcp (unsafe)** (vì đây là app do chính bạn tạo).
- Bấm **Continue / Cho phép** tất cả các quyền.
- Terminal sẽ thông báo: `[✓] Successfully connected to channel: '...'` và tự động lưu `token.json` để sử dụng mãi về sau (tự refresh token khi hết hạn).

---

## 4. Tích Hợp Vào AI Client

### Cho Antigravity (Gemini CLI / Antigravity IDE)
Mở file `~/.gemini/config/mcp_config.json` và thêm cấu hình sau:
```json
{
  "mcpServers": {
    "vunm-youtube-mcp": {
      "command": "/absolute/path/to/vunm-youtube-mcp/.venv/bin/python",
      "args": [
        "-m",
        "src.server"
      ],
      "cwd": "/absolute/path/to/vunm-youtube-mcp"
    }
  }
}
```

### Cho Claude Desktop
Mở file `~/Library/Application Support/Claude/claude_desktop_config.json` và thêm vào `mcpServers`:
```json
{
  "mcpServers": {
    "vunm-youtube-mcp": {
      "command": "/absolute/path/to/vunm-youtube-mcp/.venv/bin/python",
      "args": [
        "-m",
        "src.server"
      ],
      "cwd": "/absolute/path/to/vunm-youtube-mcp"
    }
  }
}
```

---

## 5. Giấy Phép (License)

Dự án được phân phối dưới giấy phép [MIT License](LICENSE).
