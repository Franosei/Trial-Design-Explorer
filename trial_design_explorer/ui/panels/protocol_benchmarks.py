import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from trial_design_explorer.services.comparison_service import (
    build_action_register,
    build_cohort_definition_table,
    build_design_differential_table,
    build_endpoint_precedent_table,
)


def render_protocol_benchmark_panel(trials_df: pd.DataFrame, metrics: dict, recommendations: list[dict]) -> None:
    if trials_df is None or trials_df.empty:
        st.info("Build a comparable cohort to unlock benchmark visuals.")
        return

    st.markdown("### Decision Posture")
    posture_col1, posture_col2, posture_col3, posture_col4 = st.columns(4)
    posture_col1.metric("Completed Fit", _fmt_pct(metrics.get("completed_design_fit_pct")))
    posture_col2.metric("Disrupted Fit", _fmt_pct(metrics.get("disrupted_design_fit_pct")))
    posture_col3.metric("Posture", _short_posture(metrics.get("precedent_posture", "N/A")))
    posture_col4.metric("Evidence Strength", metrics.get("evidence_strength", "Limited"))

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(_precedent_differential_chart(metrics), width="stretch")
    with chart_right:
        st.plotly_chart(_endpoint_precedent_chart(metrics), width="stretch")

    table_left, table_right = st.columns([1.25, 1])
    with table_left:
        st.markdown("#### Design Differential Matrix")
        differential_df = build_design_differential_table(metrics)
        st.dataframe(differential_df, width="stretch", hide_index=True, height=360)
    with table_right:
        st.markdown("#### Executive Action Register")
        action_df = build_action_register(recommendations)
        st.dataframe(action_df, width="stretch", hide_index=True, height=360)

    lower_left, lower_right = st.columns([1, 1.2])
    with lower_left:
        st.markdown("#### Cohort Definition")
        cohort_df = build_cohort_definition_table(metrics)
        st.dataframe(cohort_df, width="stretch", hide_index=True)
    with lower_right:
        st.markdown("#### Matched Cohort Status Mix")
        st.plotly_chart(_status_mix_chart(metrics), width="stretch")


def _precedent_differential_chart(metrics: dict) -> go.Figure:
    plot_df = pd.DataFrame(metrics.get("alignment_by_domain", [])).dropna(subset=["Completed Match (%)", "Disrupted Match (%)"], how="all")

    if plot_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No precedent differential data available.", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        fig.update_layout(title="Completed vs Disrupted Precedent", template="plotly_white", height=460)
        return fig

    plot_df = plot_df.fillna(0)
    plot_df = plot_df.sort_values("Net Gap (%)", ascending=True)

    fig = go.Figure()
    for _, row in plot_df.iterrows():
        fig.add_trace(
            go.Scatter(
                x=[row["Disrupted Match (%)"], row["Completed Match (%)"]],
                y=[row["Domain"], row["Domain"]],
                mode="lines",
                line=dict(color="#CBD5E1", width=3),
                showlegend=False,
                hoverinfo="skip",
            )
        )

    fig.add_trace(
        go.Scatter(
            x=plot_df["Completed Match (%)"],
            y=plot_df["Domain"],
            mode="markers",
            name="Completed precedent",
            marker=dict(color="#1F5B7A", size=11),
            hovertemplate="%{y}<br>Completed match %{x:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df["Disrupted Match (%)"],
            y=plot_df["Domain"],
            mode="markers",
            name="Disrupted precedent",
            marker=dict(color="#C0563D", size=11),
            hovertemplate="%{y}<br>Disrupted match %{x:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title="Completed vs Disrupted Precedent by Design Domain",
        template="plotly_white",
        height=460,
        margin=dict(t=70, b=40, l=20, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(title="Match Share (%)", range=[0, 100])
    fig.update_yaxes(title="")
    return fig


def _endpoint_precedent_chart(metrics: dict) -> go.Figure:
    endpoint_df = build_endpoint_precedent_table(metrics)
    if endpoint_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No endpoint precedent data available.", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        fig.update_layout(title="Endpoint Precedent Split", template="plotly_white", height=460)
        return fig

    plot_df = endpoint_df.copy()
    for column in ["Completed Share (%)", "Disrupted Share (%)", "Net Gap (%)"]:
        plot_df[column] = pd.to_numeric(plot_df[column], errors="coerce").fillna(0)

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=plot_df["Endpoint Category"],
            y=plot_df["Completed Share (%)"],
            name="Completed precedent",
            marker_color="#1F5B7A",
            hovertemplate="%{x}<br>Completed %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=plot_df["Endpoint Category"],
            y=plot_df["Disrupted Share (%)"],
            name="Disrupted precedent",
            marker_color="#C0563D",
            hovertemplate="%{x}<br>Disrupted %{y:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title="Endpoint Focus in Completed vs Disrupted Comparators",
        template="plotly_white",
        barmode="group",
        height=460,
        margin=dict(t=70, b=60, l=20, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_yaxes(title="Share (%)")
    fig.update_xaxes(title="")
    return fig


def _status_mix_chart(metrics: dict) -> go.Figure:
    status_distribution = metrics.get("status_distribution", {})
    plot_df = pd.DataFrame([{"Status": status, "Share": share} for status, share in status_distribution.items()]).sort_values(
        "Share",
        ascending=False,
    )

    if plot_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No status distribution is available.", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        fig.update_layout(title="Matched Cohort Status Mix", template="plotly_white", height=380)
        return fig

    fig = px.bar(
        plot_df,
        x="Status",
        y="Share",
        color="Status",
        title="Matched Cohort Status Mix",
        color_discrete_sequence=px.colors.qualitative.Safe,
    )
    fig.update_layout(template="plotly_white", height=380, margin=dict(t=60, b=20, l=20, r=20), showlegend=False)
    fig.update_yaxes(title="Share (%)")
    return fig


def _fmt_pct(value) -> str:
    if value is None:
        return "N/A"
    return f"{value}%"


def _short_posture(value: str) -> str:
    replacements = {
        "Closer to completed precedent": "Completed-led",
        "Closer to disrupted precedent": "Disrupted-led",
        "Mixed precedent posture": "Mixed",
        "Incomplete precedent signal": "Incomplete",
    }
    return replacements.get(value, value)
