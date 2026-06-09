import streamlit as st
from database import get_all_settings, set_setting

st.set_page_config(page_title="설정 관리", page_icon="⚙️", layout="wide")
st.title("⚙️ 설정 관리")
st.markdown("---")

settings = get_all_settings()

tab1, tab2, tab3 = st.tabs(["🔐 계정 설정", "🤖 AI/자동화 설정", "🕐 스케줄 설정"])

# ── 탭1: 계정 설정 ───────────────────────────────────────────
with tab1:
    st.subheader("🏢 KT 비즈오피스 (그룹웨어) 계정")
    with st.form("groupware_form"):
        gw_url = st.text_input("그룹웨어 URL",
            value=settings.get("groupware_url", ""))
        gw_id  = st.text_input("로그인 ID",
            value=settings.get("groupware_id", ""))
        gw_pw  = st.text_input("비밀번호",
            value=settings.get("groupware_pw", ""),
            type="password", help="비밀번호는 암호화되어 저장됩니다.")
        if st.form_submit_button("💾 저장", use_container_width=True):
            set_setting("groupware_url", gw_url)
            set_setting("groupware_id", gw_id)
            if gw_pw:
                set_setting("groupware_pw", gw_pw)
            st.success("그룹웨어 계정 저장 완료!")

    st.markdown("---")
    st.subheader("📋 KT 비즈메카 EZ 계정")
    with st.form("bizmeka_form"):
        bm_url = st.text_input("비즈메카 URL",
            value=settings.get("bizmeka_url", ""))
        bm_id  = st.text_input("로그인 ID",
            value=settings.get("bizmeka_id", ""))
        bm_pw  = st.text_input("비밀번호",
            value=settings.get("bizmeka_pw", ""),
            type="password")
        bm_company = st.text_input("회사 도메인 (예: openbase)",
            value=settings.get("bizmeka_company", ""))
        if st.form_submit_button("💾 저장", use_container_width=True):
            set_setting("bizmeka_url", bm_url)
            set_setting("bizmeka_id", bm_id)
            set_setting("bizmeka_company", bm_company)
            if bm_pw:
                set_setting("bizmeka_pw", bm_pw)
            st.success("비즈메카 계정 저장 완료!")

# ── 탭2: AI/자동화 설정 ─────────────────────────────────────
with tab2:
    with st.form("ai_form"):
        st.subheader("🤖 AI 파싱 설정")
        openai_key = st.text_input("OpenAI API Key",
            value=settings.get("openai_api_key", ""),
            type="password")
        mail_keyword = st.text_input("메일 검색 키워드",
            value=settings.get("mail_keyword", "세금계산서"),
            help="이 키워드가 포함된 메일만 처리합니다.")
        auto_submit = st.checkbox("결의서 자동 상신 (체크 해제 시 초안만 생성)",
            value=settings.get("auto_submit", "false") == "true")

        st.markdown("---")
        st.subheader("🧪 연결 테스트")
        col1, col2 = st.columns(2)

        if st.form_submit_button("💾 저장", use_container_width=True):
            set_setting("openai_api_key", openai_key)
            set_setting("mail_keyword", mail_keyword)
            set_setting("auto_submit", "true" if auto_submit else "false")
            st.success("AI 설정 저장 완료!")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔌 그룹웨어 연결 테스트", use_container_width=True):
            with st.spinner("연결 중..."):
                try:
                    from modules.mail_collector import test_connection
                    ok, msg = test_connection("groupware")
                    if ok: st.success(f"✅ 연결 성공: {msg}")
                    else:  st.error(f"❌ 연결 실패: {msg}")
                except Exception as e:
                    st.error(f"오류: {e}")
    with col2:
        if st.button("🔌 비즈메카 연결 테스트", use_container_width=True):
            with st.spinner("연결 중..."):
                try:
                    from modules.mail_collector import test_connection
                    ok, msg = test_connection("bizmeka")
                    if ok: st.success(f"✅ 연결 성공: {msg}")
                    else:  st.error(f"❌ 연결 실패: {msg}")
                except Exception as e:
                    st.error(f"오류: {e}")

# ── 탭3: 스케줄 설정 ─────────────────────────────────────────
with tab3:
    with st.form("schedule_form"):
        st.subheader("🕐 자동 실행 스케줄")
        interval = st.selectbox("실행 주기",
            ["10분", "30분", "1시간", "2시간", "4시간", "8시간", "매일 오전 9시"],
            index=["10분","30분","1시간","2시간","4시간","8시간","매일 오전 9시"].index(
                {"10":"10분","30":"30분","60":"1시간","120":"2시간",
                 "240":"4시간","480":"8시간","540":"매일 오전 9시"}.get(
                    settings.get("schedule_interval_min","60"), "1시간")
            )
        )
        interval_map = {
            "10분": "10", "30분": "30", "1시간": "60",
            "2시간": "120", "4시간": "240", "8시간": "480",
            "매일 오전 9시": "540"
        }
        enabled = st.checkbox("자동 실행 활성화",
            value=settings.get("schedule_enabled", "false") == "true")

        if st.form_submit_button("💾 저장", use_container_width=True):
            set_setting("schedule_interval_min", interval_map[interval])
            set_setting("schedule_enabled", "true" if enabled else "false")
            st.success(f"스케줄 설정 완료: {interval}마다 실행")

    st.info("⚠️ 자동 실행 기능은 서버 상시 가동 환경에서만 동작합니다. "
            "로컬 PC에서는 포탈이 켜져 있는 동안만 스케줄이 활성화됩니다.")