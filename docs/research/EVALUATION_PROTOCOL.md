# Đánh giá bổ sung FoodLens — 19/09/2026

## Phân biệt mục tiêu và kết quả

80–85% là mục tiêu cần chỉ rõ micro-F1 hay macro-F1, không phải mức có thể bảo đảm
trước thực nghiệm. Giữ SVM trong app cho đến khi có so sánh trên cùng tập đánh giá,
macro-F1 tốt hơn và độ trễ chấp nhận được. Không dùng sao toàn review làm nhãn
cảm xúc cho mọi khía cạnh; không dùng nhãn AI làm gold độc lập.

## Benchmark ViTASA

Giữ 1.398/200/400 review train/dev/test và SHA-256 trong báo cáo. Chọn cấu hình
bằng dev, không chọn bằng test. Test này đã được xem trong các lần báo cáo trước,
nên phải công bố giới hạn đó. Báo cả micro-F1, macro-F1 của 15 cặp nhãn, ACD-F1,
support từng lớp và khoảng tin cậy. Bootstrap 2.000 lần theo review không thay
thế được bootstrap theo nhà hàng vì nguồn chuyển đổi không có ID nhà hàng.

PhoBERT-base: hai đầu ra ACD (5) và SPC (5 × 3), BCE có mask cho các aspect được
nhắc đến; hỗ trợ review có nhiều sắc thái trên cùng aspect. Tokenization hiện dùng
underthesea, khác bộ phân đoạn VnCoreNLP được tác giả PhoBERT khuyến nghị.
Không công bố điểm trước khi có `metrics.json` từ một lượt chạy hoàn tất.

## Gold trong miền ứng dụng

`python -m scripts.prepare_evaluation_pack` tạo hai phiếu độc lập trong `data/`.
Bản hiện tại lấy 290 review từ 30 nhà hàng có ít nhất 8 review khác nhau,
ẩn sao và nhãn máy. Đây là mẫu thuận tiện, không đại diện toàn thành phố.

- Hai người đọc độc lập từng review và gán các cặp aspect–sentiment thực sự xuất hiện.
- `labels: []` nghĩa là đã đọc nhưng không có khía cạnh phù hợp; `null` là chưa làm.
- Chỉ đặt `reviewed: true` sau khi người gán nhãn thực sự kiểm tra; ghi tên/mã người gán.
- Tính agreement trước adjudication, lưu cả nhãn gốc và quyết định giải quyết bất đồng.
- Giữ nguyên 10 nhóm nhà hàng dev và 20 nhóm test trong manifest, không shuffle lại.
- Không đưa review từ các nhà hàng dành cho đánh giá vào tập tăng cường huấn luyện mới.
  Nếu đã từng dùng trước đó, phải loại giao nhau hoặc chọn nhóm hoàn toàn mới,
  công bố lịch sử tiếp xúc dữ liệu; việc tạo phiếu không tự biến chúng thành test độc lập.

Không đưa trực tiếp bộ phiếu này qua `research prepare-gold`, vì lệnh đó có quy trình
chia tập riêng. Chỉ xuất tập đánh giá sau khi xác nhận review đã được kiểm tra và
phân hoạch trong manifest được giữ nguyên.

## Retrieval và RAG

20 câu hỏi Việt/Anh được tách 6 dev, 14 test. Script `retrieval_diagnostics` chạy
BM25, E5 và hybrid trên cùng database, không fallback, và tạo pool hợp nhất top-5
đã xáo thứ tự. File private mapping không đưa cho người đánh giá.

Chấm từng tài liệu: 0 không phù hợp, 1 phù hợp một phần, 2 phù hợp trực tiếp;
kiểm tra món ăn, khu vực và nhu cầu cụ thể, không suy ra relevance từ thứ hạng máy.
Pool top-5 không bao phủ toàn corpus: khi dùng Recall phải gọi rõ là pooled recall
và công bố độ sâu pool. Muốn Recall toàn corpus cần judgments rộng hơn.

Với RAG, tách câu trả lời thành các mệnh đề và ghi supported/unsupported/unclear
dựa trên review được dẫn. Citation ID hợp lệ hoặc thuộc đúng nhà hàng không đủ
chứng minh mệnh đề đúng. Báo tỷ lệ từ chối và mức coverage cùng faithfulness.

## Kiểm tra ứng dụng và khảo sát

`python -m scripts.smoke_real_app --target <database-copy>` dùng bản sao DB thật,
tắt API và giả lập provider lỗi để kiểm tra ứng dụng vẫn trả bằng chứng lưu sẵn.
Không sửa tài khoản, lịch sử hay hồ sơ trên database đang chạy.

Chưa có người tham gia khảo sát: để trống kết quả satisfaction/usability.
Thu thập đồng ý tham gia, phân nhóm/counterbalance thứ tự tác vụ, ghi thời gian,
tỷ lệ hoàn thành và phản hồi người dùng; không điền phản hồi thay người tham gia.

## Lệnh tái lập

Chạy tại root với Python của `.venv`:

```powershell
python -m scripts.research_validation
python -m scripts.prepare_evaluation_pack --output data/evaluation_new
python -m scripts.retrieval_diagnostics --pack data/evaluation_new
python src/train_phobert_multitask.py --backbone vinai/phobert-base --batch-size 2 --accumulation 8 --threads 4 --cpu
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m unittest discover -s tests
```

Không chạy E5 và fine-tuning đồng thời trên máy 16 GB RAM. Lưu model/backup lớn
ở ổ E; nguồn code và báo cáo tổng hợp được version-control, dữ liệu và key không commit.
