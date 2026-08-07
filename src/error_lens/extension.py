from __future__ import annotations

import typing

from biscuit.extensions import Extension

if typing.TYPE_CHECKING:
    from biscuit.api import ExtensionsAPI


class ErrorLens(Extension):
    """Inline error and warning diagnostic messages directly on editor code lines."""

    def __init__(self, api: ExtensionsAPI) -> None:
        super().__init__(api)
        self.api = api
        self.diagnostics: dict[str, list[dict]] = {}
        self.api.logger.info("Error Lens extension initialised.")

    def set_diagnostics(self, file_path: str, items: list[dict]) -> None:
        self.diagnostics[file_path] = items

    def get_line_diagnostic(self, file_path: str, line_no: int) -> dict | None:
        items = self.diagnostics.get(file_path, [])
        for item in items:
            if item.get("line") == line_no:
                return item
        return None

    def format_gutter_icon(self, severity: str) -> str:
        return "🔴" if severity == "error" else ("🟡" if severity == "warning" else "🔵")

    def install(self) -> None:
        self.api.logger.info("Error Lens extension installed.")
