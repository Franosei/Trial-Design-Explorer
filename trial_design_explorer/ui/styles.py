import streamlit as st


def apply_app_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:wght@600;700&display=swap');

        :root {
            --shell-bg: #f4f6f8;
            --panel-bg: rgba(255, 255, 255, 0.94);
            --panel-border: rgba(102, 118, 133, 0.16);
            --ink: #15202b;
            --muted: #5b6978;
            --accent: #244a69;
            --success: #2c6b52;
        }

        html, body, [data-testid="stAppViewContainer"] {
            background: linear-gradient(180deg, #f8fafb 0%, var(--shell-bg) 100%);
            color: var(--ink);
            font-family: "IBM Plex Sans", system-ui, sans-serif;
        }

        [data-testid="stSidebar"] {
            background: #fbfcfd;
            border-right: 1px solid var(--panel-border);
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 2.4rem;
            max-width: 1380px;
        }

        .app-top-offset {
            height: 0.55rem;
        }

        h1, h2, h3, h4 {
            font-family: "Source Serif 4", Georgia, serif;
            letter-spacing: -0.02em;
            color: var(--ink);
        }

        p, li, label, span, div {
            font-family: "IBM Plex Sans", system-ui, sans-serif;
        }

        div.stButton > button,
        div.stDownloadButton > button {
            border-radius: 12px;
            border: 1px solid rgba(30, 86, 125, 0.24);
            background: #ffffff;
            color: var(--ink);
            font-weight: 500;
        }

        div[data-testid="stMetric"] {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 14px;
            padding: 0.85rem 0.95rem;
            box-shadow: none;
        }

        div[data-baseweb="tab-list"] {
            gap: 0.45rem;
        }

        button[kind="segmented_control"] {
            border-radius: 999px;
        }

        .shell-bar {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 16px;
            padding: 0.95rem 1.1rem;
            margin-bottom: 0.8rem;
            margin-top: 0.35rem;
        }

        .shell-kicker {
            font-size: 0.72rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--accent);
            font-weight: 600;
            margin-bottom: 0.15rem;
        }

        .shell-title {
            font-family: "Source Serif 4", Georgia, serif;
            font-size: 1.9rem;
            line-height: 1.08;
            margin: 0 0 0.2rem 0;
            color: var(--ink);
        }

        .shell-subtitle {
            color: var(--muted);
            font-size: 0.97rem;
            margin-bottom: 0;
        }

        .note-card {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 0.85rem 0.95rem;
            box-shadow: none;
        }

        .note-card h4 {
            margin: 0 0 0.35rem 0;
            font-size: 1.05rem;
        }

        .note-card p {
            margin: 0;
            color: var(--muted);
            font-size: 0.94rem;
        }

        .header-logo-wrap {
            display: flex;
            align-items: flex-start;
            justify-content: center;
            padding-top: 0.6rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_shell_bar(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <section class="shell-bar">
            <div class="shell-kicker">Clinical Trial Planning Console</div>
            <div class="shell-title">{title}</div>
            <div class="shell-subtitle">{subtitle}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_note_card(title: str, body: str) -> None:
    st.markdown(
        f"""
        <section class="note-card">
            <h4>{title}</h4>
            <p>{body}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
