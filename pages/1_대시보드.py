import streamlit as st
import pandas as pd
from database import get_invoice_stats, get_invoices, get_vendors
from modules.mail_collector import run_full_pipeline

st.set_page_config(page_title="대시보드", page_icon="📊", layout="wide")
st.title("📊 대시보드")
st.markdown("---")

col_btn1, col_btn2, col_btn3, col_spacer = st.columns([1, 1, 1, 3])
with col_btn1:
    if st.button("🔄 지금 메일 수집 실행", type="primary", use_container_width=True):
        with st.spinner("메일을 수집하고 처리 중입니다..."):
            try:
                result = run_full_pipeline()
                st.success(f"✅ 완료: 신규 {result['new']}건 수집, "
                           f"결의서 {result['submitted']}건 생성, "
                           f"오류 {result['error']}건")
                if result.get('error_msg'):
                    st.warning(f"메시지: {result['error_msg']}")
            except Exception as e:
                st.error(f"오류 발생: {e}")
with col_btn2:
    if st.button("🔃 새로고침", use_container_width=True):
        st.rerun()
with col_btn3:
    if st.button("🛠️ 코드갱신+재실행", use_container_width=True):
        import subprocess, sqlite3, os
        with st.spinner("git pull 중..."):
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            r = subprocess.run(
                ["C:/Program Files/Git/bin/git.exe", "-C", base, "pull", "--rebase"],
                capture_output=True, text=True)
            st.code(r.stdout + r.stderr)
        with st.spinner("DB 초기화 중..."):
            db_path = os.path.join(base, "portal.db")
            con = sqlite3.connect(db_path)
            con.execute("DELETE FROM tax_invoices WHERE supplier_biz_no='0000000000' OR total_amount=0")
            con.commit(); con.close()
            st.success("DB 초기화 완료")
        with st.spinner("파이프라인 재실행 중..."):
            import importlib, sys
            if 'modules.mail_collector' in sys.modules:
                importlib.reload(sys.modules['modules.mail_collector'])
            from modules.mail_collector import run_full_pipeline as rfp
            try:
                res2 = rfp()
                st.success(f"✅ 재실행 완료: 신규 {res2['new']}건, 결의서 {res2['submitted']}건, 오류 {res2['error']}건")
                if res2.get('error_msg'):
                    st.warning(res2['error_msg'])
            except Exception as ex:
                st.error(str(ex))

st.markdown("---")

stats = get_invoice_stats()
vendors = get_vendors()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("📬 전체 처리", f"{stats['TOTAL']}건")
c2.metric("⏳ 대기 중", f"{stats['PENDING']}건", delta_color="off")
c3.metric("🔍 매칭됨", f"{stats['MATCHED']}건", delta_color="off")
c4.metric("✅ 결의서 생성", f"{stats['SUBMITTED']}건", delta_color="off")
c5.metric("⏭️ 스킵됨", f"{stats['SKIPPED']}건", delta_color="off")
c6.metric("❌ 오류", f"{stats['ERROR']}건", delta_color="off")

st.markdown("---")
st.subheader("📋 최근 처리 이력 (최근 20건)")

invoices = get_invoices(limit=20)
if invoices:
    df = pd.DataFrame(invoices)
    status_map = {
        "PENDING": "⏳ 대기",
        "MATCHED": "🔍 매칭됨",
        "SUBMITTED": "✅ 결의서생성",
        "SKIPPED": "⏭️ 스킵",
        "ERROR": "❌ 오류"
    }
    df["상태"] = df["status"].map(status_map)

    def fmt_amount(x):
        try:
            v = float(x)
            if v != v or v == 0:
                return "-"
            return f"{int(v):,}원"
        except:
            return "-"

    df["합계금액"] = df["total_amount"].apply(fmt_amount)
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

st.markdown("---")
st.subheader(f"🏢 등록된 매입처: {len(vendors)}개")
if vendors:
    df_v = pd.DataFrame(vendors)[["biz_number", "name", "category", "account_code"]]
    df_v.columns = ["사업자번호", "상호명", "분류", "계정과목"]
    st.dataframe(df_v, use_container_width=True, hide_index=True)
