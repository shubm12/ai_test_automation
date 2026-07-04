"""Emergency fallback presets, used only if the LLM flow-extraction call fails.

A FlowStep is a generic, site-agnostic instruction that dom_scanner replays
with Playwright:
    {"action": "navigate", "target": "<free-text page description>"}
    {"action": "fill", "field_hint": "<free-text field description>", "value": "<value to type>"}
    {"action": "click", "target_hint": "<free-text element description>"}

The story is always the primary source of the journey (via flow_resolver.py's
LLM-based extraction) so the pipeline supports arbitrary URLs and arbitrary
journeys, not just the ones listed here. FLOWS exists purely so a demo doesn't
go dark if the LLM call errors out - it is NOT meant to be extended per-journey
(that would defeat "any URL, any elements"). Keep entries minimal (e.g. just
enough to get logged in).
"""

FlowStep = dict[str, str]

FLOWS: dict[str, list[FlowStep]] = {
    "saucedemo.com": [
        {"action": "navigate", "target": "login page"},
        {"action": "fill", "field_hint": "username", "value": "standard_user"},
        {"action": "fill", "field_hint": "password", "value": "secret_sauce"},
        {"action": "click", "target_hint": "login button"},
        {"action": "navigate", "target": "dashboard / inventory page"},
    ],
}


def find_preset(url: str) -> list[FlowStep] | None:
    for domain_key, steps in FLOWS.items():
        if domain_key in url:
            return steps
    return None
