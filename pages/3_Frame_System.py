import streamlit as st
import numpy as np
import base64

# --- 页面配置 ---
st.set_page_config(page_title="整体刚架 Frame-System", layout="wide")
st.title("⛩️ 整体刚架系统 (Portal Frame)")

st.markdown("""
> **System Insight**: 此模块采用 **“位移法 (Displacement Method)”** 计算单跨门式刚架。
> 适用于：梁柱刚性连接（焊接）的廊架、景亭。考虑了梁柱刚度分配对内力的影响。
""")

# --- 1. 参数输入 ---
col_input1, col_input2 = st.columns(2)

with col_input1:
    st.header("1. 几何与荷载")
    span_L = st.number_input("跨度 L (m)", value=5.0, step=0.5)
    height_H = st.number_input("柱高 H (m)", value=3.5, step=0.1)
    q_load = st.number_input("梁上线荷载 q (kN/m)", value=3.0, step=0.5, help="设计值：1.3恒+1.5活")
    
    st.subheader("柱脚形式 (Base Support)")
    support_type = st.radio("选择柱脚", ["刚接 (Fixed) - 埋深混凝土", "铰接 (Pinned) - 螺栓连接"], index=1)
    st.caption("景观小品基础较小，通常按 **铰接** 考虑更安全（柱底弯矩为0，但梁柱节点弯矩大）。")

with col_input2:
    st.header("2. 截面选择")
    
    # --- 梁截面 ---
    st.subheader("🟦 梁 (Beam)")
    b_beam = st.number_input("梁宽 (mm)", 150, key="bb")
    h_beam = st.number_input("梁高 (mm)", 300, key="hb")
    t_beam = st.number_input("梁壁厚 (mm)", 6.0, key="tb")
    
    # --- 柱截面 ---
    st.subheader("🟧 柱 (Column)")
    b_col = st.number_input("柱宽 (mm)", 150, key="bc")
    h_col = st.number_input("柱高/深 (mm)", 150, key="hc") # 方管通常相等
    t_col = st.number_input("柱壁厚 (mm)", 6.0, key="tc")

    # 材质
    grade = st.selectbox("钢材牌号", ["Q235B", "Q355B"])
    fy = 235 if grade == "Q235B" else 355
    E = 206000

# --- 2. 核心求解器 (Solver) ---
# 计算截面属性 (I: 惯性矩)
def calc_I(b, h, t):
    if t >= min(b,h)/2: return 0 # 几何错误
    return (b*h**3 - (b-2*t)*(h-2*t)**3)/12

Ib = calc_I(b_beam, h_beam, t_beam)
Ic = calc_I(b_col, h_col, t_col)

# 校验输入
if Ib == 0 or Ic == 0:
    st.error("截面壁厚设置错误！")
    st.stop()

# --- 位移法求解逻辑 ---
# 假设结构对称，荷载对称，无侧移。未知数：节点转角 theta
# 固端弯矩 (Fixed End Moment)
M_fem = (q_load * span_L**2) / 12 * 1000 * 1000 # kN.m -> N.mm

# 线刚度 (i = EI/L)
i_b = E * Ib / (span_L * 1000)
i_c = E * Ic / (height_H * 1000)

# 刚度系数 k
k = i_b / i_c 

# 求解节点转角 theta (根据柱脚不同)
# M_joint_beam + M_joint_col = 0
if "铰接" in support_type:
    # 柱顶力矩 M_c = 3 * i_c * theta
    # 梁端力矩 M_b = 2 * i_b * theta - M_fem
    # 平衡: 3*i_c*theta + 2*i_b*theta = M_fem
    theta = M_fem / (3*i_c + 2*i_b)
    
    M_node = 3 * i_c * theta # 节点弯矩 (柱顶=梁端)
    M_bottom = 0 # 柱底弯矩
    M_beam_mid = (q_load * span_L**2)/8 * 1e6 - M_node # 跨中弯矩 = 简支弯矩 - 节点负弯矩

else: # 刚接柱脚
    # 柱顶力矩 M_c = 4 * i_c * theta
    # 梁端力矩 M_b = 2 * i_b * theta - M_fem
    theta = M_fem / (4*i_c + 2*i_b)
    
    M_node = 4 * i_c * theta
    M_bottom = 2 * i_c * theta # 柱底弯矩 = 0.5 * 柱顶
    M_beam_mid = (q_load * span_L**2)/8 * 1e6 - M_node

# 换算回 kN.m
M_node_k = M_node / 1e6
M_bottom_k = M_bottom / 1e6
M_mid_k = M_beam_mid / 1e6

# 柱子轴力 (等于梁的剪力)
N_col = (q_load * span_L) / 2 # kN

# --- 3. 验算与可视化 ---
st.markdown("---")
st.subheader("3. 分析结果 (Analysis Result)")

# 3.1 弯矩图示意
col_res1, col_res2 = st.columns([1, 1])

with col_res1:
    st.info(f"📍 **关键内力 (Internal Forces)**")
    st.write(f"🔹 **梁柱节点弯矩 (负弯矩)**: {M_node_k:.2f} kN.m")
    st.write(f"🔹 **梁跨中弯矩 (正弯矩)**: {M_mid_k:.2f} kN.m")
    st.write(f"🔹 **柱底弯矩**: {M_bottom_k:.2f} kN.m")
    st.write(f"🔹 **柱轴压力**: {N_col:.2f} kN")
    
    # 简单的 ASCII 弯矩图
    st.code(f"""
      {M_node_k:.1f}         {M_node_k:.1f}
      ┌──────────────┐
      │  ↓ ↓ ↓ ↓ ↓   │
      │    {M_mid_k:.1f}      │
      │              │
    {M_bottom_k:.1f}              {M_bottom_k:.1f}
    """, language="text")

with col_res2:
    st.warning("📊 **强度/稳定性验算**")
    
    # 1. 梁验算 (最大弯矩可能在端部，也可能在跨中)
    M_beam_design = max(abs(M_node_k), abs(M_mid_k))
    W_beam = Ib / (h_beam/2)
    sigma_beam = M_beam_design * 1e6 / W_beam
    
    res_beam = "✅" if sigma_beam < fy else "❌"
    st.write(f"**梁应力 (Bending)**: {sigma_beam:.1f} / {fy} MPa {res_beam}")
    
    # 2. 柱验算 (压弯构件 - 简化公式)
    # sigma = N/A + M/W
    A_col = b_col*h_col - (b_col-2*t_col)*(h_col-2*t_col)
    W_col = Ic / (h_col/2)
    
    sigma_col_axial = (N_col * 1000) / A_col
    sigma_col_bend = (max(M_node_k, M_bottom_k) * 1e6) / W_col
    sigma_col_total = sigma_col_axial + sigma_col_bend
    
    res_col = "✅" if sigma_col_total < fy else "❌"
    st.write(f"**柱应力 (压+弯)**: {sigma_col_total:.1f} / {fy} MPa {res_col}")
    st.caption(f"(含: 轴压 {sigma_col_axial:.1f} + 弯曲 {sigma_col_bend:.1f})")
    
    if sigma_col_bend > sigma_col_axial * 5:
        st.error("⚠️ 注意：柱子主要受弯！这是一个受力很大的刚架。")

# --- 4. 导出 ---
report = f"""
<h3>刚架计算报告 Portal Frame Report</h3>
<p>尺寸: L={span_L}m, H={height_H}m</p>
<p>梁截面: {int(b_beam)}x{int(h_beam)}x{t_beam}</p>
<p>柱截面: {int(b_col)}x{int(h_col)}x{t_col}</p>
<p>节点弯矩: {M_node_k:.2f} kN.m</p>
<p>柱最大应力: {sigma_col_total:.1f} MPa ({res_col})</p>
"""
b64 = base64.b64encode(report.encode()).decode()
st.markdown(f'<a href="data:text/html;base64,{b64}" download="刚架计算书.html">📥 下载计算书</a>', unsafe_allow_html=True)
