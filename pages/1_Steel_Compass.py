import streamlit as st
import numpy as np
import base64

# --- 1. 基础配置 ---
st.set_page_config(page_title="结构罗盘 Steel-Compass", layout="wide")

# 🔐 安全门卫
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ 未授权访问，请先登录！")
    st.stop()

st.title("🔩 结构罗盘 (Steel-Compass) | v1.2")

# --- 2. 侧边栏：核心参数 ---
st.sidebar.header("1. 计算模式 (Mode)")
calc_mode = st.sidebar.radio("选择构件类型", ("梁 (受弯/Beam)", "柱 (受压/Column)"), horizontal=True)

st.sidebar.markdown("---")
st.sidebar.header("2. 构件与材质")

# 2.1 材质
steel_grade = st.sidebar.radio("钢材牌号", ("Q235B", "Q355B"), horizontal=True)
f_design = 215 if steel_grade == "Q235B" else 305
E = 206000 

# 2.2 截面选择
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
        ix = np.sqrt(I/A)
        props = {'I': I, 'W': I/(h/2), 'A': A, 'ix': ix, 'desc': f"方管 {int(b)}x{int(b)}x{t}"}

    elif sType == "空心矩形管 (RHS)":
        h = st.sidebar.number_input("高度 h", min_value=20.0, value=200.0, step=10.0)
        b = st.sidebar.number_input("宽度 b", min_value=20.0, value=100.0, step=10.0)
        t = st.sidebar.number_input("壁厚 t", min_value=2.0, value=6.0, step=0.5)
        if t >= min(b, h)/2: return None
        Iy = (h * b**3 - (h - 2*t) * (b - 2*t)**3) / 12 
        Iz = (b * h**3 - (b - 2*t) * (h - 2*t)**3) / 12 
        A = b*h - (b-2*t)*(h-2*t)
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

    else: 
        h = st.sidebar.number_input("高度 h", min_value=50.0, value=250.0, step=10.0)
        b = st.sidebar.number_input("翼缘宽 b", min_value=50.0, value=125.0, step=10.0)
        tw = st.sidebar.number_input("腹板厚 tw", min_value=3.0, value=6.0, step=0.5)
        tf = st.sidebar.number_input("翼缘厚 tf", min_value=3.0, value=8.0, step=0.5)
        Iy = (2*tf*b**3 + (h-2*tf)*tw**3)/12
        Iz = (b*h**3 - (b-tw)*(h-2*tf)**3)/12
        A = 2*b*tf + (h-2*tf)*tw
        ix = np.sqrt(min(Iy, Iz)/A)
        props = {'I': Iz, 'W': Iz/(h/2), 'A': A, 'ix': ix, 'desc': f"H型钢 H{int(h)}x{int(b)}"}
    
    return props

sect = get_properties(section_type)
if not sect: st.stop()

st.sidebar.markdown("---")
st.sidebar.header("3. 荷载与几何")

# === 分支逻辑 ===
if "梁" in calc_mode:
    struct_type = st.sidebar.selectbox("结构模型", ("简支梁 (两端支撑)", "悬挑梁 (一端固定)"))
    span_L = st.sidebar.number_input("梁跨度/悬挑长 (m)", 4.0, step=0.5)
    q_input = st.sidebar.number_input("设计线荷载 (kN/m)", 2.5, step=0.5)
    
    L_mm = span_L * 1000
    q_N_mm = q_input
    
    if "简支" in struct_type:
        M_max = (1/8) * q_N_mm * L_mm**2
        f_max = (5 * q_N_mm * L_mm**4) / (384 * E * sect['I'])
        f_limit = L_mm / 400
    else:
        M_max = (1/2) * q_N_mm * L_mm**2
        f_max = (1 * q_N_mm * L_mm**4) / (8 * E * sect['I'])
        f_limit = L_mm / 250
        
    sigma = M_max / sect['W']
    ratio_str = sigma / f_design
    ratio_def = f_max / f_limit
    
    res_title = "受弯 (Bending)"
    val1_label, val1, limit1 = f"最大应力 (σ)", sigma, f_design
    val2_label, val2, limit2 = f"最大挠度 (f)", f_max, f_limit

else:
    H_col = st.sidebar.number_input("立柱高度 (m)", value=3.0, step=0.1)
    N_k = st.sidebar.number_input("柱顶轴压力设计值 (kN)", value=50.0, step=5.0)
    
    L0 = H_col * 1000 * 2.0 
    lam = L0 / sect['ix']
    
    lam_n = (lam / np.pi) * np.sqrt(235 / E) # 简化计算，统一按Q235基础曲线
    if lam_n <= 0.215: phi = 1.0 - 0.65 * lam_n**2
    else:
        a2, a3 = 0.965, 0.300
        phi = (1/(2*lam_n**2)) * ((a2 + a3*lam_n + lam_n**2) - np.sqrt((a2 + a3*lam_n + lam_n**2)**2 - 4*lam_n**2))
    
    sigma = (N_k * 1000) / (phi * sect['A'])
    ratio_str = sigma / f_design
    ratio_def = lam / 150
    
    res_title = "轴压稳定性 (Stability)"
    val1_label, val1, limit1 = f"稳定应力 (σ)", sigma, f_design
    val2_label, val2, limit2 = f"长细比 (λ)", lam, 150

# --- 🔥 这里就是向导代码 (已修复缩进) ---
st.sidebar.markdown("---")
with st.sidebar.expander("📌 场景选择向导 (Guide)"):
    st.markdown("""
    **我要算...**
    - 🏯 **精神堡垒/导视牌** → 选 [柱]
    - 🛖 **单独的雨棚/挑檐** → 选 [梁] + [悬挑]
    - 🛤️ **廊架檩条/格栅** → 选 [梁] + [简支]
    """)

# --- 4. 结果输出 ---
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader(f"📊 验算结果: {res_title}")
    status = "✅ 安全" if (ratio_str < 1.0 and ratio_def < 1.0) else "❌ 危险"
    st.metric("整体状态", status, f"利用率 {max(ratio_str, ratio_def)*100:.1f}%")
    st.progress(min(max(ratio_str, ratio_def), 1.0))
    
    st.write(f"**1. {val1_label}**: {val1:.1f} / {limit1:.1f}")
    st.write(f"**2. {val2_label}**: {val2:.1f} / {limit2:.1f}")

with col2:
    st.subheader("📑 构件信息")
    st.info(f"模式: {calc_mode}")
    st.write(f"截面: {sect['desc']}")
    
    report = f"<h3>简报</h3><p>{res_title}: {status}</p>"
    b64 = base64.b64encode(report.encode("utf-8")).decode()
    href = f'<a href="data:text/html;base64,{b64}" download="report.html">📥 下载简报</a>'
    st.markdown(href, unsafe_allow_html=True)
