import streamlit as st

from trial_design_explorer.config import APP_TITLE, ASSETS_DIR
from trial_design_explorer.state import ensure_session_defaults
from trial_design_explorer.ui.pages.protocol_workspace import render_protocol_sidebar, render_protocol_workspace
from trial_design_explorer.ui.pages.registry_explorer import render_registry_sidebar, render_registry_workspace
from trial_design_explorer.ui.styles import apply_app_theme, render_shell_bar


WORKSPACE_DESCRIPTIONS = {
    "Protocol Intelligence": "Protocol-first workspace for extraction, benchmark review, recommendations, and formal reporting.",
    "Registry Explorer": "Secondary workspace for exploring historical registry cohorts and building benchmark context.",
}


def _render_header():
    st.markdown("<div class='app-top-offset'></div>", unsafe_allow_html=True)
    workspace = st.session_state["workspace"]
    logo_col, title_col, control_col = st.columns([0.7, 3.4, 2.2])
    with logo_col:
        logo_path = ASSETS_DIR / "logo.png"
        if logo_path.exists():
            st.markdown("<div class='header-logo-wrap'>", unsafe_allow_html=True)
            st.image(str(logo_path), width=84)
            st.markdown("</div>", unsafe_allow_html=True)
    with title_col:
        render_shell_bar(APP_TITLE, WORKSPACE_DESCRIPTIONS[workspace])
    with control_col:
        st.caption("Workspace")
        selected_workspace = st.segmented_control(
            "Workspace",
            ["Protocol Intelligence", "Registry Explorer"],
            default=workspace,
            selection_mode="single",
            width="stretch",
            label_visibility="collapsed",
        )
        if selected_workspace and selected_workspace != workspace:
            st.session_state["workspace"] = selected_workspace
            st.rerun()
        st.caption("Enterprise review draft")


def render_app():
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")
    ensure_session_defaults(st.session_state)
    apply_app_theme()

    with st.sidebar:
        if st.session_state["workspace"] == "Registry Explorer":
            render_registry_sidebar()
        else:
            render_protocol_sidebar()

    _render_header()

    if st.session_state["workspace"] == "Registry Explorer":
        render_registry_workspace()
    else:
        render_protocol_workspace()
