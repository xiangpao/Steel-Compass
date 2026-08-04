"""Steel-Compass V1 legacy entrypoint.

The V2 product lives in ``frontend`` and ``backend``.  This page intentionally
contains no access credential.  It remains only as a migration notice while
the new application reaches feature parity.
"""

import streamlit as st

st.set_page_config(
    page_title="Steel-Compass V2 迁移提示",
    page_icon="🏗️",
    layout="centered",
)

st.title("Steel-Compass 正在迁移到 V2")
st.info("旧版共享访问口令已作废。请使用 V2 服务端账号登录。")
st.markdown(
    """
    V2 将计算核心、账号权限、项目版本和报告生成从界面中分离，
    并同时提供“方案快算”和“专业计算 Beta”两种模式。

    旧版计算页面仅保留作迁移参考，不再作为受支持入口。
    """
)
