"""Tests for the public synchronous session helper."""

from sqlalchemy import create_engine

from sqlarec import new_session_from_engine


def test_new_session_from_engine_uses_sqlarec_defaults() -> None:
    engine = create_engine("sqlite:///:memory:")

    with new_session_from_engine(engine) as session:
        assert session.get_bind() is engine
        assert session.autoflush is False
        assert session.expire_on_commit is False

    engine.dispose()


def test_new_session_from_engine_forwards_sessionmaker_options() -> None:
    engine = create_engine("sqlite:///:memory:")

    with new_session_from_engine(
        engine,
        autoflush=True,
        expire_on_commit=True,
        autobegin=False,
        info={"scope": "test"},
    ) as session:
        assert session.autoflush is True
        assert session.expire_on_commit is True
        assert session.autobegin is False
        assert session.info == {"scope": "test"}

    engine.dispose()
