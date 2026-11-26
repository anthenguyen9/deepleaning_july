# Xác minh FoodLens Web v0.2

Ngày kiểm tra: 2026-09-16 (UTC).

## Kết quả đã chạy

- 15/15 unit/integration test thành công trên Python 3.12.
- Kiểm tra cú pháp thành công cho `webapp.py`, `restaurant_service.py`,
  `storage.py` và `configure_key.py`.
- Waitress trả HTTP 200 cho trang chủ, trang kết quả thật và CSS.
- Flask test client xác nhận Host allowlist, CSRF, CSP, escaping nội dung nguồn,
  input validation, profile SQLite và lịch sử tìm kiếm.
- Fake API test xác nhận cache 24 giờ, review dedup, quota reservation, pagination
  tối đa, partial result, ngày ISO và không cache lỗi như kết quả thành công.
- Secret scan không tìm thấy SerpApi key người dùng trong thư mục bàn giao.

## Kiểm tra SerpApi thật

Đã chạy một lượt giới hạn cho **Hải Châu, Đà Nẵng**:

- 1 lượt Google Maps + 1 lượt Google Maps Reviews.
- Nhận 1 nhà hàng và 8 review ở trang đầu.
- Lưu thành công vào SQLite.
- SVM cục bộ tạo và lưu phân tích theo review.
- Chạy lại cùng truy vấn dùng 2 cache hit, không gọi thêm API.
- Trang kết quả từ dữ liệu thật render HTTP 200.

API key không được ghi vào báo cáo, database thử nghiệm hay ZIP. Database thật dùng
để kiểm tra cũng không nằm trong thư mục project.

## Phần chưa xác minh trực tiếp

- Chưa chạy trên Windows; BAT đã được viết cho Python 3.11 và có fallback khi
  `py` vẫn trỏ đến Python 3.13 đã gỡ.
- Chưa kiểm thử trực quan bằng trình duyệt tự động vì tải Chromium trong môi trường
  kiểm tra bị timeout. Template đã được render qua Flask và kiểm tra HTTP/XSS.
- Chưa đánh giá F1 của SVM trên Google Maps có gán nhãn. Điểm baseline ViTASA trong
  [`VERIFICATION.md`](VERIFICATION.md) không được coi là chất lượng trên dữ liệu Google Maps.
- Chưa có login nhiều người dùng, public deployment, LLM/RAG, RAGAS hoặc BERTrend.

## Nội dung ZIP

ZIP chứa source code, test, template/CSS, BAT, tài liệu, aggregate metrics và thông
tin giấy phép/nguồn ViTASA. ZIP không chứa `.env`, API key, database, raw review,
raw ViTASA, file dự đoán review hay model joblib. `train_model.bat` tải dữ liệu từ
nguồn cố định và tạo model trên máy người dùng.
