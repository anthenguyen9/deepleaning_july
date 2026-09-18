# Công cụ lịch sử

Ứng dụng chính là Flask: chạy `scripts/windows/run_web.bat`.
Các công cụ trong `archive/` được giữ để tái lập công việc cũ, không được đưa vào
Docker image và không tự chạy cùng server.

## Streamlit

Chạy từ gốc repository:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements/requirements_streamlit.txt
.venv\Scripts\python.exe -m streamlit run archive/streamlit/app.py --server.address 127.0.0.1
```

Hoặc mở `archive/streamlit/run_demo.bat`. BAT tự đưa thư mục làm việc về gốc.
`setup_windows.bat` trong cùng thư mục là quy trình thiết lập nghiên cứu cũ,
có tải dữ liệu và train SVM; không chạy lại chỉ để mở demo.

## Gemini annotation

`archive/annotation/ai_annotation.py` đã thêm đường dẫn `src/` cho import cũ.
`python archive/annotation/ai_annotation.py --help` chỉ hiển thị cách dùng.
Chạy gán nhãn thật bằng công cụ này sẽ gọi Gemini; luồng hiện tại dùng
`python -m scripts.label_local_reviews` và không tự kích hoạt công cụ lưu trữ.
Giữ các file annotation AI cũ và nguồn gốc của nhãn để tái lập báo cáo.

## Video và bản sao dữ liệu cục bộ

Ảnh và script dựng video ở `instance/archive/demo_frames/`. Video đã xuất nằm tại
`C:/Users/Admin/Downloads/FoodLens-demo-2026-09-18.mp4` và đã kiểm tra giải mã toàn bộ.
`instance/archive/cleanup-20260918/instance/video_tools/` giữ bộ ffmpeg tạm vì
hệ thống chặn xóa đệ quy. Nếu cần cài lại tại vị trí cũ, dùng
`python -m pip install --target instance/video_tools imageio-ffmpeg==0.6.0`.
Pillow cần cho script dựng ảnh; giữ môi trường có Pillow khi chạy lại script.

Database smoke và backup cũ được chuyển vào `instance/archive/`, vẫn được Git
bỏ qua. Không dùng chúng làm database đang phục vụ và không commit lên repository.
