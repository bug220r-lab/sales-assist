import json
import socket

from sales_credit_evidence.__main__ import main
from sales_credit_evidence.demo import run_demo


def test_demo_has_no_network_auth_or_credit_decision(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("network prohibited in demo")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert main(["--demo"]) == 0
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary["complete"] is True
    assert summary["credit_classification"] == "NOT_EVALUATED"
    assert summary["thread_count"] == 2
    assert "@" not in output
    result = run_demo()
    reply = result.conversations[0].threads[1]
    assert reply.prior_target_thread_ids == (30001,)
    assert reply.send_time_verified is False
    assert reply.delivery_verified is False


def test_default_entry_point_is_disabled(capsys):
    assert main([]) == 0
    assert "live access disabled" in capsys.readouterr().out
