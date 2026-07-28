"""Tests for public engine and session helpers."""

import pytest
from sqlalchemy.engine import Engine

import sqlarec.database as database
from sqlarec import get_engine, init_engine, new_session


def test_get_engine_requires_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(database, "_engine", None)

    with pytest.raises(RuntimeError, match="init_engine"):
        get_engine()


def test_init_engine_registers_default_engine() -> None:
    engine = init_engine("sqlite:///:memory:")

    assert isinstance(engine, Engine)
    assert get_engine() is engine
    engine.dispose()


def test_new_session_uses_supplied_engine() -> None:
    engine = init_engine("sqlite:///:memory:")

    with new_session(engine) as session:
        assert session.get_bind() is engine
        assert session.autoflush is False
        assert session.expire_on_commit is False

    engine.dispose()
