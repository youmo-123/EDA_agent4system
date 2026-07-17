from __future__ import annotations
from dooragent.agents.base import BaseAgent


class A2Agent(BaseAgent):
    role = "A2"
    operations = {
        "analyze_rtl": ["a2_rtl_interface_analyzer"],
        "generate_verification": ["a2_verification_skeleton_generator"],
        "generate_coverage_model": ["a2_coverage_model_generator"],
        "generate_tests": ["a2_constraint_model_builder", "a2_test_generator"],
        "analyze_coverage_gap": ["a2_coverage_gap_analyzer"],
        "refine_tests": ["a2_strategy_selector", "a2_test_generator"],
        "minimize_failure": ["a2_failure_minimizer"],
        "infer_assertions": ["a2_assertion_inferencer"],
    }
