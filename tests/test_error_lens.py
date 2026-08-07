from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.error_lens import setup
from src.error_lens.extension import ErrorLens


class TestErrorLensExtension:
    def test_setup_and_registration(self, mock_api) -> None:
        setup(mock_api)
        assert "error_lens" in mock_api.registered_extensions
        ext = mock_api.registered_extensions["error_lens"]
        assert isinstance(ext, ErrorLens)

    def test_commands_registration(self, mock_api) -> None:
        ext = ErrorLens(mock_api)
        ext.install()
        assert "error_lens.toggle" in mock_api.commands.commands
        assert "error_lens.next_error" in mock_api.commands.commands
        assert "error_lens.prev_error" in mock_api.commands.commands
        assert "error_lens.clear" in mock_api.commands.commands

    def test_diagnostics_storage_and_severity_sorting(self, mock_api) -> None:
        ext = ErrorLens(mock_api)
        items = [
            {"line": 15, "column": 5, "severity": "info", "message": "Consider type hint"},
            {"line": 10, "column": 2, "severity": "warning", "message": "Unused variable 'x'"},
            {"line": 10, "column": 8, "severity": "error", "message": "SyntaxError: unexpected token"},
            {"line": 20, "column": 0, "severity": "hint", "message": "Line length > 88"},
        ]
        ext.set_diagnostics("src/module.py", items)
        retrieved = ext.get_diagnostics("src/module.py")
        assert len(retrieved) == 4

        # For line 10, error should rank ahead of warning
        line_10_diags = ext.get_line_diagnostics("src/module.py", 10)
        assert len(line_10_diags) == 2
        assert line_10_diags[0]["severity"] == "error"
        assert line_10_diags[1]["severity"] == "warning"

        # get_line_diagnostic backward compatibility
        top_diag = ext.get_line_diagnostic("src/module.py", 10)
        assert top_diag is not None
        assert top_diag["severity"] == "error"

    def test_line_diagnostic_formatting(self, mock_api) -> None:
        ext = ErrorLens(mock_api)
        diags = [
            {"line": 12, "severity": "error", "code": "E001", "message": "undefined variable 'foo'"},
            {"line": 12, "severity": "warning", "code": "W002", "message": "imported but unused"},
        ]
        formatted = ext.format_line_diagnostic(diags)
        assert "▲ Error [E001]: undefined variable 'foo'" in formatted
        assert "[+1 more problem]" in formatted

        # Single diagnostic without overflow
        formatted_single = ext.format_line_diagnostic([diags[0]])
        assert "[+" not in formatted_single
        assert "▲ Error [E001]: undefined variable 'foo'" in formatted_single

        # Truncation when exceeding max_length
        long_diag = [{"line": 1, "severity": "error", "message": "A" * 200}]
        formatted_long = ext.format_line_diagnostic(long_diag, max_length=50)
        assert len(formatted_long.strip()) <= 55
        assert "..." in formatted_long

    def test_gutter_icons(self, mock_api) -> None:
        ext = ErrorLens(mock_api)
        assert ext.format_gutter_icon("error") == "🔴"
        assert ext.format_gutter_icon("warning") == "🟡"
        assert ext.format_gutter_icon("info") == "🔵"
        assert ext.format_gutter_icon("hint") == "⚪"
        assert ext.format_gutter_icon("UNKNOWN") == "🔵"

    def test_navigation_next_and_prev(self, mock_api) -> None:
        ext = ErrorLens(mock_api)
        file1 = "file1.py"
        file2 = "file2.py"
        ext.set_diagnostics(file1, [
            {"line": 10, "severity": "error", "message": "Err1"},
            {"line": 25, "severity": "warning", "message": "Warn1"},
        ])
        ext.set_diagnostics(file2, [
            {"line": 5, "severity": "error", "message": "Err2"},
        ])

        # Next within file1
        next_pos = ext.next_error(file1, 10)
        assert next_pos is not None
        assert next_pos[1] == 25

        # Prev within file1
        prev_pos = ext.prev_error(file1, 25)
        assert prev_pos is not None
        assert prev_pos[1] == 10

        # Wrap around from last line of file1 to file2 or start
        wrap_pos = ext.next_error(file1, 30)
        assert wrap_pos is not None

    def test_clear_diagnostics(self, mock_api) -> None:
        ext = ErrorLens(mock_api)
        ext.set_diagnostics("a.py", [{"line": 1, "severity": "error", "message": "msg"}])
        ext.set_diagnostics("b.py", [{"line": 2, "severity": "warning", "message": "msg"}])
        assert len(ext.diagnostics) == 2

        ext.clear_diagnostics("a.py")
        assert len(ext.get_diagnostics("a.py")) == 0
        assert len(ext.get_diagnostics("b.py")) == 1

        ext.clear_diagnostics()
        assert len(ext.diagnostics) == 0

    def test_statusbar_summary_and_toggle(self, mock_api) -> None:
        ext = ErrorLens(mock_api)
        ext.install()
        ext.set_diagnostics("test.py", [
            {"line": 1, "severity": "error", "message": "err"},
            {"line": 2, "severity": "warning", "message": "warn1"},
            {"line": 3, "severity": "warning", "message": "warn2"},
        ])
        counts = ext.get_workspace_counts()
        assert counts["error"] == 1
        assert counts["warning"] == 2
        assert "1 Errors, 2 Warnings" in ext.statusbar_button.text

        # Toggle disables and enables
        assert ext.enabled is True
        assert ext.toggle() is False
        assert ext.enabled is False
        assert ext.toggle() is True
        assert ext.enabled is True

    def test_editor_decorations_apply_and_clear(self, mock_api) -> None:
        ext = ErrorLens(mock_api)
        mock_editor = MagicMock()
        mock_editor.path = "app.py"
        mock_text = MagicMock()
        mock_editor.text = mock_text

        ext.set_diagnostics("app.py", [
            {"line": 8, "severity": "error", "message": "Syntax Error"},
        ])
        ext.apply_decorations(mock_editor)
        mock_text.tag_config.assert_called_with("error_lens_error", background="#fff1f0", foreground="#ff4d4f")
        mock_text.tag_add.assert_called_with("error_lens_error", "8.0", "8.end")

        ext.clear_decorations(mock_editor)
        mock_text.tag_remove.assert_any_call("error_lens_error", "1.0", "end")

    def test_app_instance_compatibility(self, app_instance) -> None:
        setup(app_instance.api)
        ext = ErrorLens(app_instance.api)
        ext.set_diagnostics("app.py", [{"line": 10, "severity": "error", "message": "SyntaxError: invalid syntax"}])
        diag = ext.get_line_diagnostic("app.py", 10)
        assert diag is not None
        assert diag["message"] == "SyntaxError: invalid syntax"
        assert ext.format_gutter_icon("error") == "🔴"
