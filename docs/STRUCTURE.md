# Cấu trúc dự án FoodLens

| Thư mục | Vai trò |
| --- | --- |
| `src/` | Ứng dụng Flask, dữ liệu, tìm kiếm, gợi ý và các lệnh Python nghiên cứu. |
| `scripts/` | Các tác vụ vận hành và thu thập; `scripts/windows/` chứa lệnh `.bat`. |
| `requirements/` | Bộ phụ thuộc cho web, nghiên cứu, PhoBERT và chủ đề. |
| `docs/` | Hướng dẫn, tình trạng nghiên cứu và biên bản xác minh. |
| `templates/`, `static/` | Giao diện Flask. |
| `tests/` | Kiểm tra có sẵn. |
| `data/`, `outputs/` | Dữ liệu nghiên cứu và đầu ra mô hình. |
| `instance/` | Cơ sở dữ liệu, cấu hình riêng và dữ liệu chạy; không đưa khóa vào Git. |

Từ gốc dự án trên Windows, chạy `scripts\windows\setup_web.bat`, sau đó
`scripts\windows\run_web.bat`. Các script tự đặt thư mục làm việc về gốc và
thêm `src/` vào đường dẫn Python. Khi chạy lệnh Python thủ công trong PowerShell,
đặt `$env:PYTHONPATH = (Join-Path (Get-Location).Path 'src')` rồi gọi
`python src/webapp.py` hoặc `python -m scripts.enrich_coverage --help`.

Ứng dụng Docker dùng `compose.demo.yml`, nạp cấu hình riêng từ
`instance/docker_demo.env`, và gắn cùng thư mục `instance/` để dữ liệu tồn tại
sau khi tạo lại container. Bắt đầu tại [README.md](README.md).
