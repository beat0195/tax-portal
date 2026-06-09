import streamlit as st
import pandas as pd
from database import get_vendors, add_vendor, update_vendor, delete_vendor

st.set_page_config(page_title="매입처 관리", page_icon="🏢", layout="wide")
st.title("🏢 매입처 관리")
st.markdown("매입처 리스트에 등록된 업체의 세금계산서만 자동으로 지출결의서가 생성됩니다.")
st.markdown("---")

tab1, tab2 = st.tabs(["📋 매입처 목록", "➕ 신규 등록"])

# ── 탭1: 목록 ────────────────────────────────────────────────
with tab1:
    vendors = get_vendors(active_only=False)
    if vendors:
        df = pd.DataFrame(vendors)
        df["is_active"] = df["is_active"].map({1: "✅ 활성", 0: "❌ 비활성"})
        df_show = df[["id", "biz_number", "name", "category",
                      "account_code", "memo", "is_active", "created_at"]]
        df_show.columns = ["ID", "사업자번호", "상호명", "분류",
                           "계정과목", "메모", "상태", "등록일"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("✏️ 매입처 수정/삭제")

        vendor_options = {f"[{v['biz_number']}] {v['name']}": v for v in vendors}
        selected_label = st.selectbox("수정할 매입처 선택", list(vendor_options.keys()))
        sel = vendor_options[selected_label]

        with st.form("edit_vendor_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_name     = st.text_input("상호명",    value=sel["name"])
                new_category = st.text_input("분류",      value=sel["category"] or "")
            with col2:
                new_account  = st.text_input("계정과목",  value=sel["account_code"] or "")
                new_active   = st.checkbox("활성",        value=bool(sel["is_active"]))
            new_memo = st.text_area("메모", value=sel["memo"] or "")

            c1, c2 = st.columns(2)
            with c1:
                save = st.form_submit_button("💾 저장", use_container_width=True)
            with c2:
                delete = st.form_submit_button("🗑️ 비활성화", use_container_width=True)

            if save:
                update_vendor(sel["id"], new_name, new_category,
                              new_account, new_memo, new_active)
                st.success("저장되었습니다.")
                st.rerun()
            if delete:
                delete_vendor(sel["id"])
                st.warning("비활성화되었습니다.")
                st.rerun()
    else:
        st.info("등록된 매입처가 없습니다. '신규 등록' 탭에서 추가하세요.")

# ── 탭2: 신규 등록 ───────────────────────────────────────────
with tab2:
    st.subheader("➕ 매입처 신규 등록")

    # 엑셀 일괄 업로드
    with st.expander("📥 엑셀로 일괄 등록"):
        st.markdown("사업자번호, 상호명, 분류, 계정과목, 메모 컬럼이 있는 엑셀(.xlsx) 파일을 업로드하세요.")
        uploaded = st.file_uploader("엑셀 파일 업로드", type=["xlsx"])
        if uploaded:
            df_up = pd.read_excel(uploaded)
            st.dataframe(df_up, use_container_width=True)
            if st.button("📥 일괄 등록 실행"):
                success, fail = 0, 0
                for _, row in df_up.iterrows():
                    ok, _ = add_vendor(
                        str(row.get("사업자번호", "")),
                        str(row.get("상호명", "")),
                        str(row.get("분류", "")),
                        str(row.get("계정과목", "")),
                        str(row.get("메모", ""))
                    )
                    if ok: success += 1
                    else:  fail += 1
                st.success(f"등록 완료: {success}건 성공, {fail}건 중복/실패")
                st.rerun()

    st.markdown("---")

    # 개별 등록 폼
    with st.form("add_vendor_form"):
        col1, col2 = st.columns(2)
        with col1:
            biz_no   = st.text_input("사업자번호 *", placeholder="000-00-00000")
            name     = st.text_input("상호명 *",     placeholder="(주)예시회사")
        with col2:
            category = st.text_input("분류",         placeholder="IT장비, 소모품, 외주용역 등")
            account  = st.text_input("계정과목",     placeholder="복리후생비, 소모품비 등")
        memo = st.text_area("메모", placeholder="추가 참고사항")
        submitted = st.form_submit_button("✅ 등록", type="primary", use_container_width=True)

        if submitted:
            biz_no_clean = biz_no.replace("-", "").strip()
            if not biz_no_clean or not name:
                st.error("사업자번호와 상호명은 필수입니다.")
            else:
                ok, msg = add_vendor(biz_no_clean, name, category, account, memo)
                if ok:
                    st.success(f"✅ '{name}' 등록 완료!")
                    st.rerun()
                else:
                    st.error(msg)