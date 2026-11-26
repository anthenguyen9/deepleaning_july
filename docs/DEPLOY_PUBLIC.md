# Triển khai FoodLens lên URL công khai

## Demo trên máy với địa chỉ Cloudflare cố định

Địa chỉ demo: https://foodlens-demo.foodlens-anthen-demo.workers.dev/ . Cloudflare
Worker `foodlens-demo` chuyển tiếp tới Quick Tunnel hiện tại và giữ nguyên URL
`workers.dev` khi thay code, restart Flask/Waitress hoặc cập nhật database. Lớp
HTTP Basic và đăng nhập FoodLens vẫn có hiệu lực. Máy chủ và tiến trình tunnel
phải chạy trong suốt buổi demo; Worker không lưu app hoặc SQLite. Nếu Quick
Tunnel được cấp origin mới, cập nhật đích chuyển tiếp trong Worker; URL công
khai trên vẫn giữ nguyên. Không thể cam kết ứng dụng trực tuyến liên tục một
tháng khi máy tính, mạng hay tunnel dừng. `compose.demo.yml` hỗ trợ tự khởi
động lại app trong Docker khi Docker Engine sẵn sàng, nhưng không khôi phục
tunnel hoặc thay thế nguồn điện/mạng.

URL `*.trycloudflare.com` chỉ giữ nguyên khi **tiến trình tunnel hiện tại vẫn
chạy**; khởi động lại Flask/Waitress ở cùng cổng không đổi URL. Quick Tunnel
cấp tên ngẫu nhiên cho phiên tunnel mới, vì vậy URL này không thể được cam kết
cố định qua lần khởi động tunnel hoặc khởi động lại máy. Muốn domain ổn định,
cấu hình Cloudflare named tunnel với zone/domain do bạn quản lý (hoặc dùng
domain riêng trên dịch vụ host phù hợp). Xem tài liệu Cloudflare:
https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/

Để cập nhật database demo đang chạy trên máy: dừng riêng worker public, chạy
`python -m scripts.sync_public_snapshot`, sau đó khởi động lại worker. Script
giữ tài khoản, hội thoại và phản hồi đã có trên demo; chỉ sao chép dữ liệu nhà
hàng/review, địa điểm và phân tích từ database local. Script tạo file backup
`instance/demo_tunnel_before_enrichment_<timestamp>.sqlite3` trước khi thay database. Không
khởi động lại tiến trình `cloudflared` nếu muốn giữ URL trong phiên hiện tại.

Mục tiêu: một Railway Web Service chạy Flask, có HTTPS và một volume SQLite.
Không đưa `.env`, database gốc hay model huấn luyện lên GitHub. Bản snapshot công khai
giữ nhà hàng/review và bỏ tài khoản, lịch sử chat, cache API, phản hồi cá nhân.

## 1. Chuẩn bị trên máy

```powershell
python src/prepare_public_db.py
```

File `instance/public_seed.sqlite3` được Git bỏ qua. Kiểm tra dòng tổng kết có
`0 accounts`. `outputs/baseline.joblib` là model tùy chọn; tải riêng lên volume
để giữ phân tích ABSA, nếu không app vẫn chạy nhưng chỉ có điểm sao/review.

## 2. Tạo service và volume

1. Trong Railway, tạo project/service từ repo
   `anthenguyen9/deepleaning_july`, branch `codex/complete-thesis`, root `/`.
   Dockerfile sẽ được tự phát hiện. Chọn khu vực gần Việt Nam.
2. Gắn một volume vào **`/app/instance`** trước lần deploy đầu. Chỉ chạy một
   replica, vì SQLite cần cùng một ổ đĩa. Bật backup volume trong Railway.
3. Generate Domain trong Settings → Networking. Railway sẽ cấp URL HTTPS
   `*.up.railway.app` và biến `RAILWAY_PUBLIC_DOMAIN`.
4. Thêm service variables bên dưới. Tạo mật khẩu/secret mới; không sao chép
   `ADMIN_PASSWORD` hoặc `FLASK_SECRET_KEY` cũ trên máy.

| Variable | Giá trị |
| --- | --- |
| `DEPLOYMENT_MODE` | `public` |
| `FLASK_SECRET_KEY` | chuỗi ngẫu nhiên ít nhất 32 ký tự |
| `ADMIN_PASSWORD` | mật khẩu mới, riêng biệt, ít nhất 16 ký tự |
| `ADMIN_USERNAME` | tên quản trị mới, khác `admin` nếu muốn |
| `DATABASE_PATH` | `/app/instance/food_reviews.sqlite3` |
| `MODEL_PATH` | `/app/instance/baseline.joblib` nếu tải model |
| `AUTO_BUILD_DENSE` | `0` |
| `RETRIEVAL_METHOD` | `bm25` (container nhỏ, không tải embedding model) |
| `SERPAPI_DAILY_LIMIT` | hạn mức muốn cấp cho bản public, ví dụ `10` |
| `GEMINI_API_KEY` | key riêng cho bản public, nếu bật chat |
| `SERPAPI_API_KEY` | key riêng cho bản public, nếu bật crawl mới |
| `DEMO_ACCESS_PASSWORD` | tùy chọn; đặt mật khẩu HTTP Basic cho link demo tạm (user `foodlens`) |
| `DEMO_AUTO_LOGIN_USERNAME` | tùy chọn; tài khoản user có sẵn được mở tự động sau khi qua mật khẩu demo |

Hai biến `DEMO_*` chỉ có hiệu lực khi `DEPLOYMENT_MODE=public`. Để đăng nhập
quản trị trên URL public, đặt `DEMO_ACCESS_PASSWORD` và **để trống**
`DEMO_AUTO_LOGIN_USERNAME`; người dùng đi qua lớp mật khẩu demo rồi đăng nhập
trên form FoodLens như bình thường. Bản chạy local không dùng lớp mật khẩu demo
hoặc tự đăng nhập, kể cả khi máy còn lưu các biến `DEMO_*`.

`PUBLIC_HOSTS` không cần nếu dùng domain Railway. Nếu dùng domain riêng, đặt
`PUBLIC_HOSTS=ten-mien-cua-ban` (hoặc danh sách phân tách bằng dấu phẩy).
Không dán các key này vào code, Git, biến build hoặc URL. Cân nhắc giới hạn
quota của cả hai nhà cung cấp vì người lạ có thể đăng ký và gửi truy vấn.

## 3. Tải dữ liệu lên volume

Sau khi service đã có volume, dùng Railway CLI đã đăng nhập và liên kết project:

```powershell
railway volume files upload instance/public_seed.sqlite3 /food_reviews.sqlite3 --overwrite
railway volume files upload outputs/baseline.joblib /baseline.joblib --overwrite
```

Chỉ tải database khi service **đang dừng** để tránh ghi đè file SQLite đang mở;
khởi động hoặc redeploy service sau khi tải. Nếu service đã chạy và tạo database
rỗng, dừng service rồi mới thay thế file. Không tải `food_reviews.sqlite3` gốc.

## 4. Kiểm tra sau deploy

- `https://<domain>/health` trả JSON `{"status":"ok"}`.
- `/login` mở bằng HTTPS; cookie phiên có `Secure`, `HttpOnly`.
- Đăng nhập/đăng ký tài khoản thử, mở Assistant; thấy nhà hàng và review thật.
- Gửi một truy vấn để kiểm tra Gemini/SerpApi với hạn mức nhỏ.
- Sau redeploy, review và tài khoản thử vẫn còn. Không kiểm tra bằng cách xóa volume.

## Chi phí và giới hạn

Railway có Free nhưng giới hạn 0,5 GB RAM và tài nguyên miễn phí thấp; app với
scikit-learn có thể cần Hobby hoặc RAM cao hơn. Hobby có mức tối thiểu $5/tháng,
chi phí thực tế phụ thuộc CPU/RAM/egress. Không chuyển gói trả phí trước khi
đặt giới hạn chi tiêu trong tài khoản. Bản public không tải dense embedding
model; BM25 là phương án phù hợp container nhỏ. Cần theo dõi quota Gemini và
SerpApi riêng với chi phí hosting.
