"""CLI entry point: python -m complexity_accounting"""

import sys
import argparse
import json
import os
from contextlib import contextmanager

from .scanner import scan_file, scan_directory, ScanResult, get_language
from .config import Config, load_config, merge_cli_overrides


@contextmanager
def _output_stream(args):
    """Yield a writable stream: file if --output is set, else stdout."""
    output_path = getattr(args, "output", None)
    if output_path:
        fh = open(output_path, "w", encoding="utf-8")
        try:
            yield fh
        finally:
            fh.close()
    else:
        yield sys.stdout


def cmd_scan(args):
    """Run the scanner."""
    from pathlib import Path

    target = Path(args.path)

    # Load config
    project_dir = str(target) if target.is_dir() else str(target.parent)
    if args.config:
        project_dir = str(Path(args.config).parent)
    config = load_config(project_dir)

    # CLI overrides
    overrides = {}
    if args.threshold is not None:
        overrides["hotspot_threshold"] = args.threshold
    if args.weights:
        for pair in args.weights.split(","):
            k, v = pair.strip().split("=")
            if k.strip() == "cognitive":
                overrides["weight_cognitive"] = float(v)
            elif k.strip() == "cyclomatic":
                overrides["weight_cyclomatic"] = float(v)
    if args.churn_days is not None:
        overrides["churn_days"] = args.churn_days
    if args.churn_commits is not None:
        overrides["churn_commits"] = args.churn_commits
    if args.ncs_model is not None:
        overrides["ncs_model"] = args.ncs_model
    if getattr(args, "include_tests", False):
        overrides["include_tests"] = True
    config = merge_cli_overrides(config, **overrides)

    # Scan
    if target.is_file():
        result = ScanResult(files=[scan_file(str(target))])
    elif target.is_dir():
        result = scan_directory(str(target), include_tests=config.include_tests)
    else:
        print(f"Error: {target} not found", file=sys.stderr)
        sys.exit(1)

    # Compute coupling and churn factors
    churn_factor = 1.0
    coupling_factor = 1.0

    if not args.no_coupling:
        try:
            from .coupling import analyze_directory_coupling, compute_coupling_factor
            coupling_data = analyze_directory_coupling(str(target), include_tests=config.include_tests)
            coupling_factor = compute_coupling_factor(coupling_data)
        except Exception:
            pass  # graceful degradation

    if not args.no_churn:
        try:
            from .churn import analyze_churn, compute_churn_factor
            churn_data = analyze_churn(
                str(target), days=config.churn_days, max_commits=config.churn_commits
            )
            churn_factor = compute_churn_factor(churn_data)
        except Exception:
            pass  # graceful degradation (e.g. not a git repo)

    ncs = result.compute_ncs(config, churn_factor=churn_factor, coupling_factor=coupling_factor)

    # Compute explanation by default (suppress with --brief)
    explanation = None
    if not args.brief:
        explanation = result.compute_ncs_explained(
            config, churn_factor=churn_factor, coupling_factor=coupling_factor
        )

    with _output_stream(args) as out:
        if args.json:
            data = result.to_dict()
            data["summary"]["net_complexity_score"] = ncs
            data["summary"]["churn_factor"] = round(churn_factor, 4)
            data["summary"]["coupling_factor"] = round(coupling_factor, 4)
            data["summary"]["ncs_model"] = config.ncs_model
            if explanation is not None:
                data["explanation"] = explanation
            print(json.dumps(data, indent=2), file=out)
        else:
            # Human-readable summary
            print("=" * 60, file=out)
            print("  COMPLEXITY ACCOUNTING REPORT", file=out)
            print("=" * 60, file=out)
            print(file=out)

            s = result.to_dict()["summary"]

            # NCS rating
            if ncs <= 3:
                rating = "🟢 Healthy"
            elif ncs <= 6:
                rating = "🟡 Moderate"
            elif ncs <= 10:
                rating = "🟠 Concerning"
            else:
                rating = "🔴 Critical"

            print(f"  Net Complexity Score:  {ncs}  {rating}", file=out)
            print(f"  Files scanned:        {s['files_scanned']}", file=out)
            print(f"  Total functions:      {s['total_functions']}", file=out)
            print(f"  Avg cognitive/func:   {s['avg_cognitive_per_function']}", file=out)
            print(f"  Hotspots (>={config.hotspot_threshold}):     {s['hotspot_count']}", file=out)
            if config.ncs_model != "multiplicative":
                print(f"  NCS model:            {config.ncs_model}", file=out)
            if churn_factor != 1.0:
                print(f"  Churn factor:         {churn_factor:.3f}", file=out)
            if coupling_factor != 1.0:
                print(f"  Coupling factor:      {coupling_factor:.3f}", file=out)
            print(f"  Avg MI:               {s['avg_maintainability_index']}", file=out)
            print(file=out)

            # Explain breakdown
            if explanation is not None:
                print(f"  NCS Breakdown ({explanation['model']}):", file=out)
                print(f"  {'─' * 56}", file=out)
                print(
                    f"    Base complexity:    {explanation['base_complexity']:7.2f}"
                    f"  ({config.weight_cognitive} * {explanation['avg_cognitive']:.2f} cog"
                    f" + {config.weight_cyclomatic} * {explanation['avg_cyclomatic']:.2f} cyc)",
                    file=out,
                )
                print(
                    f"    Hotspot effect:    {explanation['hotspot_contribution']:+7.2f}"
                    f"  (ratio={explanation['hotspot_ratio']:.2f})",
                    file=out,
                )
                print(
                    f"    Churn effect:      {explanation['churn_contribution']:+7.2f}"
                    f"  (factor={explanation['churn_factor']:.3f})",
                    file=out,
                )
                print(
                    f"    Coupling effect:   {explanation['coupling_contribution']:+7.2f}"
                    f"  (factor={explanation['coupling_factor']:.3f})",
                    file=out,
                )
                print(
                    f"    MI effect:         {explanation['mi_contribution']:+7.2f}"
                    f"  (avg_mi={explanation['avg_maintainability_index']:.1f})",
                    file=out,
                )
                print(f"    Final NCS:         {explanation['ncs']:7.2f}", file=out)
                if explanation['dominant_factor'] != "none":
                    print(f"    Dominant factor:    {explanation['dominant_factor']}", file=out)
                print(file=out)

            # Top complex functions
            all_funcs = []
            for fm in result.files:
                for fn in fm.functions:
                    all_funcs.append(fn)

            all_funcs.sort(key=lambda f: f.cognitive_complexity, reverse=True)
            top = all_funcs[: args.top]

            if top:
                print(f"  Top {min(len(top), args.top)} most complex functions:", file=out)
                print(f"  {'─' * 56}", file=out)
                for fn in top:
                    risk = {"low": "  ", "moderate": "⚠️", "high": "🔥", "very_high": "💀"}
                    lang = get_language(fn.file_path)
                    low, mod, high = config.get_risk_levels(lang)
                    icon = risk.get(fn.get_risk_level(low, mod, high), "  ")
                    # Shorten path for display
                    short_path = fn.file_path
                    if len(short_path) > 30:
                        short_path = "..." + short_path[-27:]
                    print(
                        f"  {icon} {fn.cognitive_complexity:3d}  {fn.qualified_name:30s}  {short_path}:{fn.line}",
                        file=out,
                    )
                print(file=out)

            print("=" * 60, file=out)

    # CI gate
    if args.fail_above is not None and ncs > args.fail_above:
        print(f"\n❌ FAILED: NCS {ncs} exceeds threshold {args.fail_above}", file=sys.stderr)
        sys.exit(1)


def cmd_compare(args):
    """Compare complexity between git refs."""
    from .git_tracker import compare_refs

    report = compare_refs(
        base_ref=args.base,
        head_ref=args.head,
        repo_path=args.repo,
        changed_only=not args.full,
        include_tests=getattr(args, "include_tests", False),
    )

    with _output_stream(args) as out:
        if args.json:
            print(report.to_json(), file=out)
        elif args.markdown:
            print(report.to_markdown(), file=out)
        else:
            print(report.to_markdown(), file=out)


def cmd_trend(args):
    """Show complexity trend over recent commits."""
    from .git_tracker import trend

    results = trend(
        repo_path=args.repo,
        num_commits=args.commits,
        ref=args.ref,
        include_tests=getattr(args, "include_tests", False),
    )

    with _output_stream(args) as out:
        if args.json:
            print(json.dumps(results, indent=2), file=out)
        else:
            print(f"\n{'Commit':>10}  {'NCS':>6}  {'Cog':>6}  {'Funcs':>6}  {'Message'}", file=out)
            print(f"{'─' * 10}  {'─' * 6}  {'─' * 6}  {'─' * 6}  {'─' * 40}", file=out)
            for r in results:
                if "error" in r:
                    print(f"{r['commit']:>10}  {'err':>6}  {'':>6}  {'':>6}  {r.get('message', '')}", file=out)
                else:
                    print(
                        f"{r['commit']:>10}  {r['ncs']:>6.1f}  {r['total_cognitive']:>6}  {r['total_functions']:>6}  {r.get('message', '')}",
                        file=out,
                    )
            print(file=out)


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
    scan_p.add_argument("--threshold", type=int, default=None)
    scan_p.add_argument("--top", type=int, default=20)
    scan_p.add_argument("--fail-above", type=float, default=None)
    scan_p.add_argument("--config", default=None, help="Path to config file")
    scan_p.add_argument(
        "--weights",
        default=None,
        help="NCS weights as key=value pairs (e.g. cognitive=0.7,cyclomatic=0.3)",
    )
    scan_p.add_argument("--churn-days", type=int, default=None)
    scan_p.add_argument("--churn-commits", type=int, default=None)
    scan_p.add_argument("--no-churn", action="store_true", help="Disable churn factor")
    scan_p.add_argument("--no-coupling", action="store_true", help="Disable coupling factor")
    scan_p.add_argument(
        "--ncs-model",
        choices=["multiplicative", "additive"],
        default=None,
        help="NCS formula: multiplicative (default) or additive",
    )
    scan_p.add_argument(
        "--brief", action="store_true", help="Hide NCS factor breakdown (shown by default)"
    )
    scan_p.add_argument(
        "--include-tests", action="store_true",
        help="Include test files in complexity scoring (excluded by default)",
    )
    scan_p.add_argument(
        "--output", "-o", default=None,
        help="Write output to FILE instead of stdout",
        metavar="FILE",
    )
    scan_p.set_defaults(func=cmd_scan)

    # compare
    cmp_p = subparsers.add_parser("compare", help="Compare complexity between git refs")
    cmp_p.add_argument("--base", required=True, help="Base ref (e.g. main, HEAD~1)")
    cmp_p.add_argument("--head", default="HEAD", help="Head ref (default: HEAD)")
    cmp_p.add_argument("--repo", default=".", help="Path to git repo")
    cmp_p.add_argument("--json", action="store_true")
    cmp_p.add_argument("--markdown", action="store_true")
    cmp_p.add_argument("--full", action="store_true", help="Scan all files, not just changed")
    cmp_p.add_argument(
        "--include-tests", action="store_true",
        help="Include test files in complexity scoring (excluded by default)",
    )
    cmp_p.add_argument(
        "--output", "-o", default=None,
        help="Write output to FILE instead of stdout",
        metavar="FILE",
    )
    cmp_p.set_defaults(func=cmd_compare)

    # trend
    trend_p = subparsers.add_parser("trend", help="Show complexity trend over commits")
    trend_p.add_argument("--repo", default=".", help="Path to git repo")
    trend_p.add_argument("--commits", type=int, default=10, help="Number of commits")
    trend_p.add_argument("--ref", default="HEAD", help="Starting ref")
    trend_p.add_argument("--json", action="store_true")
    trend_p.add_argument(
        "--include-tests", action="store_true",
        help="Include test files in complexity scoring (excluded by default)",
    )
    trend_p.add_argument(
        "--output", "-o", default=None,
        help="Write output to FILE instead of stdout",
        metavar="FILE",
    )
    trend_p.set_defaults(func=cmd_trend)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
