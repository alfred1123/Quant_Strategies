import logging

from log_config import setup_logging, LOG_FORMAT, LOG_DATEFMT


class TestSetupLogging:
    def test_sets_info_level_by_default(self):
        root = logging.getLogger()
        # Reset handlers so basicConfig can re-apply
        root.handlers.clear()
        setup_logging()
        assert root.level == logging.INFO

    def test_sets_debug_level_when_requested(self):
        root = logging.getLogger()
        root.handlers.clear()
        setup_logging(debug=True)
        assert root.level == logging.DEBUG
        # Reset to INFO so other tests aren't affected
        root.handlers.clear()
        setup_logging()

    def test_format_string_defined(self):
        assert "%(levelname)s" in LOG_FORMAT
        assert "%(name)s" in LOG_FORMAT

    def test_datefmt_defined(self):
        assert "%Y" in LOG_DATEFMT
