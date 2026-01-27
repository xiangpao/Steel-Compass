import streamlit as st
import numpy as np
import base64

# --- 页面配置 ---
st.set_page_config(page_title="混凝土大师 RC-Master", layout="wide")

# 🔐 安全门卫
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ 未授权访问，请先登录！")
    st.stop()

st.title("🧱 混凝土大师 (RC-Master) | v1.2")

# --- 1. 交互侧边栏 ---
st.sidebar.header("1. 构件与参数")
calc_mode = st.sidebar.radio("选择构件类型", ("梁/板 (受弯/Beam)", "柱 (受压/Column)"), horizontal=True)

conc_grade = st.sidebar.selectbox("混凝土等级", ["C25", "C30", "C35", "C40"])
fc_map = {"C25": 11.9, "C30": 14.3, "C35": 16.7, "C40": 19.1} 
fc = fc_map[conc_grade]
fy = 360

st.sidebar.markdown("---")
st.sidebar.subheader("几何与荷载")

if "梁" in calc_mode:
    sub_type = st.sidebar.selectbox("子类型", ["矩形梁 (Lintel)", "板 (Slab)"])
    if sub_type == "矩形梁 (Lintel)":
        b = st.sidebar.number_input("梁宽 b (mm)", 200, step=50)
        h = st.sidebar.number_input("梁高 h (mm)", 400, step=50)
        bar_num = st.sidebar.number_input("钢筋根数", 3)
        bar_dia = st.sidebar.selectbox("钢筋直径", [10, 12, 14, 16, 20, 25], index=3)
        As = bar_num * (np.pi * (bar_dia/2)**2)
        cover = 25
    else:
        b = 1000
        h = st.sidebar.number_input("板厚 h (mm)", 120, step=10)
        bar_dia = st.sidebar.selectbox("钢筋直径", [8, 10, 12, 14], index=1)
        spacing = st.sidebar.number_input("间距 (mm)", 150, step=10)
        As = (1000 / spacing) * (np.pi * (bar_dia/2)**2)
        cover = 15

    h0 = h - cover - bar_dia/2
    span_L = st.sidebar.number_input("计算跨度 (m)", 3.0, step=0.1)
    q_design = st.sidebar.number_input("设计荷载 (kN/m或kN/m²)", 5.0, step=0.5)

    M_design = 1/8 * q_design * span_L**2
    x = (fy * As) / (1.0 * fc * b)
    Mu = fy * As * (h0 - x/2) / 1e6
    
    val_demand, val_cap = M_design, Mu
    unit = "kN.m"
    res_title = "受弯承载力"

else:
    col_type = st.sidebar.selectbox("截面形状", ["矩形柱 (Rect)", "圆柱 (Round)"])
    if "矩形" in col_type:
        b = st.sidebar.number_input("柱宽 b", 300)
        h = st.sidebar.number_input("柱深 h", 300)
        A_conc = b * h
        As = 4 * (np.pi * (16/2)**2) # 简化演示
    else:
        D = st.sidebar.number_input("直径 D", 300)
        A_conc = np.pi * (D/2)**2
        As = 6 * (np.pi * (16/2)**2)

    H_col = st.sidebar.number_input("计算高度 H0 (m)", 3.0)
    N_design = st.sidebar.number_input("轴压力 (kN)", 500.0)

    Nu = 0.9 * 0.9 * (fc * A_conc + fy * As) / 1000
    val_demand, val_cap = N_design, Nu
    unit = "kN"
    res_title = "轴压承载力"

# --- 🔥 这里就是向导代码 (已修复缩进) ---
st.sidebar.markdown("---")
with st.sidebar.expander("📌 场景选择向导"):
    st.markdown("""
    **我要算...**
    - 🪑 **混凝土坐凳** → 选 [梁/板] + [矩形梁]
    - 🌉 **小桥/栈道板** → 选 [梁/板] + [板]
    - 🌳 **树池/挡墙压顶** → 选 [梁/板] + [矩形梁]
    """)

# --- 3. 结果显示 ---
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader(f"📊 验算: {res_title}")
    ratio = val_demand / val_cap if val_cap > 0 else 999
    st.metric("需求", f"{val_demand:.1f} {unit}")
    st.metric("抗力", f"{val_cap:.1f} {unit}")
    
    if ratio <= 1.0: st.success(f"✅ 安全 (利用率 {ratio*100:.1f}%)")
    else: st.error("❌ 承载力不足")

with col2:
    st.subheader("📝 计算简报")
    st.write(f"类型: {calc_mode}")
    report = f"<h3>混凝土计算书</h3><p>{res_title}: {val_demand} vs {val_cap}</p>"
    b64 = base64.b64encode(report.encode()).decode()
    st.markdown(f'<a href="data:text/html;base64,{b64}" download="rc_report.html">📥 下载报告</a>', unsafe_allow_html=True)
