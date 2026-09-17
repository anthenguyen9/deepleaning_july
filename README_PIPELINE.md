# FoodLens incremental research pipeline

Pipeline này tích lũy review SerpApi vào cùng SQLite của web, xử lý riêng dữ liệu mới
và lưu checkpoint để có thể tiếp tục sau khi hết quota hoặc đóng cửa sổ CMD.

## Nguyên tắc dữ liệu

- ViTASA là dataset gán nhãn để training/evaluation ABSA.
- Review SerpApi là dữ liệu ứng dụng để inference, trend, retrieval và recommendation.
- Dự đoán ABSA trên SerpApi không được dùng làm ground truth để tự đánh giá model.
- Chỉ ngày ISO thật từ nguồn được dùng cho thống kê tháng; ngày tương đối không được đoán.
- `monthly_trends` là baseline hồi cứu, không được gọi là BERTopic/BERTrend.
- `review_fts` là BM25 lexical retrieval, chưa phải dense/hybrid RAG.

## Chuẩn bị

Chạy `setup_web.bat`, nhập key và chạy `train_model.bat`. Các lệnh dưới đây dùng
`.venv\Scripts\python.exe` và database `instance\food_reviews.sqlite3`.

Kiểm tra trạng thái:

```bat
.venv\Scripts\python.exe data_pipeline.py status
```

## Thu thập theo từng khu vực

Thêm seed để ghi lại kế hoạch thu thập:

```bat
.venv\Scripts\python.exe data_pipeline.py seed --area "Hải Châu, Đà Nẵng" --cuisine "món Việt"
```

Tìm và upsert tối đa 20 nhà hàng:

```bat
.venv\Scripts\python.exe data_pipeline.py ingest-restaurants --area "Hải Châu, Đà Nẵng" --cuisine "món Việt" --limit 20
```

Chạy lần lượt các seed đang bật và tự dừng khi API báo hết ngân sách/hạn mức:

```bat
.venv\Scripts\python.exe data_pipeline.py ingest-seeds --max-seeds 5 --per-seed-limit 20 --daily-limit 25
```

Lấy review cho tối đa 20 nhà hàng, mỗi nhà hàng tối đa một trang trong lần chạy:

```bat
.venv\Scripts\python.exe data_pipeline.py ingest-reviews --max-restaurants 20 --pages 1
```

Nếu còn `next_page_token`, lần chạy sau tiếp tục từ checkpoint. Nhà hàng `complete`
không bị gọi lại, trừ khi chủ động refresh trang mới nhất:

```bat
.venv\Scripts\python.exe data_pipeline.py ingest-reviews --max-restaurants 20 --pages 1 --refresh
```

`--refresh` tiêu tốn quota và chỉ nên chạy theo lịch thu thập đã định. Cache 24 giờ
và `SERPAPI_DAILY_LIMIT` vẫn được áp dụng.

## Xử lý dữ liệu mới

Chỉ phân tích review chưa có kết quả cho phiên bản model hiện tại:

```bat
.venv\Scripts\python.exe data_pipeline.py analyze-pending --limit 1000
```

Tạo baseline thống kê rating và polarity theo tháng:

```bat
.venv\Scripts\python.exe data_pipeline.py compute-trends
```

Lệnh tạo `monthly_trends` và `trend_signals`, gồm thay đổi volume, rating,
sentiment index, moving average ba tháng và mức `insufficient/stable/weak/strong`.
Đây là công thức baseline cố định, không phải dự báo hoặc BERTrend.

Tạo lại chỉ mục SQLite FTS5/BM25:

```bat
.venv\Scripts\python.exe data_pipeline.py build-index
.venv\Scripts\python.exe data_pipeline.py search-index "món ngon phục vụ tốt" --limit 5
```

Đóng dấu một phiên bản dữ liệu để sử dụng trong thí nghiệm:

```bat
.venv\Scripts\python.exe data_pipeline.py snapshot --notes "Dataset trước thí nghiệm ABSA v1"
```

Xuất data card và báo cáo chất lượng:

```bat
.venv\Scripts\python.exe data_pipeline.py data-report
```

Đầu ra cục bộ gồm `outputs/data_card.json`, `outputs/data_card.md` và
`outputs/data_quality.csv`. Các file này được `.gitignore` để tránh vô tình công bố
thống kê của database cá nhân.

## Trình tự chạy khuyến nghị

```text
ingest-restaurants
  -> ingest-seeds (tùy chọn để chạy nhiều seed)
  -> ingest-reviews
  -> analyze-pending
  -> compute-trends
  -> build-index
  -> snapshot
  -> status
```

Mỗi job chính được ghi trong `pipeline_jobs` với tham số, thời gian, trạng thái,
thống kê và lỗi rút gọn. API key không được lưu trong bảng job, cache hoặc snapshot.

## Hoàn thiện nghiên cứu tiếp theo

Các bước sau chưa có trong phiên bản này và phải được đánh giá riêng trước khi claim:

1. PhoBERT multi-task ACD + SPC và so sánh với baseline.
2. BERTopic/BERTrend, temporal topic matching và event validation.
3. Dense embedding index, hybrid retrieval và reranker.
4. Citation validation, RAGAS và retrieval metrics.
5. Ablation A-E và user study cho taste profile.

Mẫu schema tạo relevance judgment nằm tại `evaluation_queries.example.json`. Người
đánh giá phải điền restaurant/review ID thủ công; không dùng output của model làm ground truth.
