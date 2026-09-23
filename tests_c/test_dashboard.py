from datetime import date

import pandas as pd
from ui.dashboard import transaction_slice


def test_period_is_inclusive_and_gid_checks_both_directions():
    tx = pd.DataFrame({"src": [1, 2, 3, 1], "dst": [2, 1, 4, 2], "date": ["2026-09-01", "2026-09-02T23:59:00Z", "2026-09-02", "2026-09-03"], "sum_kzt": [10, 20, 30, 40]})
    result = transaction_slice(tx, date(2026, 9, 1), date(2026, 9, 2), 1)
    assert result.sum_kzt.tolist() == [10, 20]
    assert len(tx) == 4
