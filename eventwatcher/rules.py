def evaluate_rule(rule, sample):
    """
    Evaluate a single rule against the sample.

    Args:
        rule (dict): Rule with 'name' and 'condition'.
        sample (dict): Collected sample data.

    Returns:
        bool: True if the rule condition is met.

    Raises:
        ValueError: If there is an error evaluating the rule.
    """
    condition = rule.get('condition')
    if not condition:
        return False
    try:
        return eval(condition, {"__builtins__": {}}, {"data": sample})
    except Exception as e:
        raise ValueError(f"Error evaluating rule '{rule.get('name', 'Unnamed')}': {e}")

def evaluate_rules(rules, sample):
    """
    Evaluate a list of rules against the sample.

    Args:
        rules (list): List of rule dictionaries.
        sample (dict): Collected sample data.

    Returns:
        list: Names of triggered events.
    """
    triggered = []
    for rule in rules:
        if evaluate_rule(rule, sample):
            triggered.append(rule.get('name', 'Unnamed Event'))
    return triggered
