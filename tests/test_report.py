from langgraph_agent_lab.metrics import MetricsReport, ScenarioMetric
from langgraph_agent_lab.report import render_report


def test_render_report_includes_metrics_architecture_and_failures() -> None:
    # Given: a report with both successful and exhausted retry scenarios
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
                nodes_visited=3,
            ),
            ScenarioMetric(
                scenario_id="S07",
                success=False,
                expected_route="error",
                actual_route="error",
                nodes_visited=6,
                retry_count=1,
                errors=["retry attempt 1"],
            ),
        ],
    )

    # When: report is rendered
    report = render_report(metrics)

    # Then: markdown exposes required evidence rather than placeholder text
    assert "| Total scenarios | 2 |" in report
    assert "| S07 | error | error | no | 1 | 0 |" in report
    assert "## 2. Architecture" in report
    assert "## 5. Failure analysis" in report
    assert "LLM key-gated" in report
