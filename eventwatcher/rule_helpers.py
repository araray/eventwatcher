"""
Rule helper functions for EventWatcher.

This module provides helper functions for evaluating rules and a set of safe
built-in functions that can be used in rule conditions.
"""

import fnmatch

# Define safe built-in functions that can be used in rule expressions
SAFE_BUILTINS = {
    'min': min,
    'max': max,
    'any': any,
    'all': all,
    'sum': sum,
    'len': len,
    'abs': abs,
    'bool': bool,
    'int': int,
    'float': float,
    'str': str,
    'list': list,
    'dict': dict,
    'set': set,
    'round': round
}


def aggregate_metric(data, pattern, metric, func=min):
    """
    Aggregates a given metric from the sample data for files matching a glob pattern.

    Args:
        data (dict): Collected sample data mapping file paths to their metrics.
        pattern (str): Glob pattern to match file paths.
        metric (str): The metric to aggregate (e.g., 'last_modified', 'size').
        func (callable): Aggregation function (e.g., min, max, sum, or a custom function).

    Returns:
        The aggregated value, or 0 if no matching files or metric values are found.
    """
    values = [
        entry.get(metric)
        for key, entry in data.items()
        if fnmatch.fnmatch(key, pattern) and entry.get(metric) is not None
    ]
    if not values:
        return 0
    return func(values)


def get_previous_metric(db_path, watch_group, file_pattern, metric, order="DESC"):
    """
    Retrieve the most recent metric value from samples for a given file pattern.

    Args:
        db_path (str): Path to the database.
        watch_group (str): Name of the watch group.
        file_pattern (str): Glob pattern for file_path.
        metric (str): The metric to retrieve.
        order (str): 'DESC' for the most recent sample, 'ASC' for the oldest.

    Returns:
        The metric value or None if not found.
    """
    conn = __import__(
        "eventwatcher.db", fromlist=["get_db_connection"]
    ).get_db_connection(db_path)
    cur = conn.cursor()
    query = f"""
        SELECT {metric} FROM samples
        WHERE watch_group = ? AND file_path LIKE ?
        ORDER BY sample_epoch {order} LIMIT 1
    """
    cur.execute(query, (watch_group, file_pattern))
    row = cur.fetchone()
    conn.close()
    if row:
        return row[0]
    return None


def build_safe_eval_context():
    """
    Build a safe evaluation context for rule conditions.

    Returns:
        dict: Context dictionary with safe built-in functions.
    """
    return {"__builtins__": SAFE_BUILTINS}
