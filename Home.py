import streamlit as st

# --- 页面配置 ---
st.set_page_config(
    page_title="景观工程结构助手 V1.0",
    page_icon="🏗️",
    layout="centered", # 首页居中显示更像封面
    initial_sidebar_state="expanded"
)

# --- 0. 登录门卫 (全局守门员) ---
# 这是一个高级技巧：一旦在首页登录，Session状态会传递给所有子页面
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

def login_screen():
    st.title("🔐 景观结构助手 | 登录")
    st.info("SBM-Fusion 内部工具系统")
    password = st.text_input("请输入访问密钥 (Access Key)", type="password")
    
    # 🛒 模拟验证
    if st.button("进入系统"):
        valid_codes = ["VIP888", "SBM2026", "NB01"]
        if password in valid_codes:
            st.session_state.logged_in = True
            st.success("验证成功！")
            st.rerun()
        else:
            st.error("密钥错误")

if not st.session_state.logged_in:
    login_screen()
    st.stop() # ⛔ 没登录不许往下走

# --- 主界面 (登录后可见) ---
st.title("🏗️ 景观结构工程助手 (L-SE Suite)")
st.markdown("### Landscape Structural Engineering Suite")
st.markdown("---")

st.info("👋 欢迎回来，工程师。请从左侧侧边栏选择计算模块，或点击下方卡片。")

# --- 导航卡片 ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔩 结构罗盘 (Steel)")
    st.markdown("""
    *轻型钢结构估算*
    - **适用**: 廊架、景亭、精神堡垒
    - **功能**: 简支/悬挑梁、应力挠度验算
    - **材质**: Q235B / Q355B
    """)
    st.success("👈 请点击左侧 **1_Steel_Compass**")

with col2:
    st.subheader("🧱 混凝土大师 (RC)")
    st.markdown("""
    *小型钢筋混凝土构件*
    - **适用**: 坐凳、种植池壁、小跨度板
    - **功能**: 配筋计算、裂缝控制、超筋预警
    - **材质**: C30+HRB400
    """)
    st.success("👈 请点击左侧 **2_RC_Master**")

st.markdown("---")
st.caption("Version 1.0 | Limit State Design | Powered by SBM-Fusion")
