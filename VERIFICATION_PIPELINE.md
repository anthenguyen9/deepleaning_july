# Xác minh incremental pipeline

Ngày kiểm tra: 2026-09-17 UTC.

## Đã kiểm tra tự động

- Upsert nhà hàng mới và cập nhật nhà hàng đã tồn tại.
- Hỗ trợ cả định danh `data_id` và `place_id` khi lấy review.
- Lưu `next_page_token`, tiếp tục đúng trang ở lần chạy sau và chuyển trạng thái complete.
- Deduplicate review theo `(restaurant_id, review_id)`.
- Chỉ chạy ABSA cho review chưa có kết quả của `model_version` hiện tại.
- Tạo baseline rating/polarity theo tháng chỉ từ timestamp ISO thật.
- Tạo moving average, volume/rating change, sentiment shift, trend score và cờ đủ mẫu.
- Chạy nhiều ingestion seed theo thứ tự seed cũ nhất và dừng khi API báo lỗi/hết hạn mức.
- Xuất data card JSON/Markdown và data-quality CSV cục bộ.
- Tạo và truy vấn chỉ mục SQLite FTS5/BM25.
- Chat truy xuất BM25 trong candidate restaurant set và lưu method/result count/latency.
- Evaluator tính Recall@k, MRR và nDCG@k riêng ở cấp review và nhà hàng.
- Tạo dataset snapshot với số nhà hàng, review và khoảng ngày.
- Báo cáo coverage, pending ABSA, crawl state và lịch sử job.
- Gemini citation ngoài context bị loại; đề xuất không citation không được áp dụng.
- Policy từ chối trước khi gọi Gemini nếu không có review có nội dung.
- Toàn bộ test của project: 26/26 thành công.

## Chưa kiểm tra trực tiếp

- Chưa chạy batch pipeline mới bằng SerpApi thật để tránh sử dụng quota/key của người dùng.
- Chưa kiểm tra lịch chạy dài ngày trên Windows Task Scheduler.
- Chưa benchmark SQLite khi vượt mục tiêu 10.000 review.
- Chưa triển khai BERTopic/BERTrend, dense index hoặc hybrid retrieval.

Các test SerpApi sử dụng transport giả lập và không tiêu tốn quota.
