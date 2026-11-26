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

## Kiểm tra khả thi trước khi chạy PhoBERT (18/09/2026)

Đã đọc trực tiếp `data/{train,dev,test}.json` và confusion matrix trong
`outputs/metrics.json`, không huấn luyện lại hay mở khóa test để chọn ngưỡng.
Các tập chứa lần lượt 1.398/200/400 văn bản; tổng nhãn cặp 2.747/379/774.
Số review có hơn một khía cạnh lần lượt 702/99/195. Không có văn bản trùng
**chính xác** trong mỗi split hay giữa các split; kiểm tra gần trùng và
trùng theo nhà hàng vẫn là việc phải làm trước khi huấn luyện.

| Tín hiệu trên test SVM hiện tại | Số liệu | Hàm ý |
| --- | ---: | --- |
| TP / FP / FN gộp 15 nhãn | 536 / 127 / 238 | micro-F1 0,7460 |
| Nhãn F1 bằng 0 | 6/15 | Macro-F1 chỉ 0,3135; trong đó 2 nhãn không có support test |
| Food positive | 331 support, F1 0,927 | Lớp phổ biến lấn át micro-F1 |
| Food neutral / price neutral / ambience neutral | 24 / 5 / 8 support, F1 0 | Cần đánh giá độ bất định và bổ sung gold đúng lớp |
| Service neutral trong train | 3 mẫu | Không đủ dữ liệu để hứa tăng tốt trên lớp này |
| Mốc micro-F1 0,80 / 0,85 | Ít nhất 65 / 130 FN đổi thành TP nếu FP cố định | Chỉ là tính toán tối ưu minh họa, không phải dự báo PhoBERT |

Lệnh `train_phobert.py` hiện là **tham chiếu một đầu ra 15 nhãn** với ngưỡng
0,5; chưa triển khai hai đầu ra như đề xuất và chưa có kết quả PhoBERT đã
kiểm chứng. Thí nghiệm tiếp theo nên dùng PhoBERT-base-v2 với đầu ra ACD
(sigmoid cho 5 khía cạnh) và đầu ra cực tính có điều kiện (3 lớp cho mỗi khía
cạnh hiện diện), mask loss ở khía cạnh không có. So sánh thêm mô hình tham
chiếu 15 nhãn hiện có và SVM cùng split, seed, cách tiền xử lý được ghi lại.
Phân tầng lỗi theo câu nhiều khía cạnh, phủ định, giá trị trung tính và độ dài
văn bản. Dùng dev để chọn checkpoint, threshold ACD, class weights và loss
weight; giữ test bất biến cho một lần xác nhận cuối. Báo cáo micro/macro-F1,
ACD macro-F1, từng lớp, exact match, bootstrap CI và thời gian suy luận CPU.

Quyết định triển khai chỉ đưa PhoBERT vào FoodLens nếu tăng macro-F1 và micro-F1
trên test cố định, không làm mất các lớp hiếm, và chi phí/tốc độ suy luận phù
hợp máy demo. Nhãn review mới suy từ sao **không** được tính là gold hay dùng
để đánh giá. Không có cơ sở thực nghiệm nào để bảo đảm 80–85% trước khi chạy.
