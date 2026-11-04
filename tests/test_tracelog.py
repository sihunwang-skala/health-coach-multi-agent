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


def test_windows_pick_the_busiest_two_weeks_and_summary_follows_end(tmp_path):
    db = tmp_path / "t.db"
    for day, n in (("2026-09-01", 1), ("2026-10-10", 5), ("2026-10-11", 6), ("2026-10-22", 4), ("2026-11-03", 1)):
        for i in range(n):
            tracelog.log_event("u01", "q", {"route": "diet", "answer": "a", "cost": 0.01}, ts=f"{day}T12:0{i}:00", path=db)
    w = tracelog.windows(path=db)
    assert w["busiest"] == {"start": "2026-10-10", "end": "2026-10-23", "messages": 15}     # the Oct 10-22 burst, not the newest days
    assert w["blocks"][0]["end"] == "2026-11-03" and w["blocks"][0]["messages"] == 5 and w["blocks"][-1]["start"] <= "2026-09-01"
    s = tracelog.summary(path=db, end="2026-10-23")
    assert s["messages"] == 15 and s["days"][0] == "2026-10-10" and s["days"][-1] == "2026-10-23"
    assert tracelog.summary(path=db, end="2026-11-03")["messages"] == 5
