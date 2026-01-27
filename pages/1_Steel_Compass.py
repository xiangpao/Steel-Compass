import streamlit as st
import numpy as np
import base64
from datetime import datetime

# --- 1. 基础配置 ---
st.set_page_config(page_title="结构罗盘 Steel-Compass", layout="wide")
# 🔐 安全检查：如果没登录，踢回首页
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ 未授权访问，请先登录！")
    st.stop()
st.title("🔩 结构罗盘 (Steel-Compass) | v1.1")

# --- 2. 侧边栏：核心参数 ---
st.sidebar.header("1. 计算模式 (Mode)")
# ⭐ 新增：模式切换
calc_mode = st.sidebar.radio("选择构件类型", ("梁 (受弯/Beam)", "柱 (受压/Column)"), horizontal=True)

st.sidebar.markdown("---")
st.sidebar.header("2. 构件与材质")

# 2.1 材质
steel_grade = st.sidebar.radio("钢材牌号", ("Q235B", "Q355B"), horizontal=True)
f_y = 235 if steel_grade == "Q235B" else 355
f_design = 215 if steel_grade == "Q235B" else 305 # 抗弯/抗压设计值
E = 206000 # 弹性模量

# 2.2 截面选择 (通用)
section_type = st.sidebar.selectbox(
    "型材截面",
    ("空心方管 (SHS)", "空心矩形管 (RHS)", "圆管 (CHS)", "焊接H型钢 (H-Beam)")
)

def get_properties(sType):
    props = {}
    st.sidebar.markdown("#### 截面尺寸 (mm)")
    
    if sType == "空心方管 (SHS)":
        b = st.sidebar.number_input("边宽 b", min_value=20.0, value=150.0, step=10.0)
        t = st.sidebar.number_input("壁厚 t", min_value=2.0, value=6.0, step=0.5)
        h = b
        if t >= b/2: return None
        I = (b * h**3 - (b - 2*t) * (h - 2*t)**3) / 12
        A = b*h - (b-2*t)*(h-2*t)
        ix = np.sqrt(I/A) # 回转半径
        props = {'I': I, 'W': I/(h/2), 'A': A, 'ix': ix, 'desc': f"方管 {int(b)}x{int(b)}x{t}"}

    elif sType == "空心矩形管 (RHS)":
        h = st.sidebar.number_input("高度 h", min_value=20.0, value=200.0, step=10.0)
        b = st.sidebar.number_input("宽度 b", min_value=20.0, value=100.0, step=10.0)
        t = st.sidebar.number_input("壁厚 t", min_value=2.0, value=6.0, step=0.5)
        if t >= min(b, h)/2: return None
        Iy = (h * b**3 - (h - 2*t) * (b - 2*t)**3) / 12 # 弱轴
        Iz = (b * h**3 - (b - 2*t) * (h - 2*t)**3) / 12 # 强轴
        A = b*h - (b-2*t)*(h-2*t)
        # 柱子失稳通常看弱轴 (最小回转半径)
        ix = np.sqrt(min(Iy, Iz)/A) 
        props = {'I': Iz, 'W': Iz/(h/2), 'A': A, 'ix': ix, 'desc': f"矩管 {int(h)}x{int(b)}x{t}"}

    elif sType == "圆管 (CHS)":
        D = st.sidebar.number_input("外径 D", min_value=20.0, value=140.0, step=10.0)
        t = st.sidebar.number_input("壁厚 t", min_value=2.0, value=5.0, step=0.5)
        if t >= D/2: return None
        I = (np.pi * (D**4 - (D - 2*t)**4)) / 64
        A = np.pi * ((D/2)**2 - ((D-2*t)/2)**2)
        ix = np.sqrt(I/A)
        props = {'I': I, 'W': (2*I)/D, 'A': A, 'ix': ix, 'desc': f"圆管 Φ{int(D)}x{t}"}

    else: # H型钢
        h = st.sidebar.number_input("高度 h", min_value=50.0, value=250.0, step=10.0)
        b = st.sidebar.number_input("翼缘宽 b", min_value=50.0, value=125.0, step=10.0)
        tw = st.sidebar.number_input("腹板厚 tw", min_value=3.0, value=6.0, step=0.5)
        tf = st.sidebar.number_input("翼缘厚 tf", min_value=3.0, value=8.0, step=0.5)
        Iy = (2*tf*b**3 + (h-2*tf)*tw**3)/12 # 弱轴
        Iz = (b*h**3 - (b-tw)*(h-2*tf)**3)/12 # 强轴
        A = 2*b*tf + (h-2*tf)*tw
        ix = np.sqrt(min(Iy, Iz)/A) # 取弱轴回转半径
        props = {'I': Iz, 'W': Iz/(h/2), 'A': A, 'ix': ix, 'desc': f"H型钢 H{int(h)}x{int(b)}"}
    
    return props

sect = get_properties(section_type)
if not sect: st.stop()

st.sidebar.markdown("---")
st.sidebar.header("3. 荷载与几何")

# === 分支逻辑：梁模式 vs 柱模式 ===
if "梁" in calc_mode:
    # --- 梁计算逻辑 (原代码) ---
    struct_type = st.sidebar.selectbox("结构模型", ("简支梁 (两端支撑)", "悬挑梁 (一端固定)"))
    span_L = st.sidebar.number_input("梁跨度/悬挑长 (m)", 4.0, step=0.5)
    q_input = st.sidebar.number_input("设计线荷载 (kN/m)", 2.5, step=0.5, help="1.3恒+1.5活")
    
    L_mm = span_L * 1000
    q_N_mm = q_input
    
    if "简支" in struct_type:
        M_max = (1/8) * q_N_mm * L_mm**2
        f_max = (5 * q_N_mm * L_mm**4) / (384 * E * sect['I'])
        f_limit = L_mm / 400
        limit_txt = "L/400"
    else:
        M_max = (1/2) * q_N_mm * L_mm**2
        f_max = (1 * q_N_mm * L_mm**4) / (8 * E * sect['I'])
        f_limit = L_mm / 250
        limit_txt = "L/250"
        
    sigma = M_max / sect['W']
    ratio_str = sigma / f_design
    ratio_def = f_max / f_limit
    
    res_title = "受弯 (Bending)"
    val1_label, val1 = f"最大应力 (σ)", sigma
    limit1 = f_design
    val2_label, val2 = f"最大挠度 (f)", f_max
    limit2 = f_limit

else:
    # --- 柱计算逻辑 (新代码) ---
    # 输入柱高
    H_col = st.sidebar.number_input("立柱高度 (m)", value=3.0, step=0.1)
    # 输入轴压力
    st.sidebar.caption("👇 荷载输入 (二选一)")
    load_method = st.sidebar.radio("荷载来源", ["直接输入轴力", "按受荷面积估算"])
    
    if load_method == "直接输入轴力":
        N_k = st.sidebar.number_input("柱顶轴压力设计值 (kN)", value=50.0, step=5.0)
    else:
        area = st.sidebar.number_input("受荷面积 (m²)", value=9.0, help="比如3x3的亭子，单柱受荷9/4=2.25平米")
        load_ps = st.sidebar.number_input("综合面荷载 (kN/m²)", value=3.0, help="含自重/雪/风")
        N_k = area * load_ps
        st.sidebar.info(f"👉 估算轴力: {N_k:.1f} kN")
    
    # 柱子计算核心 (GB 50017)
    L0 = H_col * 1000 * 2.0 # ⚠️ 悬臂柱(亭子)计算长度系数取2.0 (最不利)
    if "H型钢" in section_type: 
        pass # H型钢根据弱轴计算
    
    # 1. 长细比 Lambda
    lam = L0 / sect['ix']
    
    # 2. 稳定系数 Phi (简化拟合 GB b类截面)
    # 归一化长细比
    lam_n = (lam / np.pi) * np.sqrt(f_y / E)
    if lam_n <= 0.215:
        phi = 1.0 - 0.65 * lam_n**2
    else:
        a2, a3 = 0.965, 0.300
        phi = (1/(2*lam_n**2)) * ((a2 + a3*lam_n + lam_n**2) - np.sqrt((a2 + a3*lam_n + lam_n**2)**2 - 4*lam_n**2))
    
    # 3. 压应力 Calculation
    # sigma = N / (phi * A)
    N_N = N_k * 1000 # kN -> N
    sigma = N_N / (phi * sect['A'])
    
    ratio_str = sigma / f_design
    ratio_def = lam / 150 # 柱子长细比容许值通常取150
    
    res_title = "轴压稳定性 (Stability)"
    val1_label, val1 = f"稳定应力 (σ = N/φA)", sigma
    limit1 = f_design
    val2_label, val2 = f"长细比 (λ)", lam
    limit2 = 150 # 规范建议上限
    limit_txt = "150 (容许值)"
    
    st.sidebar.warning(f"💡 计算长度系数取 K=2.0 (独立悬臂柱模式)。如果是框架柱，结果会更安全。")

# --- 4. 结果输出 (通用UI) ---
# ... (上面是你的荷载输入代码) ...
    
    st.sidebar.warning(f"💡 计算长度系数取 K=2.0 (独立悬臂柱模式)。...") 
    
    # 👇👇👇 在这里插入向导代码 (只加这一次) 👇👇👇
    st.sidebar.markdown("---")
    with st.sidebar.expander("📌 场景选择向导"):
        st.markdown("""
        **我要算...**
        - 🏯 **精神堡垒/导视牌** → 请选 [柱] 模式
        - 🛖 **单独的雨棚/挑檐** → 请选 [梁] + [悬挑]
        - 🛤️ **廊架檩条/格栅** → 请选 [梁] + [简支]
        """)
    # 👆👆👆 插入结束 👆👆👆

# --- 4. 结果输出 (通用UI) ---
col1, col2 = st.columns([3, 2])
# ...
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader(f"📊 验算结果: {res_title}")
    
    # 状态判定
    status = "✅ 安全" if (ratio_str < 1.0 and ratio_def < 1.0) else "❌ 危险"
    st.metric("整体状态", status, f"利用率 {max(ratio_str, ratio_def)*100:.1f}%")
    
    st.markdown("---")
    
    # 指标 1 (强度/稳定)
    st.write(f"**1. {val1_label}**")
    st.progress(min(ratio_str, 1.0))
    st.write(f"Value: **{val1:.1f}** MPa  /  Limit: {limit1} MPa")
    if "柱" in calc_mode:
        st.caption(f"注：稳定系数 φ = {phi:.3f} (折减了材料强度)")
    
    # 指标 2 (挠度/长细比)
    st.write(f"**2. {val2_label}**")
    st.progress(min(ratio_def, 1.0))
    st.write(f"Value: **{val2:.1f}** {'' if '柱' in calc_mode else 'mm'}  /  Limit: {limit2 if '柱' in calc_mode else f'{limit2:.1f}'} {'' if '柱' in calc_mode else 'mm'}")

    if ratio_str > 1.0:
        st.error("❌ 承载力不足！请加大截面或壁厚。")
    if ratio_def > 1.0:
        if "柱" in calc_mode:
            st.error("❌ 柱子太细长！(长细比超限)。这会导致柱子没被压坏就先弯了。请加大截面宽度。")
        else:
            st.warning("⚠️ 梁太软了。")

with col2:
    st.subheader("📑 构件信息")
    st.info(f"当前模式: {calc_mode}")
    st.write(f"截面: {sect['desc']}")
    st.write(f"材质: {steel_grade}")
    
    if "柱" in calc_mode:
        st.write(f"计算高度: {H_col} m")
        st.write(f"轴压力: {N_k:.1f} kN")
    else:
        st.write(f"跨度: {span_L} m")
        st.write(f"线荷载: {q_input} kN/m")
    
    # 简易导出按钮 (仅HTML)
    report = f"""
    <h3>结构计算简报</h3>
    <p>类型: {calc_mode}</p>
    <p>截面: {sect['desc']}</p>
    <p>结果: {val1:.1f} (限值 {limit1}) | {val2:.1f} (限值 {limit2})</p>
    <p>状态: {status}</p>
    """
    b64 = base64.b64encode(report.encode("utf-8")).decode()
    href = f'<a href="data:text/html;base64,{b64}" download="结构计算书.html">📥 下载简报</a>'
    st.markdown(href, unsafe_allow_html=True)


