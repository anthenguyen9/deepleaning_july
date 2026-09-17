# Quy trình gán nhãn và đánh giá FoodLens

Tập SerpApi là review ứng dụng, không có gold label. `research.py
annotation-template --output data/annotation.json` xuất review duy nhất cùng ID
nguồn. Mỗi người gán nhãn làm trên một bản sao riêng; không điền nhãn bằng dự
đoán SVM/PhoBERT hay điểm sao. Giữ file gốc để audit.

## ABSA

Với mỗi review, điền `labels` bằng tập con của 15 nhãn `aspect:POLARITY`.
Aspect gồm `food`, `price`, `service`, `ambience`, `location`; polarity gồm
`POSITIVE`, `NEUTRAL`, `NEGATIVE`. Chỉ gán khi văn bản thực sự nói đến khía
cạnh. Một review có thể có nhiều aspect và nhiều polarity của cùng aspect khi
có hai nhận xét đối lập. `[]` nghĩa là không có bằng chứng đủ rõ, không phải
review tiêu cực. Đặt `annotator` thành mã ẩn danh và `reviewed=true` sau khi
đọc review. Không sửa `restaurant_id`, `review_id`, `text`, ngày hay rating.

Hai người gán nhãn độc lập trên ít nhất một tập giao nhau. Dùng
`research.py agreement first.json second.json` để tính exact agreement và
Cohen kappa theo nhãn. Các bất đồng được đối chiếu và chốt thủ công trong bản
adjudicated; chỉ bản đó đi vào `prepare-gold`. Lệnh này khóa train/dev/test theo
nhà hàng và từ chối ghi đè split đã có. Với 13 nhà hàng hiện tại, cỡ mẫu và
độ cân bằng nhãn còn hạn chế; cần báo cáo độ phủ từng split.

## Retrieval và câu trả lời

Viết câu hỏi trước khi xem thứ hạng của các phương pháp. Người chấm độc lập
đánh dấu review liên quan bằng ID thật theo schema trong
`evaluation_queries.example.json`; không dùng kết quả BM25, dense hay hybrid
để tạo đáp án. Tách câu hỏi dev/test trước khi điều chỉnh retrieval. Chạy
`research.py evaluate-retrieval --queries ... --split test` chỉ sau khi khóa
judgments; báo cáo Recall@k, MRR, nDCG@k và latency cùng độ phủ.

Đánh giá câu trả lời RAG theo từng mệnh đề: người chấm xem review trích dẫn có
thực sự hỗ trợ mệnh đề hay không, ghi nhận gợi ý sai nhà hàng và trường hợp
đúng ra phải từ chối. Kiểm tra citation tự động chỉ xác minh ID hợp lệ và thuộc
đúng nhà hàng; nó **không** chứng minh mệnh đề đúng. Không gọi các con số tự động
là RAGAS/faithfulness nếu chưa chạy đúng bộ đo và kiểm tra mẫu thủ công.

## Khảo sát

`study_responses.example.csv` định nghĩa phiếu kết quả A/B gồm usefulness,
ease of use, trust, relevance, reuse intent, thang 1–5. Chỉ nhập dữ liệu sau
khi người tham gia đồng ý; dùng mã ẩn danh, không lưu tên/số điện thoại trong
repo. Cần phân bổ thứ tự điều kiện cân bằng và ghi nhận dropout. Lệnh
`research.py study-summary --input ...` chỉ tổng hợp phiếu thực đã nhập.
