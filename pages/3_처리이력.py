import streamlit as st
import pandas as pd
from database import get_invoices, update_invoice_status

st.set_page_config(page_title="처리 이력", page_icon="📋", layout="wide")
st.title("📋 처리 이력")
st.markdown("---")

# 필터
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    status_filter = st.selectbox("상태 필터", [
        "전체", "⏳ 대기(PENDING)", "🔍 매칭됨(MATCHED)",
        "✅ 결의서생성(SUBMITTED)", "⏭️ 스킵(SKIPPED)", "❌ 오류(ERROR)"
    ])
with col2:
    limit = st.selectbox("표시 건수", [50, 100, 200, 500], index=1)
with col3:
    search = st.text_input("🔍 공급자명 또는 사업자번호 검색")

status_map_rev = {
    "전체": None,
    "⏳ 대기(PENDING)": "PENDING",
    "🔍 매칭됨(MATCHED)": "MATCHED",
    "✅ 결의서생성(SUBMITTED)": "SUBMITTED",
    "⏭️ 스킵(SKIPPED)": "SKIPPED",
    "❌ 오류(ERROR)": "ERROR"
}
selected_status = status_map_rev[status_filter]

invoices = get_invoices(status=selected_status, limit=limit)
if search:
    invoices = [i for i in invoices if search in (i.get("supplier_name") or "")
                or search in (i.get("supplier_biz_no") or "")]

if invoices:
    df = pd.DataFrame(invoices)
    status_label = {
        "PENDING": "⏳ 대기",
        "MATCHED": "🔍 매칭됨",
        "SUBMITTED": "✅ 결의서생성",
        "SKIPPED": "⏭️ 스킵",
        "ERROR": "❌ 오류"
    }
    df["상태"] = df["status"].map(status_label)
    df["공급가액"] = df["supply_amount"].apply(lambda x: f"{int(x):,}" if (x and x == x and x != 0) else "-")
    df["세액"]    = df["tax_amount"].apply(lambda x: f"{int(x):,}" if (x and x == x and x != 0) else "-")
    df["합계금액"] = df["total_amount"].apply(lambda x: f"{int(x):,}" if (x and x == x and x != 0) else "-")

    display = df[[
        "id", "issue_date", "supplier_name", "supplier_biz_no",
        "item_name", "공급가액", "세액", "합계금액",
        "상태", "bizmeka_doc_no", "result_memo", "created_at"
    ]].rename(columns={
        "id": "ID", "issue_date": "발행일",
        "supplier_name": "공급자명", "supplier_biz_no": "사업자번호",
        "item_name": "품목", "bizmeka_doc_no": "결의서번호",
        "result_memo": "처리메모", "created_at": "수집일시"
    })

    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(f"총 {len(invoices)}건 표시")

    # 수동 상태 변경
    st.markdown("---")
    st.subheader("🛠️ 처리 상태 수동 변경")
    with st.form("manual_status_form"):
        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            inv_id = st.number_input("이력 ID", min_value=1, step=1)
        with col_b:
            new_status = st.selectbox("변경할 상태",
                ["PENDING", "MATCHED", "SUBMITTED", "SKIPPED", "ERROR"])
        with col_c:
            new_memo = st.text_input("메모")
        if st.form_submit_button("변경 적용"):
            update_invoice_status(int(inv_id), new_status, new_memo)
            st.success(f"ID {inv_id} 상태를 {new_status}로 변경했습니다.")
            st.rerun()
else:
    st.info("조건에 맞는 처리 이력이 없습니다.")
