"""Accounts and sign-in on the control server (design 2026-10-12): session unit tests."""

from claimstone import control


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_sessions_have_ids_methods_and_an_absolute_lifetime():
    clock = Clock()
    sessions = control.Sessions(idle_seconds=100, absolute_seconds=1000, clock=clock)
    token, s = sessions.create("a", "Alpha", role="admin", method="password")
    idle_token, _ = sessions.create("b", "Beta")
    assert s.session_id and s.session_id != token and s.method == "password" and s.role == "admin"
    # activity every 90 s keeps it alive far past the 100 s idle window...
    for step in range(1, 11):
        clock.now = 90.0 * step
        assert sessions.get(token) is not None, f"died at {clock.now}"
    assert clock.now == 900.0
    assert sessions.get(idle_token) is None          # ...which an untouched session did not survive
    clock.now = 990.0
    assert sessions.get(token) is not None
    # ...but never past the absolute one, though the idle window was refreshed 11 s ago
    clock.now = 1001.0
    assert sessions.get(token) is None


def test_the_idle_window_alone_still_expires_a_session():
    clock = Clock()
    sessions = control.Sessions(idle_seconds=100, absolute_seconds=1000, clock=clock)
    token, _ = sessions.create("a", "Alpha")
    clock.now = 101.0
    assert sessions.get(token) is None


def test_old_call_shape_defaults_to_an_operator_password_session():
    token, s = control.Sessions().create("a", "Alpha")
    assert (s.role, s.method, s.must_change_password) == ("operator", "password", False)
    assert s.created_at and s.csrf_token and s.csrf_token != token


def test_list_end_others_and_end_operator():
    sessions = control.Sessions()
    t1, _ = sessions.create("a", "Alpha", role="operator", method="password")
    t2, _ = sessions.create("a", "Alpha", role="operator", method="google")
    t3, _ = sessions.create("b", "Beta", role="operator", method="password")
    listed = sessions.list_for("a", current_token=t1)
    assert {x["method"] for x in listed} == {"password", "google"}
    assert [x["current"] for x in listed].count(True) == 1
    assert sessions.end_others("a", keep_token=t1) == 1
    assert sessions.get(t2) is None and sessions.get(t1) is not None and sessions.get(t3) is not None
    assert sessions.end_operator("a") == 1 and sessions.get(t1) is None


def test_list_for_never_exposes_a_token():
    sessions = control.Sessions()
    t1, s1 = sessions.create("a", "Alpha")
    t2, s2 = sessions.create("a", "Alpha", method="google")
    listed = sessions.list_for("a", current_token=t1)
    blob = repr(listed)
    assert t1 not in blob and t2 not in blob
    assert s1.csrf_token not in blob and s2.csrf_token not in blob
    assert {x["session_id"] for x in listed} == {s1.session_id, s2.session_id}
    assert all(set(x) == {"session_id", "created_at", "last_seen", "method", "current"}
               for x in listed)


def test_ended_and_expired_sessions_leave_no_state_behind():
    clock = Clock()
    sessions = control.Sessions(idle_seconds=100, absolute_seconds=1000, clock=clock)
    gone, _ = sessions.create("a", "Alpha")
    kept, _ = sessions.create("b", "Beta")
    sessions.end(gone)
    clock.now = 101.0                       # `kept` is now idle-expired; create prunes it
    sessions.create("c", "Gamma")
    tables = (sessions._expires, sessions._dies, sessions._rows, sessions._seen)
    assert all(gone not in t and kept not in t for t in tables)
    assert all(len(t) == 1 for t in tables)


def test_must_change_password_can_be_cleared():
    sessions = control.Sessions()
    token, s = sessions.create("a", "Alpha", role="operator", method="password", must_change=True)
    assert s.must_change_password is True
    sessions.clear_must_change(token)
    assert sessions.get(token).must_change_password is False
