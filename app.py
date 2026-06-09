import streamlit as st
from database import init_db

# DB 초기화
init_db()

st.set_page_config(
    page_title="세금계산서 자동처리 포탈",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 사이드바 스타일
st.markdown("""
<style>
    [data-testid="stSidebarNav"] { font-size: 16px; }
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        border: 1px solid #dee2e6;
    }
    .status-submitted { color: #28a745; font-weight: bold; }
    .status-pending   { color: #ffc107; font-weight: bold; }
    .status-error     { color: #dc3545; font-weight: bold; }
    .status-skipped   { color: #6c757d; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("🧾 세금계산서 자동 지출결의서 포탈")
st.markdown("---")
st.info("👈 왼쪽 메뉴에서 원하는 기능을 선택하세요.")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### 📊 대시보드")
    st.write("처리 현황 및 최근 이력을 한눈에 확인합니다.")
with col2:
    st.markdown("### 🏢 매입처 관리")
    st.write("자동 처리할 매입처 사업자번호와 정보를 등록/관리합니다.")
with col3:
    st.markdown("### ⚙️ 설정 관리")
    st.write("그룹웨어 및 비즈메카 계정, 스케줄 등을 설정합니다.")