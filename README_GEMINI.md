# FoodLens v0.3 — Gemini chat memory

## Model

`gemini-1.5-flash` không còn là model hiện hành. Bản này mặc định dùng
`gemini-2.5-flash`, model ổn định và chưa có lịch tắt được công bố tại thời điểm
2026-09-16. Có thể đổi `GEMINI_MODEL` trong `.env` khi Google thay vòng đời model.

Tài liệu chính thức:

- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/deprecations
- https://ai.google.dev/gemini-api/docs/structured-output

## Cấu hình

Chạy lại `configure_key.py` bằng Python trong `.venv`, hoặc chạy `setup_web.bat`.
Script giữ key hiện tại nếu nhấn Enter.

```bat
.venv\Scripts\python.exe configure_key.py
```

`.env` cục bộ:

```text
SERPAPI_API_KEY=...
SERPAPI_DAILY_LIMIT=30
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
```

Không đưa `.env` lên Git hoặc gửi kèm báo cáo. Key chỉ được gửi trong header
`x-goog-api-key` đến endpoint Gemini cố định, không lưu trong SQLite/HTML/chat.

## Context và cá nhân hóa

- `preference_memory`: sở thích tự khai báo và bản tóm tắt Gemini đã học.
- `restaurant_feedback`: quán thích/không hợp; dùng trực tiếp trong xếp hạng.
- `chat_sessions`, `chat_messages`: context chat cục bộ theo từng lượt tìm kiếm.
- Mỗi request chỉ gửi tối đa 12 tin nhắn gần nhất, 5 nhà hàng, 3 review rút gọn
  mỗi nhà hàng, hồ sơ và tối đa 20 phản hồi quán.
- Câu hỏi được truy xuất bằng SQLite FTS5/BM25, lọc trong các nhà hàng của lượt tìm.
  Tối đa 12 hit được gom theo nhà hàng trước khi tạo context Gemini.
- Gemini nhận `store=false`; nguồn dữ liệu lâu dài của ứng dụng là SQLite local.
- Structured output buộc trả `reply`, `learned_preferences` và danh sách ID gợi ý.
  ID ngoài tập ứng viên bị loại ở phía server.
- Mỗi review gửi model có mã `R1`, `R2`...; citation ngoài context bị loại. Nếu model
  đề xuất quán nhưng không có citation hợp lệ, server loại tín hiệu đề xuất đó.
- Khi không có review có nội dung, policy trả lời từ chối ngay mà không gọi Gemini.
- Xếp hạng cuối vẫn có thành phần kiểm chứng được: phản hồi like/dislike, khía cạnh
  ưu tiên, điểm Google, số review và từ khóa khẩu vị. Gemini tạo giải thích và
  thêm tín hiệu ID gợi ý, không tự tạo dữ liệu nhà hàng.
- Người dùng có nút xóa chat theo lượt tìm và xóa toàn bộ bộ nhớ học tự động.
- `retrieval_events` ghi method, số kết quả và latency; không ghi API key.

Không tự suy đoán dị ứng, sức khỏe, tôn giáo, thu nhập hoặc thuộc tính nhạy cảm.
Các hạn chế ăn uống chỉ được ghi nhận khi người dùng chủ động nhập/nói rõ.
