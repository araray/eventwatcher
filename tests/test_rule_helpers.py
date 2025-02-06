from eventwatcher.rule_helpers import aggregate_metric


def test_aggregate_metric_no_match():
    # With no matching keys, aggregate_metric should return 0.
    sample_data = {"/path/to/file.txt": {"size": 123, "last_modified": 1600000000}}
    result = aggregate_metric(sample_data, "*.nomatch", "last_modified", min)
    assert result == 0
