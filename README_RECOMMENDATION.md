# Recommendation model và thí nghiệm A–E

Hệ thống dùng bộ xếp hạng giải thích được; điểm không phải xác suất hài lòng.

- **A:** độ phổ biến Google (rating + log số review).
- **B:** A + sentiment của khía cạnh người dùng ưu tiên.
- **C:** B + độ khớp món ăn/hồ sơ/sở thích đã học.
- **D:** C + phản hồi thích/không hợp trong SQLite.
- **E:** D + độ phủ bằng chứng và gợi ý hợp lệ từ phiên chat gần nhất.

## Đánh giá trên Windows

Sao chép `recommendation_cases.example.json`, thay candidate và `relevant_restaurant_ids` bằng nhãn đánh giá thủ công, rồi chạy:

```bat
.venv\Scripts\python.exe evaluate_recommendation.py --cases recommendation_cases.json --k 3
```

Kết quả được ghi vào `outputs/recommendation_metrics.json`, gồm Recall@K, MRR và nDCG@K cho từng cấu hình. Dùng cùng tập test cho A–E; không chỉnh trọng số dựa trên tập test. Cấu hình E chỉ được coi là tốt hơn khi cải thiện metric trên dữ liệu gán nhãn.
