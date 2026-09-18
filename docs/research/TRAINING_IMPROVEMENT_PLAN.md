# Kế hoạch cải thiện F1 cho FoodLens

## Mốc hiện tại và phép đo

Baseline ViTASA trên test cố định: pair micro-F1 0,7460; pair macro-F1 của
15 nhãn 0,3135; ACD macro-F1 0,6491 (`outputs/metrics.json`). Đích 0,80–0,85
phải chỉ rõ metric và tập test. Không diễn giải 0,85 micro-F1 thành 0,85 macro-F1.
Review SerpApi là dữ liệu ứng dụng chưa được xác nhận độc lập, không phải gold
cho việc tính F1. Thử nghiệm tăng cường đã có cho thấy nhãn AI làm pair micro-F1
test còn 0,7337 và quy tắc sao còn 0,7253; không đưa các cấu hình đó vào
production chỉ vì có thêm dữ liệu.

## Các đợt thực hiện

1. Khóa bản snapshot, kiểm toán near-duplicate và rò rỉ train/dev/test ở cấp
   văn bản, tác giả/nhà hàng (nếu biết). Giữ test ViTASA bất biến. Tạo một
   tập kiểm chứng FoodLens riêng gồm review được hai người gán nhãn độc lập;
   giải quyết bất đồng, báo cáo agreement. Tập này không dùng để tune.
2. Phân tích lỗi của baseline theo từng aspect/polarity: độ hiếm nhãn, câu
   phủ định, review nhiều aspect, đánh giá sao xung đột với nội dung, tiếng Anh
   và code-switch. Ưu tiên rà soát những mẫu mà mô hình bất đồng hoặc có xác
   suất sát ngưỡng; chỉ review con người xác nhận mới gọi là gold.
3. Thử mô hình hai tầng: phát hiện aspect trước rồi phân cực cho aspect hiện
   diện; so với SVM một tầng hiện tại, PhoBERT multitask sẵn có. Tune trọng số
   lớp, threshold riêng từng nhãn và calibration **chỉ trên dev**; kiểm tra
   tác động đến micro, macro, ACD, exact match và từng nhãn.
4. Thử tăng cường review FoodLens theo trọng số 0,1–0,5, loại trùng với dev/test;
   tách nhãn sao 1–2 tiêu cực, 3 trung tính, 4–5 tích cực khỏi nhãn aspect.
   Review nhiều khía cạnh hoặc sao mâu thuẫn phải qua rà soát, không ép polarity
   chung cho mọi aspect. Có ablation baseline / gold đã xác nhận / weak labels.
5. Chọn cấu hình bằng dev, chạy test đúng một lần cho cấu hình chốt, báo cáo
   bootstrap CI, sai số theo nhà hàng và metric của cả ViTASA lẫn tập FoodLens.
   Chỉ thay `outputs/baseline.joblib` sau khi cải thiện thực tế và không giảm
   đáng kể các nhãn thiểu số. Lưu version, seed, dataset hash và thời gian chạy.

Mốc kiểm tra: trước tiên nâng micro-F1 vượt 0,75 trên dev/test độc lập; sau đó
đánh giá khả năng đạt 0,80. Mốc 0,85 là mục tiêu thử nghiệm, không phải kết quả
được đảm bảo bằng việc tăng số review hoặc đổi mô hình.
