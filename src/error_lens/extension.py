from __future__ import annotations

import os
import typing
from pathlib import Path

from biscuit.extensions import Extension

if typing.TYPE_CHECKING:
    from biscuit.api import ExtensionsAPI


SEVERITY_ORDER: dict[str, int] = {
    "error": 0,
    "warning": 1,
    "info": 2,
    "hint": 3,
}

SEVERITY_STYLES: dict[str, dict[str, str]] = {
    "error": {"fg": "#ff4d4f", "bg": "#fff1f0", "gutter": "🔴", "glyph": "▲ Error"},
    "warning": {"fg": "#faad14", "bg": "#fffbe6", "gutter": "🟡", "glyph": "▲ Warning"},
    "info": {"fg": "#1890ff", "bg": "#e6f7ff", "gutter": "🔵", "glyph": "▲ Info"},
    "hint": {"fg": "#8c8c8c", "bg": "#f5f5f5", "gutter": "⚪", "glyph": "▲ Hint"},
}


class ErrorLens(Extension):
    """Real-time inline error and warning diagnostic decorator and problem navigator."""

    def __init__(self, api: ExtensionsAPI) -> None:
        super().__init__(api)
        self.api = api
        self.enabled: bool = True
        self.diagnostics: dict[str, list[dict]] = {}
        self.statusbar_button = None
        if hasattr(self.api, "logger") and self.api.logger:
            self.api.logger.info("Error Lens extension initialised.")

    def _normalize_path(self, file_path: str) -> str:
        return str(Path(file_path).resolve()) if file_path else ""

    def _normalize_severity(self, severity: str | None) -> str:
        if not severity:
            return "error"
        sev = str(severity).strip().lower()
        return sev if sev in SEVERITY_ORDER else "info"

    def set_diagnostics(self, file_path: str, items: list[dict]) -> None:
        """Register diagnostic list for a given file path."""
        norm_path = self._normalize_path(file_path)
        normalized_items: list[dict] = []
        for item in items:
            diag = dict(item)
            diag["severity"] = self._normalize_severity(diag.get("severity"))
            diag["line"] = int(diag.get("line", 1))
            diag["column"] = int(diag.get("column", 0))
            diag["message"] = str(diag.get("message", "")).strip()
            diag["code"] = str(diag.get("code", "")).strip() if diag.get("code") else ""
            normalized_items.append(diag)

        normalized_items.sort(
            key=lambda d: (
                d["line"],
                SEVERITY_ORDER.get(d["severity"], 99),
                d["column"],
            )
        )
        self.diagnostics[norm_path] = normalized_items
        self.update_statusbar()
        self.apply_to_active_editor()

    def clear_diagnostics(self, file_path: str | None = None) -> None:
        """Clear diagnostics for a file or across entire workspace."""
        if file_path is None:
            self.diagnostics.clear()
        else:
            norm_path = self._normalize_path(file_path)
            self.diagnostics.pop(norm_path, None)
        self.update_statusbar()
        self.clear_from_active_editor()

    def get_diagnostics(self, file_path: str) -> list[dict]:
        """Return all diagnostics registered for a file."""
        norm_path = self._normalize_path(file_path)
        return list(self.diagnostics.get(norm_path, []))

    def get_line_diagnostics(self, file_path: str, line_no: int) -> list[dict]:
        """Return all diagnostics for a specific line sorted by severity."""
        items = self.get_diagnostics(file_path)
        matching = [item for item in items if item.get("line") == line_no]
        matching.sort(key=lambda d: SEVERITY_ORDER.get(d.get("severity", "info"), 99))
        return matching

    def get_line_diagnostic(self, file_path: str, line_no: int) -> dict | None:
        """Return the highest severity diagnostic on line_no (backward compatibility)."""
        matching = self.get_line_diagnostics(file_path, line_no)
        return matching[0] if matching else None

    def format_gutter_icon(self, severity: str) -> str:
        """Return gutter icon corresponding to severity."""
        sev = self._normalize_severity(severity)
        return SEVERITY_STYLES.get(sev, SEVERITY_STYLES["info"])["gutter"]

    def format_line_diagnostic(self, diagnostics: list[dict], max_length: int = 120) -> str:
        """Format inline diagnostic annotation message with severity and overflow indicator."""
        if not diagnostics:
            return ""

        sorted_diags = sorted(
            diagnostics,
            key=lambda d: SEVERITY_ORDER.get(self._normalize_severity(d.get("severity")), 99)
        )
        primary = sorted_diags[0]
        sev = self._normalize_severity(primary.get("severity"))
        glyph = SEVERITY_STYLES.get(sev, SEVERITY_STYLES["info"])["glyph"]

        code_part = f" [{primary['code']}]" if primary.get("code") else ""
        msg = primary.get("message", "")
        formatted = f"{glyph}{code_part}: {msg}"

        overflow_count = len(sorted_diags) - 1
        if overflow_count > 0:
            overflow_text = f" [+{overflow_count} more problem{'s' if overflow_count > 1 else ''}]"
        else:
            overflow_text = ""

        if len(formatted) + len(overflow_text) > max_length:
            avail = max_length - len(overflow_text) - 3
            if avail > 10:
                formatted = formatted[:avail] + "..."

        return f"    {formatted}{overflow_text}"

    def get_workspace_counts(self) -> dict[str, int]:
        """Compute aggregate diagnostic counts by severity."""
        counts = {"error": 0, "warning": 0, "info": 0, "hint": 0}
        for file_diags in self.diagnostics.values():
            for diag in file_diags:
                sev = self._normalize_severity(diag.get("severity"))
                counts[sev] = counts.get(sev, 0) + 1
        return counts

    def update_statusbar(self) -> None:
        """Update problem summary indicator on the statusbar."""
        if not self.statusbar_button:
            return
        counts = self.get_workspace_counts()
        errs = counts.get("error", 0)
        warns = counts.get("warning", 0)
        text = f"{errs} Errors, {warns} Warnings"
        if hasattr(self.statusbar_button, "change_text"):
            self.statusbar_button.change_text(text)
        elif hasattr(self.statusbar_button, "set_text"):
            self.statusbar_button.set_text(text)

    def next_error(self, file_path: str, current_line: int) -> tuple[str, int] | None:
        """Navigate to the next diagnostic line in file or workspace."""
        norm_path = self._normalize_path(file_path)
        items = self.diagnostics.get(norm_path, [])
        lines = sorted({d["line"] for d in items if d.get("line") is not None})
        for line in lines:
            if line > current_line:
                return (norm_path, line)

        # Wrap around or check other files
        all_files = sorted(self.diagnostics.keys())
        if not all_files:
            return None

        if norm_path in all_files:
            cur_idx = all_files.index(norm_path)
            for i in range(1, len(all_files) + 1):
                next_file = all_files[(cur_idx + i) % len(all_files)]
                next_items = self.diagnostics.get(next_file, [])
                if next_items:
                    return (next_file, min(d["line"] for d in next_items))
        else:
            first_file = all_files[0]
            first_items = self.diagnostics.get(first_file, [])
            if first_items:
                return (first_file, min(d["line"] for d in first_items))

        return None

    def prev_error(self, file_path: str, current_line: int) -> tuple[str, int] | None:
        """Navigate to the previous diagnostic line in file or workspace."""
        norm_path = self._normalize_path(file_path)
        items = self.diagnostics.get(norm_path, [])
        lines = sorted({d["line"] for d in items if d.get("line") is not None}, reverse=True)
        for line in lines:
            if line < current_line:
                return (norm_path, line)

        all_files = sorted(self.diagnostics.keys())
        if not all_files:
            return None

        if norm_path in all_files:
            cur_idx = all_files.index(norm_path)
            for i in range(1, len(all_files) + 1):
                prev_file = all_files[(cur_idx - i) % len(all_files)]
                prev_items = self.diagnostics.get(prev_file, [])
                if prev_items:
                    return (prev_file, max(d["line"] for d in prev_items))
        else:
            last_file = all_files[-1]
            last_items = self.diagnostics.get(last_file, [])
            if last_items:
                return (last_file, max(d["line"] for d in last_items))

        return None

    def toggle(self) -> bool:
        """Toggle inline error lens decorations on/off."""
        self.enabled = not self.enabled
        if self.enabled:
            self.apply_to_active_editor()
            if hasattr(self.api, "notifications") and self.api.notifications:
                self.api.notifications.info("Error Lens enabled.")
        else:
            self.clear_from_active_editor()
            if hasattr(self.api, "notifications") and self.api.notifications:
                self.api.notifications.info("Error Lens disabled.")
        return self.enabled

    def _resolve_text_widget(self, editor: typing.Any) -> typing.Any:
        if not editor:
            return None
        return getattr(editor, "text", None) or getattr(getattr(editor, "content", None), "text", None)

    def apply_decorations(self, editor: typing.Any, file_path: str | None = None) -> None:
        """Render diagnostic line tags and inline annotations onto editor widget."""
        if not self.enabled:
            return
        text_widget = self._resolve_text_widget(editor)
        if not text_widget or not hasattr(text_widget, "tag_add"):
            return

        target_path = file_path or getattr(editor, "path", None)
        if not target_path:
            return
        norm_path = self._normalize_path(str(target_path))
        items = self.diagnostics.get(norm_path, [])
        if not items:
            return

        lines_map: dict[int, list[dict]] = {}
        for item in items:
            line_no = item.get("line", 1)
            lines_map.setdefault(line_no, []).append(item)

        for line_no, diags in lines_map.items():
            primary = min(diags, key=lambda d: SEVERITY_ORDER.get(d.get("severity", "info"), 99))
            sev = primary.get("severity", "error")
            style = SEVERITY_STYLES.get(sev, SEVERITY_STYLES["info"])
            tag_name = f"error_lens_{sev}"

            try:
                if hasattr(text_widget, "tag_config"):
                    text_widget.tag_config(
                        tag_name,
                        background=style["bg"],
                        foreground=style["fg"]
                    )
                text_widget.tag_add(tag_name, f"{line_no}.0", f"{line_no}.end")
            except Exception:
                pass

    def clear_decorations(self, editor: typing.Any) -> None:
        """Clear diagnostic tags from editor widget."""
        text_widget = self._resolve_text_widget(editor)
        if not text_widget or not hasattr(text_widget, "tag_remove"):
            return
        for sev in SEVERITY_STYLES:
            try:
                text_widget.tag_remove(f"error_lens_{sev}", "1.0", "end")
            except Exception:
                pass

    def apply_to_active_editor(self) -> None:
        """Apply decorations to currently active editor if available."""
        if hasattr(self.api, "editors") and hasattr(self.api.editors, "active_editor"):
            editor = self.api.editors.active_editor
            if editor:
                self.apply_decorations(editor)

    def clear_from_active_editor(self) -> None:
        """Clear decorations from currently active editor."""
        if hasattr(self.api, "editors") and hasattr(self.api.editors, "active_editor"):
            editor = self.api.editors.active_editor
            if editor:
                self.clear_decorations(editor)

    def jump_to_next(self) -> None:
        """Command: Jump to next diagnostic in active editor."""
        editor = getattr(getattr(self.api, "editors", None), "active_editor", None)
        path = getattr(editor, "path", "")
        cur_line = 1
        text_widget = self._resolve_text_widget(editor)
        if text_widget and hasattr(text_widget, "index"):
            try:
                cur_line = int(str(text_widget.index("insert")).split(".")[0])
            except Exception:
                cur_line = 1

        target = self.next_error(str(path), cur_line)
        if target:
            tgt_file, tgt_line = target
            if hasattr(self.api, "editors") and hasattr(self.api.editors, "open_editor"):
                self.api.editors.open_editor(tgt_file)
            if hasattr(self.api, "notifications") and self.api.notifications:
                self.api.notifications.info(f"Jumped to line {tgt_line} ({Path(tgt_file).name})")

    def jump_to_prev(self) -> None:
        """Command: Jump to previous diagnostic in active editor."""
        editor = getattr(getattr(self.api, "editors", None), "active_editor", None)
        path = getattr(editor, "path", "")
        cur_line = 1
        text_widget = self._resolve_text_widget(editor)
        if text_widget and hasattr(text_widget, "index"):
            try:
                cur_line = int(str(text_widget.index("insert")).split(".")[0])
            except Exception:
                cur_line = 1

        target = self.prev_error(str(path), cur_line)
        if target:
            tgt_file, tgt_line = target
            if hasattr(self.api, "editors") and hasattr(self.api.editors, "open_editor"):
                self.api.editors.open_editor(tgt_file)
            if hasattr(self.api, "notifications") and self.api.notifications:
                self.api.notifications.info(f"Jumped to line {tgt_line} ({Path(tgt_file).name})")

    def install(self) -> None:
        """Register commands and statusbar item for Error Lens."""
        if hasattr(self.api, "commands") and hasattr(self.api.commands, "register_command"):
            self.api.commands.register_command("error_lens.toggle", self.toggle)
            self.api.commands.register_command("error_lens.next_error", self.jump_to_next)
            self.api.commands.register_command("error_lens.prev_error", self.jump_to_prev)
            self.api.commands.register_command("error_lens.clear", lambda: self.clear_diagnostics())

        if hasattr(self.api, "statusbar") and hasattr(self.api.statusbar, "add_button"):
            try:
                self.statusbar_button = self.api.statusbar.add_button(
                    text="0 Errors, 0 Warnings",
                    callback=self.toggle,
                    description="Error Lens: Toggle problem annotations",
                )
                if hasattr(self.statusbar_button, "show"):
                    self.statusbar_button.show()
            except Exception:
                pass

        if hasattr(self.api, "logger") and self.api.logger:
            self.api.logger.info("Error Lens extension installed.")
