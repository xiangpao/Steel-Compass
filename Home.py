import streamlit as st

# --- 1. 页面基础配置 ---
st.set_page_config(
    page_title="景观工程结构助手 V1.2",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. 安全门卫系统 (Security) ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

def login_screen():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True) # 增加一点顶部留白
        st.title("🔐 SBM 结构助手 | 登录")
        st.info("Landscape Engineering Suite V1.2")
        
        # 密码输入框
        password = st.text_input("请输入访问密钥 (Access Key)", type="password")
        
        if st.button("🚀 进入系统"):
            # === 🔑 密码库 (在此管理你的卖号密码) ===
            valid_codes = ["VIP888", "SBM2026", "NB01", "TRIAL"]
            # ======================================
            
            if password in valid_codes:
                st.session_state.logged_in = True
                st.toast("✅ 验证成功！正在进入...", icon="🎉")
                st.rerun()
            else:
                st.error("❌ 密钥错误，请检查或联系作者。")

# 如果没登录，显示登录页并停止向下运行
if not st.session_state.logged_in:
    login_screen()
    st.stop()

# --- 3. 侧边栏 (登录后可见) ---
with st.sidebar:
    st.success("👤 状态：已登录 (VIP)")
    st.markdown("---")
    st.write("如需切换账号或离开：")
    if st.button("🚪 退出系统 (Logout)", type="primary"):
        st.session_state.logged_in = False
        st.rerun()

# --- 4. 主仪表盘 (Dashboard) ---
st.title("🏗️ 景观结构工程助手 (L-SE Suite)")
st.caption("Landscape Structural Engineering System | Powered by SBM-Fusion")
st.markdown("---")

st.subheader("🛠️ 选择计算模块 (Select Module)")

# === 三列布局：核心入口 ===
col1, col2, col3 = st.columns(3)

# 🟢 模块 1: 构件罗盘
with col1:
    st.info("1️⃣ 零件级 | Component")
    st.subheader("🔩 构件罗盘 (Steel)")
    st.markdown("""
    *轻型钢结构快速估算*
    - **适用**: 檩条、次梁、精神堡垒、悬挑
    - **模式**: 梁(受弯) / 柱(受压)
    - **输出**: 强度 + 挠度 + 长细比
    """)
    # 这里的路径必须和你 pages 文件夹里的文件名一模一样
    st.page_link("pages/1_Steel_Compass.py", label="🚀 启动 构件罗盘", icon="🔩", use_container_width=True)

# 🔵 模块 2: 整体刚架
with col2:
    st.info("2️⃣ 系统级 | System")
    st.subheader("⛩️ 整体刚架 (Frame)")
    st.markdown("""
    *梁柱整体受力分析*
    - **适用**: 刚接廊架、景亭、门楼主结构
    - **核心**: 门式刚架 (位移法)
    - **输出**: 节点弯矩 + 柱压弯验算
    """)
    st.page_link("pages/3_Frame_System.py", label="🚀 启动 整体刚架", icon="⛩️", use_container_width=True)

# 🟠 模块 3: 混凝土
with col3:
    st.info("3️⃣ 混凝土 | Concrete")
    st.subheader("🧱 混凝土大师 (RC)")
    st.markdown("""
    *钢筋混凝土配筋*
    - **适用**: 坐凳、树池、地库顶板、过水板
    - **模式**: 梁 / 板 / 柱
    - **输出**: 配筋量 + 裂缝/超筋预警
    """)
    st.page_link("pages/2_RC_Master.py", label="🚀 启动 混凝土大师", icon="🧱", use_container_width=True)

# --- 5. 底部帮助区 ---
st.markdown("---")
with st.expander("📖 新手指南：如何选择工具？"):
    st.markdown("""
    - **做廊架/亭子主结构** 👉 请用 **[整体刚架]** (算柱子和主梁)
    - **做廊架顶上的玻璃檩条** 👉 请用 **[构件罗盘]** (算次梁)
    - **做单独的导视牌/景墙钢骨架** 👉 请用 **[构件罗盘]**
    - **做混凝土坐凳/种植池** 👉 请用 **[混凝土大师]**
    """)
