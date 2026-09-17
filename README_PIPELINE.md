# FoodLens incremental research pipeline

Pipeline này tích lũy review SerpApi vào cùng SQLite của web, xử lý riêng dữ liệu mới
và lưu checkpoint để có thể tiếp tục sau khi hết quota hoặc đóng cửa sổ CMD.

## Nguyên tắc dữ liệu

- ViTASA là dataset gán nhãn để training/evaluation ABSA.
- Review SerpApi là dữ liệu ứng dụng để inference, trend, retrieval và recommendation.
- Dự đoán ABSA trên SerpApi không được dùng làm ground truth để tự đánh giá model.
- Chỉ ngày ISO thật từ nguồn được dùng cho thống kê tháng; ngày tương đối không được đoán.
- `monthly_trends` là baseline hồi cứu, không được gọi là BERTopic/BERTrend.
- `review_fts` là BM25; chỉ mục E5 riêng và hybrid RRF chạy sau `research.py build-dense`.

## Chuẩn bị

Chạy `setup_web.bat`, nhập key và chạy `train_model.bat`. Các lệnh dưới đây dùng
`.venv\Scripts\python.exe` và database `instance\food_reviews.sqlite3`.

Kiểm tra trạng thái:

```bat
.venv\Scripts\python.exe data_pipeline.py status
.venv\Scripts\python.exe research.py serp-quota
```

`serp-quota` đọc Account API miễn phí của SerpApi và chỉ in số lượt dùng/còn
lại, không in khóa. Giữ một phần lượt còn lại cho demo trực tiếp; cache và
database cục bộ cho phép demo dữ liệu đã thu mà không gọi API mới.

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

Lệnh tạo `period_aggregates` theo **ngày, tháng, năm** từ ngày ISO do nguồn cung
cấp; không suy đoán ngày từ mô tả tương đối. Bảng `monthly_trends` và
`trend_signals` thêm thay đổi volume, rating, sentiment index, moving average
ba tháng và mức `insufficient/stable/weak/strong`. Đây là công thức baseline
cố định, không phải dự báo hoặc BERTrend.

Tạo lại chỉ mục SQLite FTS5/BM25:

```bat
.venv\Scripts\python.exe data_pipeline.py build-index
.venv\Scripts\python.exe data_pipeline.py search-index "món ngon phục vụ tốt" --limit 5
```

Sau `build-index`, chạy `.venv\Scripts\python.exe research.py build-dense` để tạo
vector E5. Luồng chat dùng hybrid RRF trong danh sách nhà hàng của lượt tìm;
nếu chỉ mục dense thiếu hoặc cũ, nó ghi lý do và dùng BM25. Khi không tìm được
review phù hợp, chatbot từ chối gợi ý thay vì dùng review không được truy xuất.
Đặt `AUTO_BUILD_DENSE=1` trong `.env` để web cập nhật vector tự động sau mỗi
lượt tìm kiếm mới; cần cài `requirements_research.txt` và tải model embedding.

Đóng dấu một phiên bản dữ liệu để sử dụng trong thí nghiệm:

```bat
.venv\Scripts\python.exe data_pipeline.py snapshot --notes "Dataset trước thí nghiệm ABSA v1"
```

Xuất data card và báo cáo chất lượng:

```bat
.venv\Scripts\python.exe data_pipeline.py data-report
```

Đầu ra cục bộ gồm `outputs/data_card.json`, `outputs/data_card.md`,
`outputs/data_quality.csv` và `outputs/temporal_aggregates.csv` (một dòng cho
mỗi nhà hàng, khía cạnh, ngày/tháng/năm). Các file này được `.gitignore` để
tránh vô tình công bố thống kê của database cá nhân.

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

## Thực nghiệm cần dữ liệu đánh giá

Code hai đầu PhoBERT ACD+SPC, BERTopic hồi cứu, BM25/dense/hybrid,
kiểm tra trích dẫn và tổng hợp khảo sát đã có. Kết quả thực nghiệm chỉ được
công bố sau khi chạy model, gán nhãn gold, đánh giá relevance/claim và khảo sát
người dùng. BERTrend online learning, reranker và RAGAS chưa được tích hợp.
Xem [RESEARCH_STATUS.md](RESEARCH_STATUS.md) để phân biệt code và kết quả thật.

Mẫu schema tạo relevance judgment nằm tại `evaluation_queries.example.json`. Người
đánh giá phải điền restaurant/review ID thủ công; không dùng output của model làm ground truth.

Sau khi điền relevance judgment, chạy:

```bat
.venv\Scripts\python.exe data_pipeline.py evaluate-retrieval --queries evaluation_queries.json --k 5
.venv\Scripts\python.exe research.py evaluate-retrieval --queries evaluation_queries.json --split test
```

Kết quả `Recall@k`, `MRR` và `nDCG@k` ở cấp review/nhà hàng được lưu cục bộ tại
`outputs/retrieval_metrics.json`. Xem `README_EVALUATION.md`.
