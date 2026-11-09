"""Unit tests for administrator-defined panic actions."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from scheduler import panic
from scheduler.main import _reconcile_on_startup    # type: ignore
from scheduler.panic import PanicMailSettings, PanicMode, PanicSettings


def test_panic_runs_script_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Panic executes the configured script as an argument vector."""
    command = Mock()
    monkeypatch.setattr(panic.subprocess, "run", command)
    handler = PanicMode(PanicSettings(script=Path("/opt/panic.sh")))

    handler.trigger("reconciliation failed")

    assert command.call_args.args[0] == ["/opt/panic.sh"]
    assert command.call_args.kwargs["check"] is True
    assert "shell" not in command.call_args.kwargs


def test_script_failure_does_not_prevent_email(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Email notification is attempted even when the script fails."""
    smtp_file = tmp_path / "smtp.yml"
    smtp_file.write_text(
        "host: mail.example\nport: 587\nusername: alerts@example\nuse_tls: true\n",
        encoding="utf-8",
    )
    secret_file = tmp_path / "smtp-secret"
    secret_file.write_text("smtp-password", encoding="utf-8")
    smtp_client = Mock()
    smtp_client.__enter__ = Mock(return_value=smtp_client)
    smtp_client.__exit__ = Mock(return_value=False)
    smtp = Mock(return_value=smtp_client)
    monkeypatch.setattr(panic.subprocess, "run", Mock(side_effect=OSError("failed")))
    monkeypatch.setattr(panic.smtplib, "SMTP", smtp)
    settings = PanicSettings(
        script=Path("/opt/panic.sh"),
        notify=True,
        mail=PanicMailSettings(
            send=True,
            to="admin@example.test",
            subject="Panic",
            body="Backend unavailable",
            config_file=smtp_file,
            secret_file=secret_file,
        ),
    )

    PanicMode(settings).trigger("three reconciliation failures")

    smtp.assert_called_once_with("mail.example", 587, timeout=10)
    smtp_client.starttls.assert_called_once_with()
    smtp_client.login.assert_called_once_with("alerts@example", "smtp-password")
    message = smtp_client.send_message.call_args.args[0]
    assert message["To"] == "admin@example.test"
    assert "three reconciliation failures" in message.get_content()


def test_panic_can_disable_all_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disabled panic mode performs no configured action."""
    command = Mock()
    monkeypatch.setattr(panic.subprocess, "run", command)
    handler = PanicMode(PanicSettings(mode="disabled", script=Path("/opt/panic.sh")))

    handler.trigger("reconciliation failed")

    command.assert_not_called()


def test_panic_settings_load_nested_configuration(tmp_path: Path) -> None:
    """Panic settings load from the application YAML section."""
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        "panic:\n  mode: on_error\n  retry: 3\n  notify: false\n",
        encoding="utf-8",
    )

    settings = PanicSettings.from_file(config_file)

    assert settings.retry == 3
    assert settings.mode == "on_error"
    assert settings.notify is False


def test_startup_reconciliation_triggers_after_retry_threshold() -> None:
    """Panic runs only after all configured startup attempts fail."""
    lease_scheduler = Mock()
    lease_scheduler.reconcile.side_effect = [RuntimeError(), RuntimeError(), RuntimeError()]
    panic_mode = Mock()
    panic_mode.settings = PanicSettings(retry=3)

    assert _reconcile_on_startup(lease_scheduler, panic_mode) is False

    assert lease_scheduler.reconcile.call_count == 3
    panic_mode.trigger.assert_called_once_with("Reconciliation failed after 3 attempts.")


def test_startup_reconciliation_stops_retrying_after_success() -> None:
    """A successful retry clears the incident without triggering panic."""
    lease_scheduler = Mock()
    lease_scheduler.reconcile.side_effect = [RuntimeError(), None]
    panic_mode = Mock()
    panic_mode.settings = PanicSettings(retry=3)

    assert _reconcile_on_startup(lease_scheduler, panic_mode) is True

    assert lease_scheduler.reconcile.call_count == 2
    panic_mode.trigger.assert_not_called()
