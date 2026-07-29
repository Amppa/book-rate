import argparse
import sys
import os
from rich.console import Console

from book_rate.aggregator import BookAggregator
from book_rate.formatters import format_markdown_table, print_rich_table, format_csv, format_json


def main():
    parser = argparse.ArgumentParser(
        description="BookRate Aggregator (MVP) - Query books by Chinese title, map works & editions, aggregate ratings from Open Library, Google Books, Goodreads, and Douban."
    )
    parser.add_argument(
        "query",
        type=str,
        nargs="?",
        help="Book title to search for (e.g. '快思慢想', '原子習慣')"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["table", "markdown", "json", "csv"],
        default="table",
        help="Output format: 'table' (rich terminal + markdown), 'markdown', 'json', or 'csv'."
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=5,
        help="Maximum number of work items to search and output (default: 5)."
    )
    parser.add_argument(
        "--google-key",
        type=str,
        default=None,
        help="Google Books API key (optional, can also be set via GOOGLE_BOOKS_API_KEY environment variable)."
    )
    parser.add_argument(
        "--editions",
        action="store_true",
        help="Display detailed edition lists under each work."
    )

    args = parser.parse_args()
    console = Console()

    query = args.query
    if not query:
        # Interactive prompt if no positional query passed
        console.print("[bold yellow]請輸入書名 (Enter Book Title):[/bold yellow] ", end="")
        query = input().strip()
        if not query:
            console.print("[red]錯誤: 未提供搜尋書名。[/red]")
            sys.exit(1)

    console.print(f"\n[bold green]🔍 正在搜尋書名:[/bold green] [cyan]{query}[/cyan] ...")

    google_key = args.google_key or os.environ.get("GOOGLE_BOOKS_API_KEY")
    aggregator = BookAggregator(google_api_key=google_key)

    works = aggregator.aggregate_by_title(query, limit=args.limit)

    if not works:
        console.print(f"[bold red]❌ 未找到與 '{query}' 相關的圖書或版本。[/bold red]")
        sys.exit(0)

    console.print(f"[bold green]✅ 找到 {len(works)} 個對應作品 (Works)：[/bold green]\n")

    if args.format == "markdown":
        print(format_markdown_table(works))
    elif args.format == "csv":
        print(format_csv(works))
    elif args.format == "json":
        print(format_json(works))
    else:  # "table" format (Rich terminal table followed by Markdown output)
        print_rich_table(works, console=console)
        console.print("\n[bold dim]--- Markdown 格式輸出 ---[/bold dim]\n")
        print(format_markdown_table(works))

    # Show edition breakdown if requested
    if args.editions:
        console.print("\n[bold cyan]📖 版本明細 (Editions Detail):[/bold cyan]")
        for idx, work in enumerate(works, start=1):
            console.print(f"\n[bold white]{idx}. {work.title}[/bold white] ({work.work_id})")
            if not work.editions:
                console.print("   [dim]無詳細版本紀錄[/dim]")
            for ed in work.editions:
                year = f" ({ed.publish_year})" if ed.publish_year else ""
                lang = f" [{ed.language}]" if ed.language else ""
                isbn = f" ISBN: {ed.isbn_13 or ed.isbn_10}" if (ed.isbn_13 or ed.isbn_10) else ""
                console.print(f"   • {ed.title}{year}{lang}{isbn}")


if __name__ == "__main__":
    main()
