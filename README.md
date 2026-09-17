# FoodLens — Windows Web v0.3

## Location-aware Restaurant Assistant (2026-09)

Ứng dụng Flask tại `webapp.py` dùng duy nhất `instance/food_reviews.sqlite3` qua
`Store`. Schema được tạo bằng `CREATE TABLE IF NOT EXISTS` khi khởi động; dữ liệu cũ
không bị xóa. `import_gold.py` dùng đường dẫn tuyệt đối từ `data_pipeline.DEFAULT_DB`,
kiểm tra file và bảng trước khi ghi, chỉ nhận nhãn đã được người thật duyệt.
Nhãn AI không được coi là gold độc lập.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements_research.txt
Copy-Item .env.example .env
# Điền GEMINI_API_KEY, SERPAPI_API_KEY, ADMIN_PASSWORD, FLASK_SECRET_KEY trong .env
.venv\Scripts\python.exe seed_locations.py --city "Da Nang"
.venv\Scripts\python.exe webapp.py
```

Đăng nhập admin tại `/login` rồi mở `/admin/locations/` để chọn Việt Nam → Đà Nẵng
→ phường/xã hoặc đường, xem trạng thái crawl và bấm Crawl / Refresh. Cấp quận
không còn là cấp hành chính hiện hành tại Đà Nẵng; tên một số quận cũ được nhận
như bí danh của phường cùng tên. API `/admin/locations/api/children?parent=<id>`
chỉ dành cho admin. Người dùng thường đăng ký rồi mở `/assistant` để chat riêng.

`seed_locations.py` chạy lặp lại không tạo trùng. Snapshot `location_data/danang_2025.json`
có 94 đơn vị cấp xã theo [Nghị quyết 1659/NQ-UBTVQH15](https://xaydungchinhsach.chinhphu.vn/toan-van-nghi-quyet-so-1659-nq-ubtvqh15-sap-xep-cac-dvhc-cap-xa-cua-thanh-pho-da-nang-nam-2025-119250616202714604.htm),
áp dụng từ 01/07/2025. Snapshot `location_data/danang_osm_streets.json` chứa
12.146 OSM highway ways có tên trong bounding box bao quanh Đà Nẵng mới, sau
chuẩn hóa còn 4.905 tên đường duy nhất. Dữ liệu đường theo
[ODbL / OpenStreetMap contributors](https://www.openstreetmap.org/copyright).
Bounding box có thể chứa đường ngoài địa giới và chưa có phép nối đường–phường;
chọn đồng thời đường và phường sẽ được yêu cầu làm rõ thay vì suy diễn quan hệ.
Schema `locations` có cấp quốc gia/tỉnh/huyện/phường/đường và ngày hiệu lực
để mở rộng cho tỉnh khác hoặc phiên bản địa giới sau này.

Chatbot dùng Gemini để tách intent và địa điểm thành JSON, rồi tra DB địa điểm
trước khi gọi SerpApi. Địa điểm không hợp lệ chặn crawl. `crawl_runs` lưu
location + truy vấn (bao gồm loại món) + tháng + provider; crawl thành công
trong tháng dùng lại snapshot. Lỗi provider được ghi trạng thái `failed` để
có thể thử lại. Nhà hàng/review được upsert theo ID nguồn, hoặc tên + địa chỉ
chuẩn hóa khi thiếu ID. Kết quả từ SQLite được chấm ABSA bằng model đã lưu,
xếp hạng bằng cấu hình E, truy xuất review và cung cấp ứng viên/trích dẫn cho
Gemini. Chat không huấn luyện lại. Khi SerpApi thiếu key hoặc lỗi, app vẫn dùng
dữ liệu SQLite sẵn có nếu đủ bằng chứng. Khi Gemini thiếu key hoặc lỗi,
chat hiển thị lỗi cấu hình/hạn mức rõ ràng; app không bị dừng.

Huấn luyện là lệnh offline riêng: `.venv\Scripts\python.exe pipeline.py train`
(từ tập ViTASA đã `download` và `prepare`), lưu `outputs/baseline.joblib`.
`research.py prepare-gold` chỉ dành cho nhãn người duyệt độc lập. Để nhập nhãn
đã duyệt: `.venv\Scripts\python.exe import_gold.py data/gold_human.json`.
`data_pipeline.py` tiếp tục tính aggregate theo **ngày, tháng, năm** từ
`reviews.published_at`; ngày thiếu/không parse được không tự suy diễn.

Biến môi trường nằm trong `.env` (Git bỏ qua): `SERPAPI_API_KEY`,
`SERPAPI_DAILY_LIMIT`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD`, `FLASK_SECRET_KEY`. Không đưa key xuống HTML hay log.
Nếu `FLASK_SECRET_KEY` để trống, ứng dụng tạo khóa phiên một lần trong
`instance/.flask_secret_key` (thư mục này không được đưa lên Git). Các tiến trình
cùng project, kể cả khi chạy ở cổng 5000 và 5001, dùng chung khóa và cookie;
sau lần cập nhật này cần đăng nhập lại một lần. Form có CSRF hết hạn sẽ quay về
trang an toàn kèm thông báo để gửi lại.

**Bắt đầu với [README_WEB.md](README_WEB.md).** Chạy `setup_web.bat`,
`train_model.bat`, rồi `run_web.bat` để dùng web Flask + SQLite + SerpApi.
Xem `VERIFICATION_WEB.md` cho kết quả kiểm thử bản web.

Pipeline thu thập tăng dần, ABSA pending, thống kê tháng và BM25 nằm trong
[`README_PIPELINE.md`](README_PIPELINE.md). Chạy `run_data_pipeline.bat` để xem trạng thái.

Phần dưới giữ lại tài liệu baseline v0.1 để giải thích dữ liệu và mô hình.
Các giới hạn metadata bên dưới nói về ViTASA; bản web bổ sung metadata Google Maps.

---

# Food Review Research — baseline v0.1 (tài liệu nền)

## Trạng thái hiện tại

FoodLens hiện có ứng dụng Flask để thu thập review nhà hàng từ SerpApi, phân tích
cảm xúc bằng baseline ViTASA, thống kê theo tháng, truy xuất BM25/dense/hybrid
và chatbot Gemini có kiểm tra trích dẫn. Có bộ lệnh thực nghiệm cho PhoBERT
ACD+SPC, BERTopic và đánh giá retrieval. Xem [RESEARCH_STATUS.md](RESEARCH_STATUS.md)
để biết phần nào đã chạy trên dữ liệu thật và phần nào còn cần gold label,
relevance judgments hoặc người tham gia nghiên cứu. Khóa API chỉ đặt trong `.env`.

Chạy ứng dụng mới trên Windows sau khi cài `requirements_research.txt`:

```bat
.venv\Scripts\python.exe research.py status
.venv\Scripts\python.exe research.py build-dense
.venv\Scripts\python.exe webapp.py
```

Mở `http://127.0.0.1:5000`; trang `/research` hiển thị độ phủ dữ liệu và
tín hiệu xu hướng. Hướng dẫn thu thập, checkpoint và provenance có trong
[README_PIPELINE.md](README_PIPELINE.md).

Ứng dụng mở đầu tại `/login`. Tài khoản quản trị khởi tạo lần đầu là `admin` /
`admin` trên máy cá nhân; cấu hình `ADMIN_USERNAME` và `ADMIN_PASSWORD` trong
`.env` trước lần khởi tạo nếu muốn đổi. Người dùng thường chọn `/register` và
phải nhập tài khoản, mật khẩu, tên, khu vực, món ưa thích, sở thích, khía cạnh
ưu tiên và ngưỡng điểm. Hồ sơ chỉnh sửa tại `/profile`. Tài khoản, hồ sơ,
phản hồi và quyền truy cập lưu trong SQLite; mật khẩu chỉ lưu dưới dạng hash.
Người dùng thường chỉ thấy lượt tìm của mình và không được truy cập `/admin/`.
Admin có thể gán nhãn khía cạnh–cảm xúc cho từng review, xuất JSON qua
`/admin/export`. Nhãn thủ công nằm trong bảng `gold_annotations`, tách khỏi
dự đoán ABSA; bản xuất bỏ qua nhãn nếu nội dung review đã thay đổi. Một tài
khoản admin không tạo được đánh giá agreement độc lập giữa hai người.

## Phạm vi bản demo ban đầu

Bản đầu có pipeline ViTASA Restaurant, kiểm tra dữ liệu, split tái lập,
TF-IDF ký tự + One-vs-Rest SVM, majority baseline, báo cáo F1 và demo Streamlit.
Có script PhoBERT tham chiếu tùy chọn; chưa chạy huấn luyện PhoBERT hoặc xác nhận GPU/Windows.
Đây CHƯA phải toàn bộ luận văn: chưa có kiến trúc multi-task ACD+SPC,
BERTopic/BERTrend, hybrid/vector retrieval, LLM generation, RAGAS hoặc user study.
Không thay đổi file đề cương gốc.

## Chạy trên Windows

1. Cài Python 3.11 x64 từ https://www.python.org/downloads/windows/ (kèm Python Launcher).
2. Giải nén thư mục; chạy `setup_windows.bat` trong CMD. Cần Internet lần đầu.
3. Chạy `run_demo.bat`; mở địa chỉ localhost hiện trong cửa sổ.

Hoặc thực hiện từng lệnh trong CMD:

```bat
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m unittest discover -s tests
.venv\Scripts\python pipeline.py download
.venv\Scripts\python pipeline.py prepare
.venv\Scripts\python pipeline.py train
.venv\Scripts\python -m streamlit run app.py --server.address 127.0.0.1
```

CPU dùng được cho SVM; không cần API trả phí hay Conda. Nếu download lỗi mạng,
chạy lại riêng lệnh download; không bỏ qua lỗi để train dữ liệu không đủ.

## Dữ liệu và giấy phép

Nguồn: https://github.com/kh4nh12/ViTASA
Commit cố định: cda6a4525bfdf7a7632a7d7c7ccdbe00af5b3094.
Downloader lấy restaurant.jsonl, LICENSE và README từ chính repo tác giả,
lưu SHA-256 trong data/source_manifest.json. ZIP bàn giao không phân phối lại dữ liệu thô.
Repo có MIT LICENSE; cần xác nhận quyền dữ liệu nguồn trước khi tái phân phối.
Trích dẫn: Tran et al., ViTASA: New benchmark and methods for Vietnamese targeted
aspect sentiment analysis for multiple textual domains, Computer Speech & Language,
93, 101800, 2025, https://doi.org/10.1016/j.csl.2025.101800.

## Quyết định nhãn — cần giảng viên duyệt

Chỉ dùng trường `label` (span annotations). Trường `labels` là nguồn chú giải khác,
không trộn hoặc tuyên bố một trường sai. Giữ cả hai trong file raw để đối chiếu.
Các span chuyển thành tập cặp khía cạnh/cực tính cấp review; không huấn luyện span extraction.
PRICE luôn ánh xạ vào price; FOOD/DRINKS khác PRICE vào food;
SERVICE, AMBIENCE, LOCATION vào service, ambience, location.
RESTAURANT không phải PRICE bị bỏ vì không ánh xạ chắc chắn vào năm nhóm.
Giữ nhiều polarity cho một aspect; không tự biến mixed thành neutral.
Review không có nhãn được ánh xạ trở thành vector 0; audit công bố phân bố nhãn.

Kết quả là bài toán chuyển đổi riêng, không so trực tiếp với điểm paper ViTASA.
Deduplicate text chuẩn hóa, cách ly exact duplicate mâu thuẫn; seed 42, split 70/10/20.
Không có timestamp/restaurant_id nên không temporal/group split được. Chưa khử near-duplicate.
Vectorizer fit train; chọn C theo dev; test chỉ dùng đánh giá sau chọn cấu hình.
Không lặp tuning dựa trên test. Nhãn hiếm có thể vắng ở split và kéo macro F1 xuống.

## PhoBERT tùy chọn

```bat
.venv\Scripts\python -m pip install -r requirements_phobert.txt
.venv\Scripts\python train_phobert.py --epochs 3 --batch-size 4
```

Tải model lớn, cần Internet/dung lượng và có thể chạy chậm trên CPU.
CUDA cần bản PyTorch tương thích máy theo https://pytorch.org/get-started/locally/.
Tham chiếu model: https://huggingface.co/vinai/phobert-base-v2 (AGPL-3.0).
Script dùng underthesea segmentation, không giống segmenter tiền huấn luyện VnCoreNLP;
giới hạn 256 tokens có thể bỏ mất bằng chứng cuối review. Báo cáo những giới hạn này.
Single-head multi-label PhoBERT không được gọi là multi-task ACD+SPC.
Demo hiện chỉ nạp SVM. Không nạp file joblib từ nguồn không tin cậy.

## Output

- outputs/audit.json: lỗi span, trùng lặp, phân bố từng split.
- outputs/metrics.json: dev tuning, test micro/macro F1, exact match, per-label, majority.
- outputs/test_predictions.json: phục vụ phân tích lỗi (tạo cục bộ).
- outputs/baseline.joblib: mô hình tạo cục bộ.
- outputs/phobert_metrics.json: chỉ xuất sau khi huấn luyện PhoBERT thực sự.

Review evidence search là TF-IDF lexical, không phải semantic/hybrid RAG.
Không có metadata nên KHÔNG gán review vào nhà hàng/món ăn ViFoodRec,
không tạo timestamp, không xuất xu hướng hoặc địa chỉ giả.

## Bước tiếp theo

Chốt guideline nhãn với giảng viên; chạy PhoBERT trên máy đích; bổ sung ACD+SPC,
multi-seed/CI và error analysis. Khi có metadata hợp lệ mới triển khai trend và
gợi ý địa điểm. NTC-SCV/ViFoodRec chưa tích hợp vào bản v0.1.
