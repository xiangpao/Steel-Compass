import streamlit as st

st.set_page_config(page_title="景观工程结构助手", layout="wide")

# --- 0. 登录逻辑 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

def login_screen():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 系统登录")
        pwd = st.text_input("Access Key", type="password")
        if st.button("登录"):
            if pwd in ["VIP888", "SBM2026"]: # 你的密码库
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("密码错误")

if not st.session_state.logged_in:
    login_screen()
    st.stop() 

# --- 侧边栏：显示用户信息 & 退出按钮 ---
with st.sidebar:
    st.success("✅ 已登录")
    if st.button("🚪 退出系统 (Logout)"):
        st.session_state.logged_in = False
        st.rerun() # 刷新页面，瞬间回到登录界面

# --- 主内容区 (不变) ---
st.title("🏗️ 景观结构工程助手")
# ... (保留你之前的三个模块导航代码) ...
