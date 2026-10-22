from coach import tracelog


def test_log_alert_and_summary(tmp_path):
    db = tmp_path / "t.db"
    tracelog.log_event("u06", "I feel chest pain", {"route": "emergency", "latency_s": 0.01, "calls": 0, "cost": 0}, path=db)
    i = tracelog.log_event("u01", "walk after dinner?", {"route": "exercise", "domains": ["exercise"], "cost": 0.003,
                                                       "safety_notes": [{"id": "R1"}], "latency_s": 15}, path=db)
    s = tracelog.summary(path=db)
    assert s["messages"] == 2 and s["open_alerts"] == 1 and s["rules"] == {"R1": 1}
    ev = tracelog.rows("SELECT * FROM events", path=db)
    assert {e["user_id"] for e in ev} == {"u06", "u01"} and all("name" not in e for e in ev)   # ids only, no names
    assert tracelog.set_alert_status(i, "handled", path=db) == 0    # a normal message is not an alert
    assert tracelog.set_alert_status(ev[0]["id"], "handled", path=db) == 1
    assert tracelog.summary(path=db)["open_alerts"] == 0
