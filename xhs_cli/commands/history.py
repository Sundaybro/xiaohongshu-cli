"""Read the current account's server-side note browsing history."""

from datetime import datetime

import click
from rich.table import Table

from ..formatter import console, print_info
from ._common import handle_command, structured_output_options


def _browse_time(value):
    try:
        timestamp = float(value)
        if timestamp > 100_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value or "")


@click.command("history")
@click.option("--cursor", default="", help="Continuation cursor returned by the previous page")
@click.option("--note-index", default=0, type=click.IntRange(min=0), help="Previous page's next_note_index")
@structured_output_options
@click.pass_context
def history(ctx, cursor: str, note_index: int, as_json: bool, as_yaml: bool):
    """Read the current account's note browsing history (web profile history tab)."""
    def _render(data):
        table = Table(title="笔记浏览历史")
        table.add_column("浏览时间")
        table.add_column("标题")
        table.add_column("作者")
        table.add_column("笔记 ID")
        for note in data["notes"]:
            user = note.get("user") or {}
            table.add_row(
                _browse_time(note.get("browse_time")), str(note.get("title", "")),
                str(user.get("nickname", "")), str(note.get("id", "")),
            )
        console.print(table)
        if data["has_more"]:
            if data["cursor"]:
                print_info(f"More history — use --cursor {data['cursor']} --note-index {data['next_note_index']}")
            else:
                print_info("API reports more history but returned no continuation cursor")

    handle_command(
        ctx,
        action=lambda client: client.get_browsing_history(cursor=cursor, note_index=note_index),
        render=_render,
        as_json=as_json,
        as_yaml=as_yaml,
    )
