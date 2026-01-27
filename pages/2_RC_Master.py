import streamlit as st
import numpy as np

# --- 页面配置 ---
st.set_page_config(page_title="混凝土大师 RC-Master", layout="wide")
st.title("🧱 混凝土大师 (RC-Master) | 景观构件")

# --- 0. 登录门卫 (可选，如果需要统一登录，可引用主程序的session) ---
if 'logged_in' in st.session_state and not st.session_state.logged_in:
    st.warning("⚠️ 请先在主页登录")
    st.stop()

# --- 1. 交互侧边栏 ---
st.sidebar.header("1. 构件参数")

# 1.1 构件类型
comp_type = st.sidebar.selectbox("构件类型", ["矩形梁 (Bench/Lintel)", "板 (Slab/Deck)"])

# 1.2 材料强度 (GB 50010)
# C30: fc=14.3, ft=1.43 | C35: fc=16.7, ft=1.57
conc_grade = st.sidebar.selectbox("混凝土等级", ["C25", "C30", "C35", "C40"])
fc_map = {"C25": 11.9, "C30": 14.3, "C35": 16.7, "C40": 19.1} # N/mm2 (Design Value)
ft_map = {"C25": 1.27, "C30": 1.43, "C35": 1.57, "C40": 1.71}
fc = fc_map[conc_grade]
ft = ft_map[conc_grade]

# 钢筋: HRB400 (fy=360) 是景观最常用的
fy = 360 # N/mm2
st.sidebar.caption(f"材料设计值: {conc_grade} (fc={fc}), HRB400 (fy={fy})")

# 1.3 几何尺寸
st.sidebar.markdown("---")
st.sidebar.subheader("截面尺寸 (mm)")
if comp_type == "矩形梁 (Bench/Lintel)":
    b = st.sidebar.number_input("梁宽 b", value=200, step=50)
    h = st.sidebar.number_input("梁高 h", value=400, step=50)
    # 钢筋输入方式：根数 + 直径
    st.sidebar.subheader("配筋 (底筋)")
    bar_num = st.sidebar.number_input("钢筋根数", value=3, step=1)
    bar_dia = st.sidebar.selectbox("钢筋直径", [8, 10, 12, 14, 16, 18, 20, 22, 25], index=4)
    As = bar_num * (np.pi * (bar_dia/2)**2)
    cover = 25 # 保护层
else: # 板
    b = 1000 # 板按1米宽带计算
    h = st.sidebar.number_input("板厚 h", value=120, step=10)
    st.sidebar.caption("计算取 1000mm 宽板带")
    # 钢筋输入方式：间距 + 直径
    st.sidebar.subheader("配筋 (底筋)")
    bar_dia = st.sidebar.selectbox("钢筋直径", [8, 10, 12, 14], index=1)
    spacing = st.sidebar.number_input("钢筋间距 (mm)", value=150, step=10)
    As = (1000 / spacing) * (np.pi * (bar_dia/2)**2)
    cover = 15 # 板保护层较小

# 有效高度 h0
h0 = h - cover - bar_dia/2

# 1.4 荷载
st.sidebar.markdown("---")
st.sidebar.subheader("荷载与跨度")
span_L = st.sidebar.number_input("计算跨度 L (m)", value=3.0, step=0.1)
q_design = st.sidebar.number_input("设计线/面荷载 (kN/m 或 kN/m²)", value=5.0, step=1.0)
st.sidebar.caption("注：输入值应包含 1.3恒+1.5活 的组合系数")

# --- 2. 核心计算 (GB 50010-2010) ---
# 2.1 弯矩计算 M (kN.m)
M_design = 1/8 * q_design * span_L**2 # 简支弯矩

# 2.2 承载力计算 (M_u)
# 平衡方程: alpha1 * fc * b * x = fy * As
# 简化: alpha1 = 1.0 (for <= C50)
x = (fy * As) / (1.0 * fc * b) # 受压区高度 x

# 相对受压区高度 xi
xi = x / h0
xi_b = 0.518 # HRB400 界限值

# 最小配筋率校验
rho = As / (b * h)
rho_min = max(0.2/100, 0.45 * ft / fy) # 0.2% 或公式值

# 弯矩承载力 Mu = fy * As * (h0 - x/2)
Mu = fy * As * (h0 - x/2) / 1e6 # 换算为 kN.m

# --- 3. 结果显示 ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 验算结论")
    
    # 弯矩对比
    st.metric("弯矩需求 (Md)", f"{M_design:.2f} kN.m")
    st.metric("弯矩抗力 (Mu)", f"{Mu:.2f} kN.m", delta=f"{Mu-M_design:.2f}")

    # 安全判断逻辑
    checks = []
    
    # Check 1: 强度
    if Mu >= M_design:
        checks.append(("✅ 强度满足", f"抗力 {Mu:.1f} > 需求 {M_design:.1f}"))
    else:
        checks.append(("❌ 强度不足", "钢筋太少或截面太小，请加筋！"))

    # Check 2: 破坏形态 (最重要!)
    if xi <= xi_b:
        checks.append(("✅ 适筋破坏 (安全)", f"ξ={xi:.3f} < {xi_b} (延性好)"))
    else:
        checks.append(("❌ 超筋破坏 (极度危险)", "钢筋太多了！混凝土会被压碎，请加大截面或减小钢筋。"))

    # Check 3: 最小配筋率
    if rho >= rho_min:
        checks.append(("✅ 配筋率满足", f"ρ={rho:.2%} > {rho_min:.2%}"))
    else:
        checks.append(("❌ 少筋 (脆性危险)", "钢筋少于规范构造要求，一裂就断！"))

    # 输出Check结果
    for title, desc in checks:
        if "❌" in title:
            st.error(f"**{title}**\n\n{desc}")
        else:
            st.success(f"**{title}**\n\n{desc}")

with col2:
    st.subheader("🧱 截面分析")
    st.info(f"当前截面: {int(b)}x{int(h)} mm | {conc_grade}")
    
    # 可视化截面配筋
    st.write(f"**配筋方案**: {int(As)} mm²")
    if comp_type == "矩形梁 (Bench/Lintel)":
        st.write(f"🔹 {int(bar_num)}根 Φ{int(bar_dia)} (底筋)")
    else:
        st.write(f"🔹 Φ{int(bar_dia)} @ {int(spacing)} (板带)")

    st.write("---")
    st.write("**受压区高度 x**:", f"{x:.1f} mm")
    
    # 进度条展示利用率
    util_ratio = M_design / Mu if Mu > 0 else 1.2
    st.write(f"**承载力利用率**: {util_ratio*100:.1f}%")
    st.progress(min(util_ratio, 1.0))

    if util_ratio < 0.5:
        st.warning("💡 设计过于保守，浪费材料。")
    elif util_ratio > 0.95 and util_ratio <= 1.0:
        st.info("👌 极致经济设计。")
