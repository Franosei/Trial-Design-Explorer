from dotenv import load_dotenv

load_dotenv()  # Must be top-level — Streamlit imports this module, never runs it as __main__

from trial_design_explorer.ui.app_shell import render_app


if __name__ == "__main__":
    render_app()
