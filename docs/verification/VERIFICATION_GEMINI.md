# Xác minh FoodLens v0.3 — Gemini memory

Ngày kiểm tra: 2026-09-16 (UTC).

## Đã kiểm tra

- 19/19 test thành công.
- SQLite tạo/lưu/đọc/xóa `preference_memory`, `restaurant_feedback`,
  `chat_sessions` và `chat_messages`.
- Chat được phân tách theo lượt tìm kiếm và chỉ lấy 12 tin nhắn gần nhất để gửi model.
- Context nhà hàng giới hạn 5 ứng viên × 3 review rút gọn; không gửi toàn database.
- Request Gemini dùng endpoint cố định, key ở header, `store=false` và structured output.
- ID nhà hàng do model trả nhưng không thuộc tập ứng viên bị loại ở server.
- Tin nhắn, tên nhà hàng và nội dung review được Jinja escape khi render.
- Feedback thích/không thích được lưu và ảnh hưởng trực tiếp đến xếp hạng.
- Bộ nhớ học và chat có luồng xóa riêng; hồ sơ tự khai báo không bị xóa theo.
- Khi thiếu key hoặc Gemini lỗi, tìm kiếm/ABSA/xếp hạng quy tắc vẫn hoạt động.

## Chưa kiểm tra trực tiếp

- Chưa gọi Gemini API thật vì không có `GEMINI_API_KEY` trong môi trường bàn giao.
- Chưa chạy v0.3 trên Windows; BAT và fallback Python 3.11 kế thừa v0.2.
- Chưa có tập Google review gán nhãn để đo chất lượng khuyến nghị cá nhân hóa.
- Chưa đánh giá RAGAS/user study; chat hiện grounded trên snapshot kết quả SerpApi,
  chưa có vector database hoặc hybrid retriever.

## Quyết định model

Không dùng `gemini-1.5-flash` vì model này không còn trong danh sách hiện hành.
Mặc định dùng `gemini-2.5-flash`, có thể đổi bằng `GEMINI_MODEL` trong `.env`.

Nguồn đối chiếu:

- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/deprecations
- https://ai.google.dev/gemini-api/docs/structured-output
