import streamlit as st
import numpy as np
import base64

# --- 页面配置 ---
st.set_page_config(page_title="混凝土大师 RC-Master", layout="wide")

# 🔐 子页面门卫 (防止直接通过URL访问)
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ 请从首页登录系统")
    st.stop() # 强制停止

st.title("🧱 混凝土大师 (RC-Master) | v1.1")

# --- 1. 交互侧边栏 ---
st.sidebar.header("1. 构件与参数")

# 1.1 构件类型切换
calc_mode = st.sidebar.radio("选择构件类型", ("梁/板 (受弯/Beam)", "柱 (受压/Column)"), horizontal=True)

# 1.2 材料强度 (GB 50010)
conc_grade = st.sidebar.selectbox("混凝土等级", ["C25", "C30", "C35", "C40"])
fc_map = {"C25": 11.9, "C30": 14.3, "C35": 16.7, "C40": 19.1} 
ft_map = {"C25": 1.27, "C30": 1.43, "C35": 1.57, "C40": 1.71}
fc = fc_map[conc_grade]
ft = ft_map[conc_grade]

fy = 360 # HRB400
st.sidebar.caption(f"设计值: {conc_grade}(fc={fc}), HRB400(fy={fy})")

# --- 2. 几何与荷载 (根据模式变化) ---
st.sidebar.markdown("---")
st.sidebar.subheader("几何与荷载")

if "梁" in calc_mode:
    # === 梁板模式 (原有逻辑) ===
    sub_type = st.sidebar.selectbox("子类型", ["矩形梁 (Lintel)", "板 (Slab)"])
    
    if sub_type == "矩形梁 (Lintel)":
        b = st.sidebar.number_input("梁宽 b (mm)", 200, step=50)
        h = st.sidebar.number_input("梁高 h (mm)", 400, step=50)
        st.sidebar.subheader("配筋 (底筋)")
        bar_num = st.sidebar.number_input("钢筋根数", 3)
        bar_dia = st.sidebar.selectbox("钢筋直径", [10, 12, 14, 16, 18, 20, 22, 25], index=3)
        As = bar_num * (np.pi * (bar_dia/2)**2)
        cover = 25
    else:
        b = 1000
        h = st.sidebar.number_input("板厚 h (mm)", 120, step=10)
        st.sidebar.subheader("配筋 (板底)")
        bar_dia = st.sidebar.selectbox("钢筋直径", [8, 10, 12, 14], index=1)
        spacing = st.sidebar.number_input("间距 (mm)", 150, step=10)
        As = (1000 / spacing) * (np.pi * (bar_dia/2)**2)
        cover = 15

    h0 = h - cover - bar_dia/2
    span_L = st.sidebar.number_input("计算跨度 (m)", 3.0, step=0.1)
    q_design = st.sidebar.number_input("设计荷载 (kN/m或kN/m²)", 5.0, step=0.5)

    # 计算逻辑
    M_design = 1/8 * q_design * span_L**2
    x = (fy * As) / (1.0 * fc * b)
    xi = x / h0
    xi_b = 0.518
    rho = As / (b * h)
    rho_min = max(0.2/100, 0.45 * ft / fy)
    Mu = fy * As * (h0 - x/2) / 1e6
    
    # 结果变量打包
    val_demand, val_cap = M_design, Mu
    unit = "kN.m"
    res_title = "受弯承载力"

else:
    # === 柱模式 (新增逻辑) ===
    col_type = st.sidebar.selectbox("截面形状", ["矩形柱 (Rect)", "圆柱 (Round)"])
    
    if "矩形" in col_type:
        b = st.sidebar.number_input("柱宽 b (mm)", 300, step=50)
        h = st.sidebar.number_input("柱深 h (mm)", 300, step=50)
        A_conc = b * h
        st.sidebar.subheader("纵向钢筋 (全部)")
        bar_total_num = st.sidebar.number_input("总根数 (4根以上)", 4, step=2)
        bar_dia = st.sidebar.selectbox("钢筋直径", [12, 14, 16, 18, 20, 22, 25], index=2)
        As = bar_total_num * (np.pi * (bar_dia/2)**2)
    else:
        D = st.sidebar.number_input("柱直径 D (mm)", 300, step=50)
        A_conc = np.pi * (D/2)**2
        st.sidebar.subheader("纵向钢筋 (全部)")
        bar_total_num = st.sidebar.number_input("总根数 (6根以上)", 6, step=1)
        bar_dia = st.sidebar.selectbox("钢筋直径", [12, 14, 16, 18, 20, 22, 25], index=2)
        As = bar_total_num * (np.pi * (bar_dia/2)**2)

    H_col = st.sidebar.number_input("计算高度 H0 (m)", 3.0, step=0.1)
    N_design = st.sidebar.number_input("轴压力设计值 (kN)", 500.0, step=50.0, help="1.3恒+1.5活")

    # 柱计算逻辑 (GB 50010 - 轴心受压简化)
    # 稳定系数 phi
    # 矩形回转半径 i = h / sqrt(12) ≈ 0.289h
    # 圆形回转半径 i = d / 4 = 0.25d
    if "矩形" in col_type:
        i_radius = min(b, h) * 0.289
        size_min = min(b, h)
    else:
        i_radius = D * 0.25
        size_min = D
        
    l0_i = (H_col * 1000) / i_radius # 长细比
    
    # 查表法拟合 phi (简单线性插值)
    # l0/b (或d) <= 8 -> phi=1.0
    # GB表: l0/b=10->0.98, 15->0.95, 20->0.92, ... (简化算法)
    # 这里用更保守的 l0/b 公式
    ratio = (H_col * 1000) / size_min
    if ratio <= 8: phi = 1.0
    elif ratio <= 10: phi = 0.98
    elif ratio <= 15: phi = 0.95
    elif ratio <= 20: phi = 0.90
    elif ratio <= 30: phi = 0.81
    else: phi = 0.70 # 太细了
    
    # 承载力 Nu = 0.9 * phi * (fc*A + fy'*As')
    # 0.9 是轴压构件的可靠度调整系数
    Nu = 0.9 * phi * (fc * A_conc + fy * As) / 1000 # N -> kN
    
    # 结果变量打包
    val_demand, val_cap = N_design, Nu
    unit = "kN"
    res_title = "轴心受压承载力"

# ... (上面是你的配筋计算代码) ...
    
    # 结果变量打包
    val_demand, val_cap = N_design, Nu
    unit = "kN"
    res_title = "轴心受压承载力"

    # 👇👇👇 在这里插入向导代码 (只加这一次) 👇👇👇
    st.sidebar.markdown("---")
    with st.sidebar.expander("📌 场景选择向导"):
        st.markdown("""
        **我要算...**
        - 🪑 **混凝土坐凳** → 请选 [梁/板] + [矩形梁]
        - 🌉 **小桥/栈道板** → 请选 [梁/板] + [板]
        - 🌳 **树池/挡墙压顶** → 请选 [梁/板] + [矩形梁]
        """)
    # 👆👆👆 插入结束 👆👆👆

# --- 3. 结果显示 ---
col1, col2 = st.columns([3, 2])
# ...

# --- 3. 结果显示 ---
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader(f"📊 验算: {res_title}")
    
    ratio = val_demand / val_cap if val_cap > 0 else 999
    
    st.metric("需求 (Design)", f"{val_demand:.1f} {unit}")
    st.metric("抗力 (Capacity)", f"{val_cap:.1f} {unit}", delta=f"{val_cap - val_demand:.1f}")
    
    st.progress(min(ratio, 1.0))
    
    if ratio <= 1.0:
        st.success(f"✅ 安全 (利用率 {ratio*100:.1f}%)")
    else:
        st.error(f"❌ 承载力不足！请加大截面或提高标号。")
        
    # 补充检查
    if "梁" in calc_mode:
        if xi > xi_b: st.error("❌ 超筋破坏警报！混凝土会被压碎。必须加大截面。")
        elif rho < rho_min: st.error("❌ 少筋警报！必须增加钢筋。")
    else:
        # 柱的补充检查
        rho_col = As / A_conc
        st.info(f"配筋率: {rho_col:.2%} (规范最小 0.6%)")
        if rho_col < 0.006: st.warning("⚠️ 配筋率小于 0.6%，属于少筋柱。")
        if phi < 0.8: st.warning("⚠️ 柱子比较细长，承载力折减较大。")

with col2:
    st.subheader("📝 计算简报")
    st.write(f"类型: {calc_mode}")
    st.write(f"材质: {conc_grade} + HRB400")
    if "梁" in calc_mode:
        st.write(f"尺寸: {b}x{h} mm")
        st.write(f"配筋: {int(As)} mm²")
    else:
        if "矩形" in col_type: st.write(f"尺寸: {b}x{h} mm")
        else: st.write(f"尺寸: D={D} mm")
        st.write(f"配筋: {int(bar_total_num)}根 Φ{bar_dia}")
        st.write(f"稳定系数 φ: {phi:.3f}")
    
    # 导出 HTML
    report = f"""<h3>混凝土计算书</h3><p>{res_title}: {val_demand} vs {val_cap} ({unit})</p>"""
    b64 = base64.b64encode(report.encode()).decode()
    st.markdown(f'<a href="data:text/html;base64,{b64}" download="混凝土计算书.html">📥 下载报告</a>', unsafe_allow_html=True)
