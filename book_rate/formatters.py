import csv
import io
import json
from typing import List, Optional
from rich.console import Console
from rich.table import Table

from book_rate.models import Work


def format_markdown_table(works: List[Work]) -> str:
    """Format a list of Work objects into a Markdown table as specified by the prompt."""
    headers = ["書名", "原作者", "work", "Open Library 分數／人數", "Google Books 分數／人數", "Goodreads 分數／人數", "豆瓣 分數／人數"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |"
    ]

    for work in works:
        ol_summary = work.get_rating_summary("Open Library")
        gb_summary = work.get_rating_summary("Google Books")
        gr_summary = work.get_rating_summary("Goodreads")
        db_summary = work.get_rating_summary("Douban")
        
        row = [
            work.title,
            work.author,
            work.work_id,
            ol_summary,
            gb_summary,
            gr_summary,
            db_summary
        ]
        # Clean newlines or bar characters in text for markdown table safety
        safe_row = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(safe_row) + " |")

    return "\n".join(lines)


def print_rich_table(works: List[Work], console: Optional[Console] = None) -> None:
    """Print an attractive color-highlighted table in the terminal using Rich."""
    if console is None:
        console = Console()

    table = Table(title="📚 圖書跨平台版本與評分整合 (Books Score MVP)", show_header=True, header_style="bold cyan")
    table.add_column("書名", style="bold white", width=25)
    table.add_column("原作者", style="green", width=18)
    table.add_column("work (ID)", style="dim magenta", width=22)
    table.add_column("Open Library 分數／人數", style="yellow", justify="center")
    table.add_column("Google Books 分數／人數", style="blue", justify="center")
    table.add_column("Goodreads 分數／人數", style="magenta", justify="center")
    table.add_column("豆瓣 分數／人數", style="red", justify="center")

    for work in works:
        ol_summary = work.get_rating_summary("Open Library")
        gb_summary = work.get_rating_summary("Google Books")
        gr_summary = work.get_rating_summary("Goodreads")
        db_summary = work.get_rating_summary("Douban")
        table.add_row(
            work.title,
            work.author,
            work.work_id,
            ol_summary,
            gb_summary,
            gr_summary,
            db_summary
        )

    console.print(table)


def format_csv(works: List[Work]) -> str:
    """Format works list as CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["書名", "原作者", "work", "Open Library 分數／人數", "Google Books 分數／人數", "Goodreads 分數／人數", "豆瓣 分數／人數"])

    for work in works:
        ol_summary = work.get_rating_summary("Open Library")
        gb_summary = work.get_rating_summary("Google Books")
        gr_summary = work.get_rating_summary("Goodreads")
        db_summary = work.get_rating_summary("Douban")
        writer.writerow([work.title, work.author, work.work_id, ol_summary, gb_summary, gr_summary, db_summary])

    return output.getvalue()


def format_json(works: List[Work]) -> str:
    """Format works list as JSON string."""
    data = []
    for work in works:
        data.append({
            "work_id": work.work_id,
            "title": work.title,
            "author": work.author,
            "ratings": {
                name: {
                    "rate": r.rate,
                    "rating_count": r.rating_count,
                    "url": r.url
                } for name, r in work.ratings.items()
            },
            "editions_count": len(work.editions),
            "editions": [
                {
                    "edition_id": ed.edition_id,
                    "title": ed.title,
                    "publish_year": ed.publish_year,
                    "language": ed.language,
                    "isbn_13": ed.isbn_13,
                    "isbn_10": ed.isbn_10,
                    "publisher": ed.publisher
                } for ed in work.editions
            ]
        })
    return json.dumps(data, ensure_ascii=False, indent=2)
