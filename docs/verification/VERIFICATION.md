# Kết quả kiểm tra v0.1

Đã chạy thực tế trên Linux, Python 3.12, scikit-learn 1.8.0.
Chưa kiểm thử trên Windows/Python 3.11; các script BAT dành cho máy đích.

- Tải thành công ViTASA Restaurant từ commit ghi trong README: 2.000 review.
- Sau loại 2 review trùng chính xác: 1.998 review, không có span lỗi.
- Train/dev/test: 1.398 / 200 / 400; không giao nhau về text đã chuẩn hóa.
- 7 unit test thành công; kiểm tra cú pháp cả pipeline, app và script PhoBERT thành công.
- Smoke test dự đoán 15 nhãn và truy hồi chỉ từ tập train thành công.
- SVM chọn C=1 bằng dev micro-F1, không chọn cấu hình theo test.

| Chỉ số test | SVM | Majority |
| --- | ---: | ---: |
| Micro-F1 | 0,7460 | 0,5639 |
| Macro-F1 (15 nhãn cố định) | 0,3135 | 0,0604 |
| Exact match | 0,4475 | 0,3150 |

Đây là kết quả một lần chia dữ liệu với seed 42, không phải điểm benchmark gốc
ViTASA. Nhiều nhãn hiếm có F1 bằng 0. LOCATION:NEUTRAL không có mẫu train;
cảnh báo constant-label của scikit-learn là dự kiến, không phải huấn luyện thành công
nhãn này. Macro-F1 tính cả nhãn vắng với zero_division=0.

Chưa chạy giao diện Streamlit vì môi trường kiểm thử chưa cài Streamlit.
Chưa huấn luyện hoặc kiểm thử runtime PhoBERT. Chưa triển khai RAG LLM,
multi-task ACD+SPC và phân tích xu hướng. Không có timestamp/restaurant_id
để đánh giá trend hoặc đề xuất nhà hàng cụ thể một cách có căn cứ.

ZIP không chứa dữ liệu thô hoặc model joblib. Setup tải dữ liệu và train tại máy
người dùng; outputs/metrics.json là báo cáo của lần chạy kiểm thử nêu trên và
sẽ được thay thế khi train lại.
