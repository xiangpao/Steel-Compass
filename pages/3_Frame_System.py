import streamlit as st
import numpy as np
import base64

# --- 页面配置 ---
st.set_page_config(page_title="整体刚架 Frame-System", layout="wide")

# 🔐 安全门卫
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ 未授权访问，请先登录！")
    st.stop()

st.title("⛩️ 整体刚架系统 (Portal Frame) | v1.2")

st.markdown("""
> **System Insight**: 采用 **位移法 (Displacement Method)** 计算单跨刚架。
> 适用于：梁柱刚接（焊接）的廊架、景亭。已解锁小截面输入限制。
""")

# --- 1. 参数输入 ---
col_input1, col_input2 = st.columns(2)

with col_input1:
    st.header("1. 几何与荷载")
    # 同样解锁跨度和高度的限制
    span_L = st.number_input("跨度 L (m)", min_value=1.0, value=5.0, step=0.5)
    height_H = st.number_input("柱高 H (m)", min_value=1.0, value=3.5, step=0.1)
    q_load = st.number_input("梁上线荷载 q (kN/m)", min_value=0.0, value=3.0, step=0.5, help="设计值：1.3恒+1.5活")
    
    st.subheader("柱脚形式")
    support_type = st.radio("选择柱脚", ["刚接 (Fixed)", "铰接 (Pinned)"], index=1)
    st.caption("注：景观独立柱通常按刚接，廊架柱建议按铰接（安全储备在柱顶）。")

with col_input2:
    st.header("2. 截面选择")
    
    # --- 梁截面 (Bug修复处) ---
    st.subheader("🟦 梁 (Beam)")
    # 使用关键字参数 value=..., min_value=...
    b_beam = st.number_input("梁宽 (mm)", min_value=20.0, value=150.0, step=10.0, key="bb")
    h_beam = st.number_input("梁高 (mm)", min_value=20.0, value=300.0, step=10.0, key="hb")
    t_beam = st.number_input("梁壁厚 (mm)", min_value=2.0, value=6.0, step=0.5, key="tb")
    
    # --- 柱截面 (Bug修复处) ---
    st.subheader("🟧 柱 (Column)")
    b_col = st.number_input("柱宽 (mm)", min_value=20.0, value=150.0, step=10.0, key="bc")
    h_col = st.number_input("柱高/深 (mm)", min_value=20.0, value=150.0, step=10.0, key="hc")
    t_col = st.number_input("柱壁厚 (mm)", min_value=2.0, value=6.0, step=0.5, key="tc")

    # 材质
    grade = st.selectbox("钢材牌号", ["Q235B", "Q355B"])
    fy = 235 if grade == "Q235B" else 355
    E = 206000

# --- 2. 核心求解器 (Solver) ---
def calc_I(b, h, t):
    # 几何检查
    if t >= min(b,h)/2: return 0 
    return (b*h**3 - (b-2*t)*(h-2*t)**3)/12

Ib = calc_I(b_beam, h_beam, t_beam)
Ic = calc_I(b_col, h_col, t_col)

if Ib == 0 or Ic == 0:
    st.error("❌ 截面错误：壁厚过大（变成了实心）或尺寸不合理。")
    st.stop()

# --- 位移法求解逻辑 ---
# 固端弯矩 (Fixed End Moment)
M_fem = (q_load * span_L**2) / 12 * 1e6 # N.mm

# 线刚度 (i = EI/L)
i_b = E * Ib / (span_L * 1000)
i_c = E * Ic / (height_H * 1000)

# 求解节点转角 theta
if "铰接" in support_type:
    # 3*i_c*theta + 2*i_b*theta = M_fem
    theta = M_fem / (3*i_c + 2*i_b)
    M_node = 3 * i_c * theta 
    M_bottom = 0
else: # 刚接
    # 4*i_c*theta + 2*i_b*theta = M_fem
    theta = M_fem / (4*i_c + 2*i_b)
    M_node = 4 * i_c * theta
    M_bottom = 2 * i_c * theta

# 跨中弯矩
M_beam_mid = (q_load * span_L**2)/8 * 1e6 - M_node

# 换算回 kN.m
M_node_k = M_node / 1e6
M_bottom_k = M_bottom / 1e6
M_mid_k = M_beam_mid / 1e6
N_col = (q_load * span_L) / 2 # 柱轴力

# --- 3. 验算与可视化 ---
st.markdown("---")
st.subheader("3. 分析结果")

col_res1, col_res2 = st.columns([1, 1])

with col_res1:
    st.info(f"📍 **内力分布**")
    st.write(f"🔹 梁柱节点弯矩: **{M_node_k:.2f}** kN.m")
    st.write(f"🔹 梁跨中弯矩: **{M_mid_k:.2f}** kN.m")
    st.write(f"🔹 柱底弯矩: **{M_bottom_k:.2f}** kN.m")
    st.write(f"🔹 柱轴压力: **{N_col:.2f}** kN")
    
    # 弯矩图 ASCII 示意
    st.code(f"""
      {M_node_k:.1f}         {M_node_k:.1f}
      ┌──────────────┐
      │  ↓ ↓ ↓ ↓ ↓   │ {M_mid_k:.1f}
      │              │
    {M_bottom_k:.1f}              {M_bottom_k:.1f}
    """, language="text")

with col_res2:
    st.warning("📊 **应力验算**")
    
    # 1. 梁验算
    M_beam_design = max(abs(M_node_k), abs(M_mid_k))
    W_beam = Ib / (h_beam/2)
    sigma_beam = M_beam_design * 1e6 / W_beam
    
    res_beam = "✅ 安全" if sigma_beam < fy else "❌ 危险"
    st.write(f"**梁应力**: {sigma_beam:.1f} / {fy} MPa")
    st.progress(min(sigma_beam/fy, 1.0))
    if sigma_beam >= fy: st.error("梁强度不足！")
    
    # 2. 柱验算 (压弯)
    A_col = b_col*h_col - (b_col-2*t_col)*(h_col-2*t_col)
    W_col = Ic / (h_col/2)
    
    sigma_col_axial = (N_col * 1000) / A_col
    sigma_col_bend = (max(M_node_k, M_bottom_k) * 1e6) / W_col
    sigma_col_total = sigma_col_axial + sigma_col_bend
    
    res_col = "✅ 安全" if sigma_col_total < fy else "❌ 危险"
    st.write(f"**柱应力**: {sigma_col_total:.1f} / {fy} MPa")
    st.progress(min(sigma_col_total/fy, 1.0))
    st.caption(f"构成: 轴压 {sigma_col_axial:.1f} + 弯曲 {sigma_col_bend:.1f}")
    
    if sigma_col_total >= fy: 
        st.error("柱强度不足！")
        if sigma_col_bend > sigma_col_axial * 3:
            st.warning("💡 提示：柱子主要是被梁掰弯的，请加大柱截面或增加壁厚。")

# --- 4. 导出 ---
report = f"""<h3>刚架计算报告</h3><p>尺寸: {span_L}x{height_H}m</p><p>结果: 梁{sigma_beam:.1f}MPa | 柱{sigma_col_total:.1f}MPa</p>"""
b64 = base64.b64encode(report.encode()).decode()
st.markdown(f'<a href="data:text/html;base64,{b64}" download="刚架计算书.html">📥 下载简报</a>', unsafe_allow_html=True)
