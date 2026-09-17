# FoodLens v0.3 — Web + SQLite + SerpApi + Gemini

Ứng dụng web chạy trên Windows tại http://127.0.0.1:5000.
Flask/Jinja/CSS + Waitress; SQLite tích hợp Python, không cần cài database server.
Đây là web cá nhân chạy tại máy, chưa có tài khoản đa người dùng hoặc triển khai Internet.

## Cài và chạy (không Conda)

1. Cài Python 3.11 x64. Kiểm tra `py -3.11 --version` trong CMD.
2. Giải nén ZIP, mở thư mục `food_review_windows`, chạy `setup_web.bat`.
3. Dán SerpApi key và Gemini API key khi được hỏi. Ký tự không hiện trên màn hình
   là bình thường. Các key được lưu trong `.env` trên máy bạn; không gửi file này
   cho người khác.
4. Chạy `train_model.bat` để tải ViTASA và huấn luyện SVM. Cần Internet lần đầu.
   Có thể bỏ qua bước này để thử tìm nhà hàng và tổng hợp điểm sao trước;
   khi chưa có model, web thông báo rõ chưa có phân tích ABSA.
5. Chạy lại `configure_key.py` khi cần đổi một trong hai key. Xem README_GEMINI.md.
6. Chạy `run_web.bat`, mở http://127.0.0.1:5000.
7. Lưu hồ sơ, nhập khu vực, bấm **Tìm & phân tích nhà hàng**.

Để thu thập dữ liệu nghiên cứu tăng dần ngoài luồng web, xem `README_PIPELINE.md`.

Nếu vừa train lại model hoặc đổi key, dừng cửa sổ web bằng Ctrl+C rồi chạy lại.
Chi phí/hạn mức Gemini và SerpApi phụ thuộc gói tài khoản của bạn; ứng dụng không tự
kiểm tra số dư trên dashboard của hai dịch vụ.

### Khi `python`/`py` đang trỏ nhầm Python đã gỡ

Dùng đường dẫn Python 3.11 thực tế trên máy để tạo môi trường. Ví dụ CMD:

```bat
"%LocalAppData%\Programs\Python\Python311\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements_web.txt
.venv\Scripts\python.exe configure_key.py
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe pipeline.py download
.venv\Scripts\python.exe pipeline.py prepare
.venv\Scripts\python.exe pipeline.py train
.venv\Scripts\python.exe webapp.py
```

Nếu đường dẫn ví dụ không tồn tại, dùng vị trí Python 3.11 thực tế; không chọn Python313
đã bị gỡ. Khi đã tạo `.venv` thành công, các BAT sử dụng Python trong đó.

## Chức năng

- Hồ sơ SQLite: tên, khu vực mặc định, loại món ưa thích, điểm Google tối thiểu,
  khía cạnh ưu tiên. Đây là một hồ sơ cá nhân dùng chung trên máy, không phải đăng nhập.
- Tìm nhà hàng theo chuỗi `nhà hàng <loại món> tại <khu vực>` bằng `google_maps`.
  Kết quả phụ thuộc Google; chưa lọc bằng đa giác ranh giới địa lý.
- Lấy review `google_maps_reviews` bằng `data_id`/`place_id`, sắp xếp `newestFirst`.
  Chỉ lấy 1 trang danh sách nhà hàng và tối đa 5 nhà hàng có định danh hợp lệ.
- Mỗi nhà hàng 1–3 trang review. Trang đầu không truyền `num`; trang sau truyền
  `next_page_token` và `num=20`. Chỉ sử dụng endpoint cố định, không fetch URL từ payload.
- Lưu dữ liệu API đã loại key, nhà hàng, review và kết quả SVM; cập nhật review trùng
  theo `(restaurant_id, review_id)`. Không ghép Google review với ViTASA bằng tên.
- Nhận xét tự động dựa trên điểm mẫu và số nhãn theo khía cạnh; có review/link nguồn.
- Gemini chat dùng context SQLite, hồ sơ, feedback và tập nhà hàng đã truy xuất.
  Đây là grounded recommendation chat, chưa phải vector/hybrid RAG hoàn chỉnh.
- Xếp hạng theo tỷ lệ nhãn tích cực ở khía cạnh ưu tiên khi có >=3 nhãn;
  tie-break bằng Google rating và số lượt đánh giá. Không phải điểm xác suất đã hiệu chỉnh.
- Lịch sử mở lại không gọi API. Kết quả phân tích là snapshot; bộ lọc/sắp xếp theo
  hồ sơ hiện tại. Train lại không tự thay đổi kết quả lịch sử; tìm lại để phân tích mới.
- Phân bố theo tháng chỉ dùng `iso_date` thật. Ngày tương đối không được đoán thành
  timestamp. Chỉ hiện cảnh báo đủ mẫu tối thiểu khi >=2 tháng có >=3 review mỗi tháng;
  đây không phải kiểm định xu hướng hay BERTrend.

## Cache, hạn mức và xử lý lỗi

- Cache SQLite 24 giờ theo engine và tham số truy vấn; không theo key.
- Mặc định 3 nhà hàng × 1 trang: tối đa 4 request ngoài cache mỗi lượt tìm.
- Mức cao nhất 5 × 3: tối đa 16 request. Không tự động phân trang không giới hạn.
- `SERPAPI_DAILY_LIMIT=30` trong `.env` chặn số request ứng dụng gửi mỗi ngày UTC,
  tính cả request thất bại. Đây không phải số dư tín dụng từ tài khoản SerpApi và
  không bao gồm API call từ ứng dụng khác. Có thể tăng theo nhu cầu/hạn mức của bạn.
- Timeout mỗi request 30 giây, không retry tự động để tránh tiêu tốn quota.
- Lỗi review ở một nhà hàng không làm mất các nhà hàng khác. Kết quả đánh dấu partial,
  có thể dùng review đã lưu trước đó và hiển thị ngày cập nhật.
- Không tự bỏ cache cũ để trả kết quả thành công khi API lỗi; review cũ nếu có được
  hiển thị kèm cảnh báo. Cache lỗi không được lưu như một kết quả thành công.

## Database

File tự tạo: `instance/food_reviews.sqlite3`.

| Bảng | Nội dung |
|---|---|
| profile | Hồ sơ và sở thích một người dùng |
| restaurants | Định danh nguồn, thông tin nhà hàng và thời điểm lấy |
| reviews | Review, điểm, ngày gốc, liên kết, payload nguồn |
| analyses | Nhãn theo review, hash nội dung, phiên bản model |
| searches | Truy vấn và snapshot kết quả/lỗi một phần |
| api_cache | JSON nguồn đã loại key và thời điểm lấy |
| api_calls | Engine, thời điểm, trạng thái request; không lưu key |
| preference_memory | Sở thích tự khai báo và tóm tắt khẩu vị Gemini đã học |
| restaurant_feedback | Phản hồi thích/không thích theo nhà hàng |
| chat_sessions | Phiên tư vấn gắn với từng lượt tìm kiếm |
| chat_messages | Context hội thoại user/assistant và ID gợi ý đã kiểm tra |
| ingestion_seeds | Danh sách khu vực/loại món dùng để thu thập theo đợt |
| restaurant_crawl_state | Checkpoint phân trang review của từng nhà hàng |
| pipeline_jobs | Lịch sử, tham số, trạng thái và thống kê từng job |
| dataset_versions | Snapshot số lượng và khoảng thời gian dữ liệu |
| monthly_trends | Baseline ABSA/rating theo tháng; chưa phải BERTrend |
| review_documents, review_fts | Kho tài liệu và chỉ mục BM25 SQLite FTS5 |

Dùng SQL tham số hóa, foreign keys, WAL, transaction và khóa quota.
Muốn sao lưu: dừng web trước, sao chép cả thư mục `instance`.
Review và hồ sơ nằm trên đĩa không mã hóa; không đưa database thật lên Git.

## API key và phạm vi triển khai

Key chỉ đọc từ biến môi trường hoặc `.env` phía Python, không gửi ra HTML/JS,
không lưu vào bảng profile và không có trong ZIP. `.env` là cấu hình plaintext tại máy;
chỉ chia sẻ `.env.example` trống. `configure_key.py` cho phép thay key (đặt lại giới hạn
về 30/ngày). Key đã chia sẻ trong chat nên được thay mới trên dashboard.

App chỉ bind 127.0.0.1, có CSRF token, cookie HttpOnly/SameSite, kiểm tra Host,
escape nội dung nguồn và CSP. Không đổi sang 0.0.0.0 hoặc public port khi chưa bổ sung
authentication, phân quyền, HTTPS và cấu hình production. Không gửi hồ sơ cá nhân
cho SerpApi: chỉ gửi khu vực/loại món từ truy vấn và định danh nhà hàng cần lấy review.

## Giới hạn nghiên cứu

SVM kế thừa ViTASA từ bản v0.1, năm nhóm khía cạnh × ba cực tính.
ViTASA dùng để train, Google Maps dùng để suy luận: có domain shift; model chưa được
đánh giá bằng tập Google review gán nhãn. `hl=vi` không bảo đảm mọi review là tiếng Việt;
bản dịch tự động có thể ảnh hưởng kết quả. Nhãn dự đoán không thay thế bằng chứng nguồn.

Google rating là điểm toàn bộ do nguồn trả; điểm mẫu là trung bình review tải được;
nhãn ABSA là dự đoán mô hình. Ba loại này hiển thị riêng. Mẫu mới nhất và số lượng
nhỏ không đủ để kết luận chất lượng chung, mức độ an toàn hoặc phù hợp dị ứng.

Chưa triển khai PhoBERT multi-task, vector/hybrid retrieval, RAGAS hoặc nghiên cứu
người dùng. Gemini đã được tích hợp cho hội thoại và học sở thích, nhưng chỉ được
ground trên ứng viên của lượt tìm hiện tại. Script PhoBERT tùy chọn từ v0.1 vẫn được
giữ nhưng chưa tích hợp suy luận vào web. Chi tiết: README_GEMINI.md.

Tài liệu API đã đối chiếu:
- https://serpapi.com/google-maps-api
- https://serpapi.com/google-maps-reviews-api

## Kiểm thử

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

21 test giả lập API không tốn quota: kiểm tra CSRF/XSS, profile/SQL tham số hóa,
cache/dedup, quota, lỗi API, ngày nguồn, phân trang, Gemini structured output,
lọc ID bịa, chat memory, feedback, checkpoint incremental, ABSA pending, trend baseline,
BM25 index và render trang kết quả. Xem
VERIFICATION_WEB.md và VERIFICATION_GEMINI.md để biết phần nào đã chạy thực tế.
