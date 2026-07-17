"""Tests for ``python -m substrate`` (the health-check entry point)."""
from __future__ import annotations

import pytest

from substrate import __version__
from substrate.__main__ import _self_check, main


def test_self_check_passes() -> None:
    assert _self_check() is True


def test_main_returns_zero_on_healthy_install(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert __version__ in out
    assert "OK" in out


def test_version_flag_prints_only_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == __version__


def test_short_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["-V"]) == 0
    assert capsys.readouterr().out.strip() == __version__
