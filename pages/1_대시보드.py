import streamlit as st
import pandas as pd
from database import get_invoice_stats, get_invoices, get_vendors
from modules.mail_collector import run_full_pipeline  # 다음 단계 구현

st.set_page_config(page_title="대시보드", page_icon="📊", layout="wide")
st.title("📊 대시보드")
st.markdown("---")

# ── 수동 실행 버튼 ──────────────────────────────────────────
col_btn1, col_btn2, col_spacer = st.columns([1, 1, 4])
with col_btn1:
    if st.button("🔄 지금 메일 수집 실행", type="primary", use_container_width=True):
        with st.spinner("메일을 수집하고 처리 중입니다..."):
            try:
                result = run_full_pipeline()
                st.success(f"✅ 완료: 신규 {result['new']}건 수집, "
                           f"결의서 {result['submitted']}건 생성, "
                           f"오류 {result['error']}건")
            except Exception as e:
                st.error(f"오류 발생: {e}")
with col_btn2:
    if st.button("🔃 새로고침", use_container_width=True):
        st.rerun()

st.markdown("---")

# ── 통계 카드 ────────────────────────────────────────────────
stats = get_invoice_stats()
vendors = get_vendors()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("📬 전체 처리", f"{stats['TOTAL']}건")
c2.metric("⏳ 대기 중",   f"{stats['PENDING']}건",  delta_color="off")
c3.metric("🔍 매칭됨",   f"{stats['MATCHED']}건",  delta_color="off")
c4.metric("✅ 결의서 생성", f"{stats['SUBMITTED']}건", delta_color="off")
c5.metric("⏭️ 스킵됨",   f"{stats['SKIPPED']}건",  delta_color="off")
c6.metric("❌ 오류",      f"{stats['ERROR']}건",    delta_color="off")

st.markdown("---")

# ── 최근 처리 이력 ─────────────────────────────────────────
st.subheader("📋 최근 처리 이력 (최근 20건)")

invoices = get_invoices(limit=20)
if invoices:
    df = pd.DataFrame(invoices)
    # 상태 한글 변환
    status_map = {
        "PENDING": "⏳ 대기",
        "MATCHED": "🔍 매칭됨",
        "SUBMITTED": "✅ 결의서생성",
        "SKIPPED": "⏭️ 스킵",
        "ERROR": "❌ 오류"
    }
    df["상태"] = df["status"].map(status_map)
    df["합계금액"] = df["total_amount"].apply(
        lambda x: f"{int(x):,}원" if x else "-"
    )
    display_cols = {
        "issue_date": "발행일",
        "supplier_name": "공급자명",
        "supplier_biz_no": "사업자번호",
        "item_name": "품목",
        "합계금액": "합계금액",
        "상태": "상태",
        "result_memo": "처리메모",
        "created_at": "수집일시"
    }
    df_show = df.rename(columns=display_cols)[list(display_cols.values())]
    st.dataframe(df_show, use_container_width=True, hide_index=True)
else:
    st.info("아직 처리된 세금계산서가 없습니다. '지금 메일 수집 실행' 버튼을 눌러보세요.")

# ── 매입처 현황 ─────────────────────────────────────────────
st.markdown("---")
st.subheader(f"🏢 등록된 매입처: {len(vendors)}개")
if vendors:
    df_v = pd.DataFrame(vendors)[["biz_number", "name", "category", "account_code"]]
    df_v.columns = ["사업자번호", "상호명", "분류", "계정과목"]
    st.dataframe(df_v, use_container_width=True, hide_index=True)