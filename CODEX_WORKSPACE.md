# Codex workspace

Branch này dành cho việc hoàn thiện đồ án của Nguyễn Thế An (24MSE33019).

## Trạng thái hiện tại

- Flask web + SQLite
- SerpApi ingestion, cache và quota guard
- Gemini RAG với chat context, citation và abstention
- BM25/FTS5 retrieval và evaluator Recall@K, MRR, nDCG@K
- Recommendation A-E, profile và feedback history
- 29 automated tests đã đạt ở lần kiểm tra gần nhất

## Việc tiếp theo

1. Dense/hybrid retrieval và ablation với BM25
2. Dataset thật, data card và quality audit
3. Gold labels cho ABSA
4. PhoBERT baseline/fine-tuning
5. Trend analysis trên dữ liệu đủ thời gian
6. Chatbot evaluation và user study
7. Cập nhật bảng kết quả vào báo cáo Google Drive

## Bảo mật

Không commit .env, API keys, SQLite database, dataset riêng hoặc thông tin người tham gia. Cấu hình SERPAPI_API_KEY và GEMINI_API_KEY bằng secrets của môi trường.
