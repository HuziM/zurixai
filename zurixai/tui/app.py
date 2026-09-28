"""ZurixAI TUI — Interactive dashboard (Week 5, minimal slice)."""

from __future__ import annotations

from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import Footer, Header, Static

STATUS_TEXT = (
    "[bold]ZurixAI Dashboard[/bold]\n\n"
    "[green]Checks:[/green] imports, supply-chain, drift, rules\n"
    "[green]Tests:[/green] micro-mock (stub)\n"
    "[green]Bugs:[/green] stack-trace parser (stub)\n"
    "[green]Schema:[/green] detect + migration patches (stub)\n\n"
    "[dim]Press [bold]q[/bold] to quit[/dim]"
)


class ZurixDashboard(App):
    """Minimal ZurixAI TUI dashboard."""

    TITLE = "ZurixAI"
    SUB_TITLE = "Agentic Quality Engine"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(STATUS_TEXT, id="status")
        yield Footer()


def run_tui() -> None:
    """Launch the TUI (blocking)."""
    app = ZurixDashboard()
    app.run()
