from __future__ import annotations

from langgraph_agent_lab.metrics import MetricsReport, ScenarioMetric
from langgraph_agent_lab.report import render_report


def test_render_report_includes_metrics_and_scenarios() -> None:
    metrics = MetricsReport(
        total_scenarios=2,
        success_rate=0.5,
        avg_nodes_visited=4.5,
        total_retries=1,
        total_interrupts=1,
        scenario_metrics=[
            ScenarioMetric(
                scenario_id="S01",
                success=True,
                expected_route="simple",
                actual_route="simple",
                retry_count=0,
                interrupt_count=0,
                latency_ms=12,
            ),
            ScenarioMetric(
                scenario_id="S02",
                success=False,
                expected_route="tool",
                actual_route="error",
                retry_count=1,
                interrupt_count=1,
                latency_ms=34,
                errors=["ERROR: service unavailable"],
            ),
        ],
    )

    report = render_report(metrics)

    assert "# Day 08 Lab Report" in report
    assert "| Success rate | 50.00% |" in report
    assert "| S01 | simple | simple | Yes | 0 | 0 | 12 |" in report
    assert "| S02 | tool | error | No | 1 | 1 | 34 |" in report
    assert "ERROR: service unavailable" in report
