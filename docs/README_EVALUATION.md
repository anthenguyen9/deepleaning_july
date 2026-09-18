# FoodLens retrieval evaluation

## Mục đích

Đánh giá retrieval độc lập với Gemini để trả lời một phần RQ3. Ground truth phải do
người đánh giá xác nhận, không sao chép từ kết quả BM25, Gemini hoặc ABSA.

## Chuẩn bị query set

Sao chép `evaluation_queries.example.json` thành `evaluation_queries.json`. Với mỗi query:

- `constraints`: ràng buộc khu vực, loại món, giá hoặc khía cạnh.
- `relevant_restaurant_ids`: nhà hàng được đánh giá là phù hợp.
- `relevant_review_ids`: review chứa bằng chứng trả lời query.
- `split`: dùng `dev` để tuning; giữ `test` cố định cho báo cáo cuối.

Query chưa có relevance ID bị bỏ qua khi tính metric và được tính trong
`queries_in_file`, không được tính vào `judged_queries`.

## Chạy đánh giá

```bat
.venv\Scripts\python.exe src/data_pipeline.py build-index
.venv\Scripts\python.exe src/research.py build-dense
.venv\Scripts\python.exe src/research.py evaluate-retrieval --queries evaluation_queries.json --split test --k 5
```

Output mặc định: `outputs/retrieval_comparison.json`, gồm BM25, dense E5 và
hybrid RRF trên cùng tập query được chấm độc lập. Nếu dense chưa sẵn sàng,
lệnh thất bại thay vì ghi kết quả BM25 thay cho dense.

## Chỉ số

- `Recall@k`: tỷ lệ evidence liên quan xuất hiện trong top-k.
- `MRR`: nghịch đảo hạng của kết quả liên quan đầu tiên.
- `nDCG@k`: chất lượng thứ tự top-k với relevance nhị phân.

Metrics được tính riêng ở cấp review và nhà hàng. BM25 thấp hơn trong SQLite được đổi
thành score cao hơn chỉ để hiển thị; thứ hạng vẫn theo `bm25()` của FTS5.

## Quy tắc thực nghiệm

- Chỉ tuning tokenizer/query expansion/weight trên dev.
- Không thay relevance judgment sau khi xem kết quả test.
- Ghi dataset snapshot và model version dùng để build index.
- Báo cáo số query được judgment, không chỉ báo cáo trung bình metric.
- So sánh BM25 với dense và hybrid trên cùng query set, dùng cùng snapshot.
