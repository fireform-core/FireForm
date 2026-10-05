from datetime import timedelta
from importlib import import_module
from unittest.mock import MagicMock, patch

init_db = import_module("app.db.init_db")


def test_seed_template_uses_timezone_aware_utc_datetime():
    session = MagicMock()
    session.exec.return_value.first.return_value = None

    with patch.object(init_db, "Session") as mock_session:
        mock_session.return_value.__enter__.return_value = session

        init_db.seed_db()

    template = session.add.call_args.args[0]

    assert template.created_at.tzinfo is not None
    assert template.created_at.utcoffset() == timedelta(0)
    session.commit.assert_called_once()