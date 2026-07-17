from __future__ import annotations
from dooragent.agents.base import BaseAgent


class A1Agent(BaseAgent):
    role = "A1"
    operations = {
        "compile": ["a1_compile"],
        "simulate": ["a1_simulate"],
        "measure_diagnostic_coverage": ["a1_diagnostic_coverage"],
        "analyze_bottleneck": ["a1_profile_metrics", "a1_bottleneck_analyzer"],
        "analyze_coverage_hotspot": ["a1_diagnostic_coverage", "a1_source_map",
                                     "a1_coverage_hotspot_analyzer"],
        "full_simulation_analysis": [
            "a1_compile", "a1_simulate", "a1_diagnostic_coverage",
            "a1_profile_metrics", "a1_bottleneck_analyzer",
        ],
    }
