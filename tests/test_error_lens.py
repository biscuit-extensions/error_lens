from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.error_lens import setup
from src.error_lens.extension import ErrorLens


class TestErrorLensExtension:
    def test_extension_setup(self, app_instance) -> None:
        setup(app_instance.api)
        ext = ErrorLens(app_instance.api)
        ext.set_diagnostics("app.py", [{"line": 10, "severity": "error", "message": "SyntaxError: invalid syntax"}])
        diag = ext.get_line_diagnostic("app.py", 10)
        assert diag is not None
        assert diag["message"] == "SyntaxError: invalid syntax"
        assert ext.format_gutter_icon("error") == "🔴"
