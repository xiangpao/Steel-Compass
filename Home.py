import streamlit as st

# --- 页面配置 ---
st.set_page_config(
    page_title="景观工程结构助手 V1.1",
    page_icon="🏗️",
    layout="wide", # 升级为宽屏模式，因为有3个卡片
    initial_sidebar_state="expanded"
)

# --- 0. 登录门卫 (全局守门员) ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

def login_screen():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 SBM 结构助手 | 登录")
        st.info("Landscape Engineering Suite V1.1")
        password = st.text_input("请输入访问密钥 (Access Key)", type="password")
        
        if st.button("🚀 进入系统"):
            # 在此处设置你的密码库
            valid_codes = ["VIP888", "SBM2026", "NB01", "TRIAL"]
            if password in valid_codes:
                st.session_state.logged_in = True
                st.toast("验证成功！正在进入...")
                st.rerun()
            else:
                st.error("密钥错误，请重试。")

if not st.session_state.logged_in:
    login_screen()
    st.stop() 

# --- 主界面 (登录后可见) ---
st.title("🏗️ 景观结构工程助手 (L-SE Suite)")
st.caption("Landscape Structural Engineering System | Powered by SBM-Fusion")
st.markdown("---")

# --- 顶部：工具导航 ---
st.subheader("🛠️ 选择计算模块 (Select Module)")

# 使用 3 列布局
col1, col2, col3 = st.columns(3)

with col1:
    st.info("1️⃣ 零件级")
    st.subheader("🔩 构件罗盘 (Steel)")
    st.markdown("""
    **功能**: 单根梁/柱的快速估算
    - **适用**: 檩条、次梁、单独的悬臂、精神堡垒
    - **核心**: 简支/悬挑模型
    - **输出**: 强度 + 挠度 + 长细比
    """)
    st.markdown("👉 [点击左侧 **1_Steel_Compass** 启动](#)")

with col2:
    st.info("2️⃣ 系统级")
    st.subheader("⛩️ 整体刚架 (Frame)")
    st.markdown("""
    **功能**: 梁柱整体受力分析
    - **适用**: 刚接廊架、景亭、门楼主结构
    - **核心**: 门式刚架 (位移法)
    - **输出**: 节点弯矩 + 柱压弯验算
    """)
    st.markdown("👉 [点击左侧 **3_Frame_System** 启动](#)")

with col3:
    st.info("3️⃣ 混凝土")
    st.subheader("🧱 混凝土大师 (RC)")
    st.markdown("""
    **功能**: 钢筋混凝土配筋
    - **适用**: 坐凳、树池、地库顶板、过水板
    - **核心**: 适筋梁理论
    - **输出**: 配筋量 + 裂缝/超筋预警
    """)
    st.markdown("👉 [点击左侧 **2_RC_Master** 启动](#)")

# --- 底部：使用指南 ---
st.markdown("---")
with st.expander("📖 新手必读：应该用哪个工具？"):
    st.markdown("""
    #### 场景 A：我要做一个 4米跨的钢廊架
    1. **先用 [整体刚架]**: 输入跨度4m，柱高3m。算出 **主梁和主柱** 的规格（比如梁200x100，柱150x150）。
    2. **再用 [构件罗盘]**: 廊架顶上要铺玻璃，下面要有次龙骨（檩条）。输入跨度（主梁间距），算出 **檩条** 规格（比如50x50）。
    
    #### 场景 B：我要做一个悬挑的导视牌
    * 直接用 **[构件罗盘]** -> 切换到 **柱模式** 算立柱 -> 切换到 **悬挑梁** 算挑臂。
    
    #### 场景 C：我要做一个 5米长的混凝土坐凳
    * 直接用 **[混凝土大师]** -> 矩形梁模式。
    """)
