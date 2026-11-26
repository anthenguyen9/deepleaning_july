# Kết quả dọn dự án — 18/09/2026

Điểm khôi phục trước thay đổi: commit `19aa02e`.
App Flask tiếp tục chạy; không restart tunnel hoặc thay URL công khai.

## Đã thực hiện

| Nhóm | Kết quả |
| --- | --- |
| Streamlit cũ | Chuyển `src/app.py` và hai BAT `run_demo/setup_windows` vào `archive/streamlit/`; cập nhật import, lệnh chạy và hướng dẫn |
| Gemini annotation cũ | Chuyển `src/ai_annotation.py` vào `archive/annotation/`; giữ khả năng xem `--help`, không gọi API |
| Dependency | Thêm `requirements_core.txt`, `requirements_streamlit.txt`; web và nghiên cứu không còn tự kéo Streamlit |
| Docker context | Loại `archive/` khỏi image; Docker vẫn COPY toàn bộ thư mục requirements nên các include tương đối còn hợp lệ |
| Snapshot smoke | Chuyển sang `instance/archive/public_smoke.sqlite3`, giữ khả năng kiểm tra lại thay vì xóa dữ liệu chưa chứng minh là trùng hoàn toàn |
| Backup cũ | Chuyển bản không timestamp vào `instance/archive/`; giữ bản timestamp mới hơn và checkpoint trước dọn |
| Nguồn video | Chuyển ảnh/script sang `instance/archive/demo_frames/`; MP4 trong Downloads đã được giải mã toàn bộ thành công |
| Cache và công cụ tạm | Chuyển 8 mục, tổng 84,93 MiB, vào `instance/archive/cleanup-20260918/`, giữ cấu trúc đường dẫn gốc |

8 mục cách ly: `__pycache__`, `.pytest_cache`, `src/__pycache__`,
`scripts/__pycache__`, `tests/__pycache__`, `instance/video_tools`,
`instance/foodlens.sqlite3` rỗng và `outputs/study_summary_smoke.json`.
Cache có thể tự xuất hiện lại khi ứng dụng chạy; đó không phải dữ liệu cần bảo tồn.

Hệ thống xét duyệt tự động đã từ chối lệnh xóa đệ quy với thông báo
`blocked by policy`. Vì vậy đợt này dùng di chuyển có thể khôi phục, **không xóa
vĩnh viễn và không giải phóng dung lượng ổ đĩa**. Việc tạo backup làm tăng dung
lượng lưu trữ; mục đích là dọn cấu trúc mà vẫn có đường phục hồi.

## Giữ lại có chủ đích

- Toàn bộ module thuộc luồng Flask; CSS/JS, template và thư viện Leaflet.
- `.venv` nghiên cứu, `instance/deploy-venv` đang phục vụ app, cloudflared.
- Database, secret/session, tài khoản, model SVM, các split dữ liệu và kết quả luận văn.
- PhoBERT một đầu ra để so sánh/ablation; PhoBERT hai đầu ra cho thực nghiệm dự kiến.
- `public_seed.sqlite3` và WAL/SHM, log/PID đang dùng hoặc chưa xác minh hết handle.
- LICENSE, manifest, README nguồn của ViTASA và biên bản kiểm tra lịch sử.

## Xác minh

- 17 test hiện có về auth, admin, pipeline, retrieval và recommendation: đạt.
- 1 test kiến trúc PhoBERT trong môi trường nghiên cứu: đạt; không fine-tune model.
- `AppTest` mở bản Streamlit ở vị trí lưu trữ: không có exception.
- Công cụ annotation lưu trữ chạy `--help` thành công; không gọi Gemini.
- AST tất cả file Python trong src/scripts/archive hợp lệ; 13 template biên dịch được.
- Cả 7 requirements profile đọc được đệ quy; Streamlit chỉ có trong profile riêng.
- SHA-256 của `.env`, model, khóa phiên và cấu hình demo khớp trước/sau.
- Local: 138 nhà hàng / 7.331 review / 2 tài khoản, không đổi.
- Public: 139 nhà hàng / 7.405 review / 3 tài khoản, không đổi.
- `/health` local và domain workers.dev trả 200 sau thay đổi; `/login` trả 200 trong smoke test.
- Không tuyên bố toàn bộ test suite đã xanh: các lỗi đã ghi nhận ngoài phạm vi
  dọn thư mục chưa được sửa ở đợt này. Không tuyên bố Docker image đã rebuild.

## Khôi phục

Backup SQLite trước dọn và manifest nằm ở
`instance/maintenance/cleanup-20260918T164026Z/`. Hai backup đã qua
`PRAGMA integrity_check`; file `checkpoint.json` ghi count và hash cấu hình/model,
`quarantine.json` ghi nguồn, đích, kích thước các mục đã cách ly. Thư mục instance
không được commit và không được phục vụ như static.

Khôi phục code bằng revert commit dọn; khôi phục một file cách ly bằng cách kiểm
tra đường dẫn trong manifest và chuyển lại nếu đích chưa tồn tại. Dừng riêng
server dùng database trước khi phục hồi SQLite, dùng backup đúng môi trường.
Không chép đè database đang chạy hoặc mang database local lên public.

Lệnh chạy app không đổi: `scripts/windows/run_web.bat`. Hướng dẫn công cụ cũ ở
[LEGACY_TOOLS.md](LEGACY_TOOLS.md); danh mục hiện tại ở [file_usage.csv](file_usage.csv).
