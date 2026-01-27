import streamlit as st
import numpy as np
import base64
from datetime import datetime

# --- 1. 基础配置 ---
st.set_page_config(page_title="结构罗盘 Struct-Compass v0.2", layout="wide")
st.title("🏗️ 结构罗盘 (Struct-Compass) | v0.2")

# --- 2. 侧边栏：核心参数 ---
st.sidebar.header("1. 构件与材质")

# 2.1 材质升级 (Q235B / Q355B)
steel_grade = st.sidebar.radio("钢材牌号", ("Q235B", "Q355B"), horizontal=True)
# 设计强度 (t<16mm)
f_design_map = {"Q235B": 215, "Q355B": 305} 
f_design = f_design_map[steel_grade]
E = 206000 # 弹性模量

# 2.2 结构拓扑 (响应“伞亭”vs“廊架”)
struct_type = st.sidebar.selectbox(
    "结构受力模型 (Topology)",
    ("简支梁 (两端支撑) - 如: 廊架/方亭梁", "悬挑梁 (一端固定) - 如: 单柱伞亭/挑檐")
)

# 2.3 截面选择 (保持不变)
section_type = st.sidebar.selectbox(
    "型材截面",
    ("空心方管 (SHS)", "空心矩形管 (RHS)", "圆管 (CHS)", "焊接H型钢 (H-Beam)")
)

def get_properties(sType):
    props = {}
    st.sidebar.markdown("---")
    st.sidebar.subheader("截面尺寸 (mm)")
    
    # 关键修改：显式指定 min_value=10.0 (最小值), value=200.0 (默认值)
    if sType == "空心方管 (SHS)":
        b = st.sidebar.number_input("边宽 b", min_value=20.0, value=200.0, step=10.0)
        t = st.sidebar.number_input("壁厚 t", min_value=2.0, value=8.0, step=0.5)
        
        # 几何计算
        h = b
        # 防止壁厚大于边宽导致计算报错 (t < b/2)
        if t >= b/2:
            st.error(f"❌ 几何错误: 壁厚 {t} 必须小于边宽的一半 ({b/2})")
            return None
            
        I = (b * h**3 - (b - 2*t) * (h - 2*t)**3) / 12
        W = I / (h / 2)
        A = b*h - (b-2*t)*(h-2*t)
        props = {'I': I, 'W': W, 'A': A, 'desc': f"方管 {int(b)}x{int(b)}x{t}"}

    elif sType == "空心矩形管 (RHS)":
        h = st.sidebar.number_input("高度 h", min_value=20.0, value=250.0, step=10.0)
        b = st.sidebar.number_input("宽度 b", min_value=20.0, value=150.0, step=10.0)
        t = st.sidebar.number_input("壁厚 t", min_value=2.0, value=8.0, step=0.5)
        
        if t >= min(b, h)/2:
            st.error("❌ 几何错误: 壁厚过大")
            return None

        I = (b * h**3 - (b - 2*t) * (h - 2*t)**3) / 12
        W = I / (h / 2)
        A = b*h - (b-2*t)*(h-2*t)
        props = {'I': I, 'W': W, 'A': A, 'desc': f"矩管 {int(h)}x{int(b)}x{t}"}

    elif sType == "圆管 (CHS)":
        D = st.sidebar.number_input("外径 D", min_value=20.0, value=219.0, step=10.0)
        t = st.sidebar.number_input("壁厚 t", min_value=2.0, value=6.0, step=0.5)
        
        if t >= D/2:
            st.error("❌ 几何错误: 实心了？")
            return None

        I = (np.pi * (D**4 - (D - 2*t)**4)) / 64
        W = (2 * I) / D
        A = np.pi * ((D/2)**2 - ((D-2*t)/2)**2)
        props = {'I': I, 'W': W, 'A': A, 'desc': f"圆管 Φ{int(D)}x{t}"}

    elif sType == "焊接H型钢 (H-Beam)":
        h = st.sidebar.number_input("高度 h", min_value=50.0, value=300.0, step=10.0)
        b = st.sidebar.number_input("翼缘宽 b", min_value=50.0, value=150.0, step=10.0)
        tw = st.sidebar.number_input("腹板厚 tw", min_value=3.0, value=6.0, step=0.5)
        tf = st.sidebar.number_input("翼缘厚 tf", min_value=3.0, value=8.0, step=0.5)
        
        I = (b * h**3 - (b - tw) * (h - 2*tf)**3) / 12
        W = I / (h / 2)
        A = 2*b*tf + (h-2*tf)*tw
        props = {'I': I, 'W': W, 'A': A, 'desc': f"H型钢 H{int(h)}x{int(b)}x{tw}x{tf}"}
    
    return props

sect = get_properties(section_type)

st.sidebar.markdown("---")
st.sidebar.header("2. 荷载与环境 (GB 50009)")

# 2.4 城市气象数据 (GB 50009 内置表 - 迷你版)
city_loads = {
    "宁波": {"wind": 0.50, "snow": 0.30},
    "杭州": {"wind": 0.45, "snow": 0.45},
    "上海": {"wind": 0.55, "snow": 0.20},
    "北京": {"wind": 0.45, "snow": 0.40},
    "自定义": {"wind": 0.0, "snow": 0.0}
}
city = st.sidebar.selectbox("所在城市 (用于查风雪荷载)", list(city_loads.keys()))

if city == "自定义":
    w0 = st.sidebar.number_input("基本风压 (kN/m²)", 0.5)
    s0 = st.sidebar.number_input("基本雪压 (kN/m²)", 0.3)
else:
    w0 = city_loads[city]["wind"]
    s0 = city_loads[city]["snow"]
    st.sidebar.caption(f"📍 {city}: 风压 {w0} | 雪压 {s0}")

# 2.5 覆盖层荷载 (增加铝板)
load_map = {
    "轻型玻璃顶 (1.5 kN/m)": 1.5,
    "铝板/金属屋面 (0.8 kN/m)": 0.8, # 新增
    "木格栅顶 (1.0 kN/m)": 1.0,
    "重型/种植顶 (4.0 kN/m)": 4.0,
    "自定义输入": 0.0
}
roof_type = st.sidebar.selectbox("屋面形式", list(load_map.keys()))
span_L = st.sidebar.number_input("梁跨度/悬挑长度 (m)", value=4.0, step=0.5)
width_B = st.sidebar.number_input("受荷宽度 (m) [梁间距]", value=3.0, step=0.5)

# 自动组合荷载 (简化版组合 1.3恒 + 1.5活)
# 这里假设输入的 kN/m 已经是包含了部分恒活的标准值，为了演示规范逻辑，我们做一个简单的换算
if roof_type == "自定义输入":
    q_design = st.sidebar.number_input("设计线荷载 (kN/m)", 2.0)
else:
    # 估算逻辑：线荷载 = (恒载+活载+风雪组合) * 受荷宽度
    # 简化：屋面自重(load_map) + 风雪最大值
    dead_load = load_map[roof_type]
    live_load_env = max(w0, s0) # 取风雪大值
    q_standard_area = dead_load/width_B + live_load_env if width_B >0 else 0 # 反算面荷载
    # 组合值设计值 (Design Value) q = 1.3*恒 + 1.5*活
    q_design = (1.3 * (load_map[roof_type]/width_B if width_B>0 else 1.5) + 1.5 * live_load_env) * width_B
    st.sidebar.info(f"📐 自动计算设计荷载: {q_design:.2f} kN/m")

# --- 3. 计算引擎 ---
L_mm = span_L * 1000
q_N_mm = q_design

# 公式分流：简支 vs 悬挑
if "简支" in struct_type:
    M_max = (1/8) * q_N_mm * (L_mm**2)
    f_max = (5 * q_N_mm * L_mm**4) / (384 * E * sect['I'])
    f_limit = L_mm / 400
    model_name = "简支梁 (Simply Supported)"
else: # 悬挑
    M_max = (1/2) * q_N_mm * (L_mm**2) # 悬挑弯矩大得多
    f_max = (1 * q_N_mm * L_mm**4) / (8 * E * sect['I'])
    f_limit = L_mm / 250 # 悬挑挠度限值通常宽松一点
    model_name = "悬挑梁 (Cantilever)"

sigma = M_max / sect['W']
stress_ratio = sigma / f_design
def_ratio = f_max / f_limit

# --- 4. 结果与导出 ---
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("📊 验算结果")
    
    # 状态指示灯
    status = "✅ 安全" if (stress_ratio < 1.0 and def_ratio < 1.0) else "❌ 危险"
    st.metric("整体状态", status, f"利用率 {max(stress_ratio, def_ratio)*100:.1f}%")

    st.write("---")
    st.write(f"**1. 抗弯强度 (Strength)** [{steel_grade}]")
    st.progress(min(stress_ratio, 1.0))
    st.write(f"σ = {sigma:.1f} MPa / {f_design} MPa")
    
    st.write(f"**2. 变形挠度 (Deflection)**")
    st.progress(min(def_ratio, 1.0))
    st.write(f"f = {f_max:.1f} mm / {f_limit:.1f} mm")

    if stress_ratio > 1.0:
        st.error(f"强度不足！请加大截面或改用 {steel_grade}")
    if def_ratio > 1.0:
        st.warning("刚度不足（太软）！对于悬挑结构，挠度非常敏感，请增加截面高度。")

with col2:
    st.subheader("📑 计算书导出")
    st.write("点击下方按钮生成报告：")
    
    # 生成 HTML 报告
    report_html = f"""
    <div style="font-family:SimHei; padding:20px; border:2px solid #333;">
        <h2 style="text-align:center;">结构计算简报</h2>
        <p><strong>项目时间:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
        <hr>
        <h3>1. 设计参数</h3>
        <ul>
            <li><strong>构件类型:</strong> {model_name}</li>
            <li><strong>型材规格:</strong> {sect['desc']} ({steel_grade})</li>
            <li><strong>跨度/悬挑:</strong> {span_L} m</li>
            <li><strong>荷载工况:</strong> {roof_type} (风压 {w0}/雪压 {s0})</li>
        </ul>
        <h3>2. 验算结论</h3>
        <ul>
            <li><strong>最大应力:</strong> {sigma:.1f} MPa (限值 {f_design}) -> {'<span style="color:green">满足</span>' if stress_ratio<1 else '<span style="color:red">不满足</span>'}</li>
            <li><strong>最大挠度:</strong> {f_max:.1f} mm (限值 {f_limit:.1f}) -> {'<span style="color:green">满足</span>' if def_ratio<1 else '<span style="color:red">不满足</span>'}</li>
        </ul>
        <hr>
        <p style="font-size:0.8em; color:grey;">*本计算书仅供方案参考，施工图请以注册结构师签章为准。</p>
    </div>
    """
    
    # 编码为下载链接
    b64 = base64.b64encode(report_html.encode()).decode()
    href = f'<a href="data:text/html;base64,{b64}" download="结构计算书_{datetime.now().strftime("%Y%m%d")}.html" style="background-color:#4CAF50; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">📥 下载计算书 (HTML)</a>'
    st.markdown(href, unsafe_allow_html=True)

    st.caption("下载后双击打开，按 Ctrl+P 即可打印为 PDF。")
