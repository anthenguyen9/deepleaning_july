# Chuyển FoodLens sang ổ E

Thư mục đích cho code hiện hành: `E:\FoodLens\deepleaning_july`.
Thư mục luận văn: `E:\FoodLens\thesis_paperdock`.
Model nghiên cứu/cache lớn: `E:\FoodLensArtifacts` và `E:\Codex\FoodLensModels`.

## Các bước kiểm chứng

1. Kết thúc tác vụ đang dùng project; dừng riêng hai web server và tunnel của FoodLens.
2. Checkpoint WAL, kiểm tra toàn vẹn hai SQLite và ghi hash của file, tài khoản,
   cấu hình cùng model vào manifest riêng ngoài repository.
3. Chuyển bằng đường dẫn tuyệt đối đã đối chiếu, không ghi đè thư mục có sẵn.
4. Đối chiếu lại toàn bộ file theo manifest trước khi cập nhật launcher.
5. Tạo junction ở đường dẫn cũ để các shortcut/venv launcher cũ tiếp tục trỏ tới
   dữ liệu thật trên E. Junction không phải bản sao code ở C.
6. Chạy app trực tiếp từ E; kiểm tra test, database, route và domain.

Python nền do Codex/Windows cài ở C vẫn là runtime hệ thống; không di chuyển
runtime chung của các project khác. Môi trường `.venv` và `instance/deploy-venv`
nằm trong project và đi cùng sang E. Ưu tiên `python -m pip`, `python -m scripts.serve`
thay vì launcher có đường dẫn tuyệt đối cũ.

## Khởi động

Tại root project:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/start_servers.ps1
```

Local: `http://127.0.0.1:5001/`. Public origin: `http://127.0.0.1:5000/`.
Script không dừng tiến trình khác và không tạo database rỗng khi thiếu file.
Chạy local ở cửa sổ tương tác: `scripts/windows/run_web.bat`.

Domain demo vẫn là `https://foodlens-demo.foodlens-anthen-demo.workers.dev/`.
Khởi động lại Quick Tunnel có thể đổi origin nội bộ; cần cập nhật Worker tới origin
mới, không đổi tên Worker. Không đưa URL Quick Tunnel cho người dùng làm địa chỉ
cố định. Máy, mạng và tunnel cần hoạt động để domain truy cập được.

## Dữ liệu cần giữ

`instance/food_reviews.sqlite3` là local, `instance/demo_tunnel.sqlite3` là public;
không chép đè hai file lên nhau. Giữ `.env`, `.flask_secret_key`, cấu hình demo,
model baseline và tài khoản cũ. `SESSION_COOKIE_NAME` cho phép giữ tên phiên khi
đổi vị trí project; không cần thay mật khẩu người dùng để di chuyển thư mục.

## Kết quả thực hiện ngày 19/09/2026

- Đã chuyển 56.571 file (2.376.897.658 byte) và đối chiếu SHA-256 trước/sau:
  tất cả khớp. 48 file luận văn cũng khớp. Đối chiếu thực hiện trước các log,
  báo cáo và commit phát sinh sau khi khởi động lại.
- Cả hai DB `integrity_check=ok`; hash toàn bộ dòng tài khoản không đổi.
- Local giữ 138 nhà hàng, 7.331 review, 2 tài khoản, 4 phản hồi và 50 tin nhắn.
- Public giữ 139 nhà hàng, 7.405 review, 3 tài khoản, 5 phản hồi và 6 tin nhắn.
- `.env`, khóa phiên và model baseline nằm trong tập file đã đối chiếu;
  tên cookie phiên đã được cố định trước khi chuyển. Trình duyệt local còn phiên cũ.
- VS Code được mở lại ở E; đường dẫn project và luận văn cũ là junction tới E.
  Junction model cũ được lưu trong `migration-links` tại workspace C, không xóa
  hoặc di chuyển nội dung model phía đích. Model tiếp tục nằm trên E.
- 36/36 test đạt từ ổ E. Kiểm tra phụ thuộc môi trường web không có lỗi.
- Đăng nhập admin public bằng thông tin có sẵn thành công; sáu trang chính và
  `/health` local/public trả HTTP 200. Worker giữ tên và URL cũ, cập nhật origin mới.
- Bốn truy vấn trên bản sao DB thật vẫn trả bằng chứng khi cố ý tắt provider:
  xem `outputs/post_move_smoke.json`. Không gọi SerpApi/OpenAI cho kiểm tra đó.
- Kiểm tra trực tiếp trình duyệt: Assistant, xu hướng, hồ sơ tải được sau chuyển.

Manifest riêng: `E:\FoodLensArtifacts\validation\migration_20260919.json`;
backup DB trước chuyển: `pre_move_local.sqlite3`, `pre_move_public.sqlite3` cùng
thư mục. Không commit các file này vì chúng chứa dữ liệu tài khoản/người dùng.

Nếu khởi động lại cả tunnel, chạy `scripts/windows/start_tunnel.ps1` trước server;
script ghi origin vào `instance/tunnel_origin.txt` để server chấp nhận đúng host.
Sau đó cập nhật origin của Worker hiện có qua Cloudflare nếu origin đổi.
Lệnh `start_servers.ps1` không tự redeploy Worker. Kiểm tra HTTP ở domain bằng
trình duyệt; Cloudflare đã từ chối User-Agent mặc định của urllib với mã 1010,
trong khi User-Agent trình duyệt và đăng nhập thực hoạt động bình thường.
