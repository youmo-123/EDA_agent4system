from __future__ import annotations
from dooragent.agents.base import BaseAgent


class A3Agent(BaseAgent):
    role = "A3"
    operations = {
        "synthesize": ["a3_synth_tool", "a3_netlist_validator"],
        "evaluate_strategy": ["a3_synth_tool", "a3_timing_estimator", "a3_cost_model"],
        "estimate_timing": ["a3_timing_estimator"],
        "validate_netlist": ["a3_netlist_validator"],
        "search_ppa": ["a3_search_engine"],
        "locate_hotspots": ["a3_hotspot_localizer"],
        "recommend_rtl": ["a3_rtl_recommender"],
        "reevaluate_candidate": ["a3_synth_tool", "a3_timing_estimator",
                                  "a3_netlist_validator", "a3_cost_model"],
    }
