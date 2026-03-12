"""CLI entry point: python -m complexity_accounting"""

import sys
import argparse
import json

from .scanner import scan_file, scan_directory, ScanResult


def cmd_scan(args):
    """Run the scanner."""
    from .scanner import main as scanner_main
    # Re-use scanner's main with sys.argv manipulation
    sys.argv = ["complexity-scan", args.path]
    if args.json:
        sys.argv.append("--json")
    if args.threshold:
        sys.argv.extend(["--threshold", str(args.threshold)])
    if args.top:
        sys.argv.extend(["--top", str(args.top)])
    if args.fail_above is not None:
        sys.argv.extend(["--fail-above", str(args.fail_above)])
    scanner_main()


def cmd_compare(args):
    """Compare complexity between git refs."""
    from .git_tracker import compare_refs
    
    report = compare_refs(
        base_ref=args.base,
        head_ref=args.head,
        repo_path=args.repo,
        changed_only=not args.full,
    )
    
    if args.json:
        print(report.to_json())
    elif args.markdown:
        print(report.to_markdown())
    else:
        print(report.to_markdown())


def cmd_trend(args):
    """Show complexity trend over recent commits."""
    from .git_tracker import trend
    
    results = trend(
        repo_path=args.repo,
        num_commits=args.commits,
        ref=args.ref,
    )
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"\n{'Commit':>10}  {'NCS':>6}  {'Cog':>6}  {'Funcs':>6}  {'Message'}")
        print(f"{'─' * 10}  {'─' * 6}  {'─' * 6}  {'─' * 6}  {'─' * 40}")
        for r in results:
            if "error" in r:
                print(f"{r['commit']:>10}  {'err':>6}  {'':>6}  {'':>6}  {r.get('message', '')}")
            else:
                print(f"{r['commit']:>10}  {r['ncs']:>6.1f}  {r['total_cognitive']:>6}  {r['total_functions']:>6}  {r.get('message', '')}")
        print()


def main():
    parser = argparse.ArgumentParser(
        prog="complexity-accounting",
        description="Complexity Accounting Tool — measure and track Net Complexity Score",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # scan
    scan_p = subparsers.add_parser("scan", help="Scan files or directories")
    scan_p.add_argument("path", help="File or directory to scan")
    scan_p.add_argument("--json", action="store_true")
    scan_p.add_argument("--threshold", type=int, default=10)
    scan_p.add_argument("--top", type=int, default=20)
    scan_p.add_argument("--fail-above", type=float, default=None)
    scan_p.set_defaults(func=cmd_scan)
    
    # compare
    cmp_p = subparsers.add_parser("compare", help="Compare complexity between git refs")
    cmp_p.add_argument("--base", required=True, help="Base ref (e.g. main, HEAD~1)")
    cmp_p.add_argument("--head", default="HEAD", help="Head ref (default: HEAD)")
    cmp_p.add_argument("--repo", default=".", help="Path to git repo")
    cmp_p.add_argument("--json", action="store_true")
    cmp_p.add_argument("--markdown", action="store_true")
    cmp_p.add_argument("--full", action="store_true", help="Scan all files, not just changed")
    cmp_p.set_defaults(func=cmd_compare)
    
    # trend
    trend_p = subparsers.add_parser("trend", help="Show complexity trend over commits")
    trend_p.add_argument("--repo", default=".", help="Path to git repo")
    trend_p.add_argument("--commits", type=int, default=10, help="Number of commits")
    trend_p.add_argument("--ref", default="HEAD", help="Starting ref")
    trend_p.add_argument("--json", action="store_true")
    trend_p.set_defaults(func=cmd_trend)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
