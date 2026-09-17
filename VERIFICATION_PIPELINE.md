# Xác minh incremental pipeline

Ngày kiểm tra: 2026-09-17 UTC.

## Đã kiểm tra tự động

- Upsert nhà hàng mới và cập nhật nhà hàng đã tồn tại.
- Hỗ trợ cả định danh `data_id` và `place_id` khi lấy review.
- Lưu `next_page_token`, tiếp tục đúng trang ở lần chạy sau và chuyển trạng thái complete.
- Deduplicate review theo `(restaurant_id, review_id)`.
- Chỉ chạy ABSA cho review chưa có kết quả của `model_version` hiện tại.
- Tạo baseline rating/polarity theo tháng chỉ từ timestamp ISO thật.
- Tạo và truy vấn chỉ mục SQLite FTS5/BM25.
- Tạo dataset snapshot với số nhà hàng, review và khoảng ngày.
- Báo cáo coverage, pending ABSA, crawl state và lịch sử job.
- Toàn bộ test của project: 21/21 thành công.

## Chưa kiểm tra trực tiếp

- Chưa chạy batch pipeline mới bằng SerpApi thật để tránh sử dụng quota/key của người dùng.
- Chưa kiểm tra lịch chạy dài ngày trên Windows Task Scheduler.
- Chưa benchmark SQLite khi vượt mục tiêu 10.000 review.
- Chưa triển khai BERTopic/BERTrend, dense index hoặc hybrid retrieval.

Các test SerpApi sử dụng transport giả lập và không tiêu tốn quota.
