"""
Rules module for EventWatcher.

This module provides functions for evaluating rule conditions against a given context.
Each rule may define a condition (a Python expression) that uses helper functions and
variables from the context (such as `data`, `now`, and `aggregate`).

Rules may also define optional fields:
  - event_type: the type of event (e.g., "modified", "created", etc.)
  - severity: the severity level (e.g., "WARNING", "CRITICAL", etc.)
  - affected_files_expr (optional): a Python expression to determine which files are affected.
"""


def evaluate_rule(rule, context):
    """
    Evaluate a single rule against the given context.

    The context should include:
      - data: the current sample data (a dict mapping file paths to their metrics)
      - now: current epoch time
      - aggregate: a helper function for aggregating metrics, e.g., aggregate(data, '*.test', 'last_modified', min)

    Optionally, the rule can define 'affected_files_expr', which when evaluated returns a list of affected files.

    Returns:
      (triggered: bool, affected_files: list)
    """
    condition = rule.get("condition")
    if not condition:
        return False, []

    # Build a local context from the provided context.
    # This context is available to the eval() call.
    local_context = context.copy()
    # Pre-populate an empty list for affected_files in case the condition uses it.
    local_context["affected_files"] = []

    # Define a set of safe built-in functions for use in rule expressions.
    safe_builtins = {
        "min": min,
        "max": max,
        "any": any,
        "all": all,
        "sum": sum,
        "len": len,
    }

    try:
        # Evaluate the condition with our safe builtins.
        triggered = eval(condition, {"__builtins__": safe_builtins}, local_context)
    except Exception as e:
        raise ValueError(f"Error evaluating rule '{rule.get('name', 'Unnamed')}': {e}")

    # Determine which files are affected.
    affected_files = []
    if "affected_files_expr" in rule:
        try:
            affected_files = eval(
                rule["affected_files_expr"],
                {"__builtins__": safe_builtins},
                local_context,
            )
        except Exception as e:
            raise ValueError(
                f"Error evaluating affected_files_expr for rule '{rule.get('name', 'Unnamed')}': {e}"
            )
    else:
        # If no affected_files_expr is provided and the rule is triggered,
        # assume all files in the sample are affected.
        if triggered:
            affected_files = list(local_context.get("data", {}).keys())

    return triggered, affected_files


def evaluate_rules(rules, context):
    """
    Evaluate a list of rules against the given context.

    Returns a list of dicts for triggered events. Each dict contains:
      - name: the rule's name
      - event_type: the rule-defined event type (if any)
      - severity: the rule-defined severity (if any)
      - affected_files: list of file paths that triggered the event
    """
    triggered_events = []
    for rule in rules:
        triggered, affected_files = evaluate_rule(rule, context)
        if triggered and affected_files:
            event_record = {
                "name": rule.get("name", "Unnamed Event"),
                "event_type": rule.get("event_type"),
                "severity": rule.get("severity"),
                "affected_files": affected_files,
            }
            triggered_events.append(event_record)
    return triggered_events
