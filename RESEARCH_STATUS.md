# Trạng thái thực nghiệm FoodLens

Đề cương gốc do học viên cung cấp: Thạc sĩ Kỹ thuật Phần mềm, Nguyễn Thế An, GVHD Nguyễn Gia Trí. Tài liệu MBA trên Drive là một bản khác và không dùng làm chuẩn cho mã nguồn.

Các kết quả nghiên cứu chỉ được ghi sau khi có dữ liệu nguồn và kiểm chứng độc lập.

Snapshot `serpapi-20260917T071815Z` trong SQLite cục bộ có 28 nhà hàng và
4.821 review có ngày nguồn, trải trên 843 ngày, 65 tháng và 9 năm. Có 3.580
review có nội dung đã được baseline ABSA phân tích và lập chỉ mục BM25. Bảng
`period_aggregates` chứa tổng hợp theo ngày/tháng/năm, CSV trong `outputs/`.
Đây là mẫu crawl để kiểm tra hệ thống, chưa phải tập đánh giá đại diện.
Key SerpApi mới đã dùng 238/250 lượt; 12 lượt còn lại giữ cho demo trực tiếp.
Database và khóa API không đẩy lên Git.
Gemini `gemini-3.6-flash` đã được gọi thật trên một review fixture và trả lời
có trích dẫn hợp lệ; đây là kiểm tra tích hợp, không phải đánh giá faithfulness.
BERTopic hồi cứu đã chạy trên 3.580 review có nội dung: 21 tháng đạt ngưỡng
30 review/tháng, tạo 10 topic và 146 dòng topic-tháng. Topic chưa được chuyên
gia kiểm tra về độ mạch lạc; đây không phải BERTrend online learning hay dự báo.

## Đã triển khai trong code

- SerpApi → SQLite, checkpoint, cache, phiên bản dataset, data card.
- Baseline ViTASA TF-IDF + SVM. `train_phobert_multitask.py` chứa hai nhánh ACD và SPC; chỉ gọi là kết quả PhoBERT sau khi huấn luyện và lưu metrics thật.
- Tổng hợp review và cảm xúc theo ngày/tháng/năm từ ngày ISO nguồn; tín hiệu thay đổi theo tháng có điều kiện tối thiểu. `topic_trends.py` chỉ chạy BERTopic khi đủ tháng; chưa triển khai BERTrend online learning.
- BM25, embedding E5 và hybrid RRF; SQLite lưu vector, hash của văn bản và ID model. `research.py evaluate-retrieval` so sánh ba cấu hình trên cùng judgments.
- Gemini RAG chỉ nhận review được truy xuất, kiểm tra citation thuộc đúng quán, từ chối nếu thiếu căn cứ.
- Recommendation A–E; bộ xuất review để gán nhãn, tách tập theo nhà hàng, agreement và tổng hợp khảo sát.

## Chưa thể tuyên bố hoàn thành thực nghiệm

- Chưa có gold label riêng cho Google Maps, relevance judgments độc lập, đánh giá claim RAGAS hoặc người tham gia user study.
- Chưa có kết quả huấn luyện PhoBERT multi-task, BERTrend online learning hoặc so sánh hybrid trên tập gold. Kết quả BERTopic mới là phân tích khám phá, chưa có nhãn đánh giá topic.
- Các ngưỡng F1, faithfulness, hallucination và satisfaction trong đề cương là **mục tiêu**, không phải kết quả.

## Lệnh chạy trên Windows

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements_research.txt
.\.venv\Scripts\python.exe pipeline.py download
.\.venv\Scripts\python.exe pipeline.py prepare
.\.venv\Scripts\python.exe pipeline.py train
.\.venv\Scripts\python.exe data_pipeline.py ingest-restaurants --area "Hải Châu, Đà Nẵng" --limit 3
.\.venv\Scripts\python.exe data_pipeline.py ingest-reviews --max-restaurants 3 --pages 2
.\.venv\Scripts\python.exe data_pipeline.py analyze-pending
.\.venv\Scripts\python.exe data_pipeline.py build-index
.\.venv\Scripts\python.exe research.py build-dense
.\.venv\Scripts\python.exe research.py annotation-template --output data/annotation.json
.\.venv\Scripts\python.exe research.py prepare-gold --input data/annotation.json --output data/gold
.\.venv\Scripts\python.exe research.py evaluate-retrieval --queries data/relevance.json --split test
.\.venv\Scripts\python.exe train_phobert_multitask.py --data-dir data
.\.venv\Scripts\python.exe -m pip install -r requirements_topics.txt
.\.venv\Scripts\python.exe topic_trends.py
.\.venv\Scripts\python.exe webapp.py
```

Khóa API chỉ đặt trong `.env`; dữ liệu gán nhãn và phiếu khảo sát cần người thật kiểm tra và đồng ý tham gia.
