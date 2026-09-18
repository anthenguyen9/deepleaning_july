# Rà soát file và kế hoạch dọn FoodLens

**Trạng thái:** kế hoạch bên dưới là bản trước khi dọn. Xem
[kết quả thực thi](CLEANUP_RESULT.md) cho đường dẫn và trạng thái hiện tại;
`file_usage.csv` đã được cập nhật theo các file đã chuyển.

Ngày kiểm tra: 2026-09-18. Mốc mã nguồn: `4b3b53e`.
Phạm vi: file Git, import Python (kể cả import trong hàm), entry point Windows/Docker,
template/static, cấu hình đường dẫn và tên/kích thước dữ liệu cục bộ. Không đọc giá trị
khóa bí mật. Đây là **kế hoạch**, chưa xóa hoặc chuyển các file được đề xuất bên dưới.

## Kết luận

- 18/30 module trong `src/` nằm trong đồ thị phụ thuộc của Flask; giữ nguyên.
- 12 module còn lại là công cụ offline hoặc ứng dụng Streamlit cũ. Không được Flask
  import không đồng nghĩa với không còn giá trị.
- Cả 13 template đều được route hoặc template khác tham chiếu và biên dịch được.
- Cả 11 file trực tiếp trong `static/` đều được giao diện tham chiếu. Chưa có bằng
  chứng để xóa nguyên file CSS/JS; cần đo độ sử dụng selector riêng trước khi gộp CSS.
- Hai môi trường Python phục vụ mục đích khác nhau: `.venv` Python 3.12 có torch,
  transformers, Streamlit, BERTopic; server đang chạy từ `instance/deploy-venv`
  Python 3.11. Giữ cả hai trong đợt dọn đầu.
- Danh mục từng file Git và bằng chứng nằm tại [file_usage.csv](file_usage.csv).
  Phân tích tĩnh này không chứng minh mọi hàm/nhánh đều được thực thi; các import
  có điều kiện, chế độ nghiên cứu và đường dẫn nhận qua CLI vẫn phải được giữ.

## Mã nguồn đang phục vụ web

Giữ `webapp.py`, `auth.py`, `admin_annotations.py`, `location_routes.py`,
`assistant_service.py`, `assistant_view.py`, `chat_ui.py`, `locations.py`,
`restaurant_service.py`, `recommendation_service.py`, `retrieval_service.py`,
`dense_service.py`, `gemini_service.py`, `openai_service.py`, `data_pipeline.py`,
`pipeline.py`, `storage.py`, `trend_dashboard.py` trong `src/`.

`pipeline.py` và `data_pipeline.py` vừa là CLI vừa được server import. Hai provider
Gemini/OpenAI cùng dense retrieval là khả năng có điều kiện; không xóa chỉ vì một
provider hoặc retrieval mode hiện đang tắt.

## Công cụ offline: giữ hay lưu trữ

| File | Bằng chứng sử dụng | Quyết định |
| --- | --- | --- |
| `src/configure_key.py` | `scripts/windows/setup_web.bat` gọi | Giữ |
| `src/seed_locations.py` | CLI nạp catalog; hướng dẫn README | Giữ |
| `src/import_gold.py` | Nhập nhãn đã kiểm tra, được tài liệu hướng dẫn | Giữ |
| `src/prepare_public_db.py` | Tạo database public đã lọc; tài liệu deploy | Giữ |
| `src/research.py` | Build dense, annotation, retrieval, survey | Giữ |
| `src/evaluate_recommendation.py` | CLI đánh giá A–E | Giữ |
| `src/compare_pseudo_labels.py` | Tạo hai báo cáo augmentation đang dùng trong luận văn | Giữ để tái lập |
| `src/topic_trends.py` | Thực nghiệm BERTopic; khác dashboard aggregate | Giữ để nghiên cứu |
| `src/train_phobert_multitask.py` | Mô hình hai đầu ra; test kiến trúc tham chiếu | Giữ, chưa có kết quả fine-tune để thay SVM |
| `src/train_phobert.py` | Tham chiếu một đầu ra, README vẫn hướng dẫn | Có thể lưu trữ sau khi chọn pipeline hai đầu ra; giữ nếu làm ablation |
| `src/ai_annotation.py` | Công cụ Gemini cũ, ANNOTATION_GUIDE vẫn nhắc | Đề xuất lưu trữ vì yêu cầu mới không dùng Gemini để gán nhãn; giữ dữ liệu/provenance cũ |
| `src/app.py` | Streamlit qua `run_demo.bat` | Đề xuất lưu trữ cùng `run_demo.bat` và `setup_windows.bat` nếu chỉ bàn giao Flask |

Ba script `scripts/enrich_coverage.py`, `label_local_reviews.py`,
`sync_public_snapshot.py` vừa được dùng để thu thập, gán nhãn tạm và đồng bộ public.
Giữ `scripts/__init__.py`: nó cung cấp đường dẫn `src/` cho các lệnh `python -m scripts...`.
Giữ `run_web.bat`, `setup_web.bat`, `train_model.bat`, `run_data_pipeline.bat`.

## Dữ liệu, model và tài liệu không được xem là rác

- `.env`, `.env.example`, `instance/.flask_secret_key`, `demo_credentials.json`,
  `docker_demo.env`: cấu hình và phiên đăng nhập; không xóa, không đưa bí mật vào Git.
- `instance/food_reviews.sqlite3` (70,73 MiB), `demo_tunnel.sqlite3` (38,29 MiB):
  database thực đang dùng; các file WAL/SHM đi kèm không được xóa thủ công khi DB mở.
- `outputs/baseline.joblib`: mô hình triển khai. Giữ metrics, audit, dự đoán test,
  báo cáo augmentation và nguồn dữ liệu để kiểm chứng các số liệu trong luận văn.
- `data/train.json`, `dev.json`, `test.json`, raw ViTASA, annotation và manifest:
  không xóa vì web không đọc chúng. Giữ các split và bằng chứng nguồn nhãn; tên
  `data/gold/` không tự chứng minh đó là nhãn gold độc lập.
- `data/README.md` là README **của bộ ViTASA**, được `source_manifest.json` ghi nhận
  và `pipeline.download` tải cùng LICENSE. Không chuyển nó sang docs hay xóa như
  tài liệu project trùng lặp.
- `location_data/*.json`, các file LICENSE và ba fixture example tại gốc: cần cho
  catalog, nguồn dữ liệu/thư viện và thực nghiệm; giữ hoặc chuyển examples có sửa link.
- `docs/verification/`: biên bản lịch sử, không xóa vì mô tả phiên bản cũ. Nên thêm
  ngày/mốc version và liên kết tới báo cáo kiểm tra hiện tại để tránh hiểu nhầm.

## Ứng viên dọn cục bộ

Kích thước là tại thời điểm kiểm tra, đơn vị MiB (1.048.576 byte).

| Đường dẫn | Dung lượng | Phương án và điều kiện |
| --- | ---: | --- |
| `__pycache__/`, các `__pycache__` trong src/scripts/tests; `.pytest_cache/` | khoảng 1 MiB | Có thể xóa cache, sẽ tự sinh lại; dùng danh sách đường dẫn trong workspace |
| `instance/foodlens.sqlite3` | 0 | File rỗng, không có đường dẫn cấu hình đang dùng; có thể xóa sau kiểm tra lần cuối |
| `instance/public_smoke.sqlite3` | 22,92 | Snapshot smoke không được cấu hình hiện tại tham chiếu; xác nhận không có tiến trình mở và không có dữ liệu duy nhất trước khi xóa |
| `outputs/study_summary_smoke.json` | <0,01 | Kết quả smoke 0 người tham gia, không phải nghiên cứu người dùng; có thể tái tạo từ fixture |
| `instance/demo_frames/` | 3,99 | Nguồn ảnh và script video; lưu trữ nếu còn cần dựng lại video, chỉ xóa sau kiểm tra bản MP4 ở Downloads |
| `instance/video_tools/` | 83,67 | Công cụ ffmpeg tạm; chỉ xóa sau hoàn tất/chốt video, giữ lại cách cài tái tạo |
| `instance/public_seed.sqlite3` và WAL/SHM | 22,93 | Artifact deploy có thể tái tạo, nhưng DEPLOY_PUBLIC còn tham chiếu; chưa xóa trong đợt đầu |
| Hai `demo_tunnel_before_enrichment*.sqlite3` | tổng 59,12 | Backup rollback: giữ bản mới nhất, lưu trữ bản cũ sau kiểm tra tài khoản và dữ liệu |
| Log/PID cũ trong `instance/` | rất nhỏ | Đối chiếu tiến trình và file log thực đang mở; không xóa bằng wildcard toàn bộ `.log/.pid` |
| `.venv/` | 1.513,10 | Giữ: môi trường nghiên cứu và các BAT đang tham chiếu |
| `instance/deploy-venv/` | 256,54 | Giữ: server local/public đang chạy từ đây |
| `instance/tools/cloudflared.exe` | 52,43 | Giữ: tunnel đang hoạt động |

Hai PNG marker mặc định của Leaflet hiện không được bản đồ app dùng trực tiếp
(Assistant/Trends dùng `L.divIcon`). Tuy nhiên Leaflet có đường dẫn fallback,
CSS tham chiếu `images/marker-icon.png`; vị trí hiện tại và rule loại PNG trong
`.dockerignore` cần kiểm tra khi đóng gói. Giữ cả bundle/vendor license trong
đợt này: xóa vài KB ảnh không có lợi so với nguy cơ hỏng bản đồ khi bật control mới.

## Thứ tự thực hiện đề xuất

1. **Chốt điểm khôi phục:** ghi commit, danh sách file/kích thước, backup SQLite
   qua SQLite backup API nếu DB đang mở; ghi rõ database/model mà hai server dùng.
2. **Dọn phát sinh có thể tái tạo:** cache, file SQLite rỗng, smoke output; đối chiếu
   `public_smoke.sqlite3` trước khi xóa. Không đụng virtualenv hay database thật.
3. **Lưu trữ tính năng cũ:** Streamlit và Gemini annotation; sửa README,
   ANNOTATION_GUIDE, BAT, đường dẫn và import của file đã chuyển. Không chuyển
   script Python đơn thuần vì sẽ làm mất cách tìm `pipeline` trong `src/`.
4. **Tách dependency:** training hiện kế thừa `requirements.txt`, kéo theo Streamlit.
   Tách core/web, legacy Streamlit, PhoBERT và topic requirements trước khi cân nhắc
   bỏ Streamlit. Không gỡ package khỏi môi trường đang chạy.
5. **Chốt pipeline training:** quyết định có cần PhoBERT một đầu ra cho ablation;
   chỉ lưu trữ nó khi tài liệu và thực nghiệm không còn cần. Giữ hai đầu ra + baseline SVM.
6. **Xác minh sau từng nhóm:** import/CLI, compile 13 template, login/home/Assistant/
   trends/admin, đọc model/database, asset bản đồ và hai endpoint health. Chạy test
   liên quan; so với lỗi đã tồn tại trước dọn, không coi toàn bộ test đang xanh.
7. **Chốt lưu trữ:** chỉ dọn video tools/frames và backup cũ sau khi kiểm tra MP4,
   khả năng rollback và hướng dẫn tạo lại; mỗi nhóm một commit để dễ phục hồi code.

Chưa xóa gì ở lần kiểm tra này. Không có cơ sở để xóa hàng loạt `.py`, CSS, dataset,
model hoặc các kết quả nghiên cứu. Lợi ích lớn nhất trước mắt là giảm nhầm lẫn giữa
luồng Flask đang chạy và công cụ demo cũ, không phải giảm vài chục KB mã nguồn.
