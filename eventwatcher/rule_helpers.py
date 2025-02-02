import fnmatch

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
        # Return 0 so that subtraction (e.g. now - 0) yields a large number, preventing the rule from triggering.
        return 0
    return func(values)

def get_previous_metric(db_path, watch_group, file_pattern, metric, order='DESC'):
    """
    Retrieve the most recent metric value from exploded_samples for a given file pattern.

    Args:
        db_path (str): Path to the database.
        watch_group (str): Name of the watch group.
        file_pattern (str): Glob pattern for file_path.
        metric (str): The metric to retrieve.
        order (str): 'DESC' for the most recent sample, 'ASC' for the oldest.

    Returns:
        The metric value or None if not found.
    """
    conn = __import__('eventwatcher.db', fromlist=['get_db_connection']).get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute(f'''
        SELECT {metric} FROM exploded_samples
        WHERE watch_group = ?
        ORDER BY sample_epoch {order} LIMIT 1
    ''', (watch_group,))
    row = cur.fetchone()
    conn.close()
    if row:
        return row[0]
    return None
