import joblib
import streamlit as st
from pipeline import OUT, ASPECTS, normalize, retrieve

st.title('Vietnamese Food Reviews — research baseline')
st.caption('ViTASA Restaurant • Không có địa chỉ hoặc thời gian đánh giá')
st.warning('Đây là demo ABSA và tìm bằng chứng bằng TF-IDF; chưa phải chatbot LLM/RAG hoàn chỉnh.')
text = st.text_area('Nhập đánh giá hoặc câu hỏi', 'Món ăn ngon nhưng nhân viên phục vụ chậm')
if st.button('Phân tích'):
    if not text.strip():
        st.error('Vui lòng nhập nội dung.'); st.stop()
    path = OUT/'baseline.joblib'
    if not path.exists():
        st.error('Chạy setup_windows.bat trước.'); st.stop()
    # Only load the locally trained artifact; never load an untrusted joblib file.
    bundle = joblib.load(path)
    pred = bundle['model'].predict(bundle['vectorizer'].transform([normalize(text)]))[0]
    labels = [c for c,v in zip(bundle['classes'],pred) if v]
    st.write('Nhãn dự đoán:',labels or 'Không phát hiện khía cạnh')
    st.caption('Có thể xuất hiện nhiều cực tính cho cùng khía cạnh. SVM chưa được hiệu chỉnh xác suất.')
    st.subheader('Review liên quan trong tập train')
    for row in retrieve(normalize(text)):
        st.write(f"Review {row['id']} · lexical score {row['score']:.3f}")
        st.write(row['text'])
    st.info('Không thể kết luận xu hướng hoặc đề xuất địa điểm cụ thể từ bộ dữ liệu này.')
