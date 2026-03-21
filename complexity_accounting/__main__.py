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


def _get_format(args) -> str:
    """Resolve output format from --format and --json flags."""
    fmt = getattr(args, "format", None)
    if fmt:
        return fmt
    if getattr(args, "json", False):
        return "json"
    return "text"


def _ncs_rating(ncs: float) -> str:
    """Return a human-readable NCS rating string."""
    if ncs <= 3:
        return "🟢 Healthy"
    elif ncs <= 6:
        return "🟡 Moderate"
    elif ncs <= 10:
        return "🟠 Concerning"
    else:
        return "🔴 Critical"


def _build_config(args, target):
    """Load config and apply CLI overrides."""
    from pathlib import Path

    project_dir = str(target) if target.is_dir() else str(target.parent)
    if args.config:
        project_dir = str(Path(args.config).parent)
    config = load_config(project_dir)

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
    return merge_cli_overrides(config, **overrides)


def _setup_cache(args, target):
    """Initialize content-hash caching if enabled."""
    if not getattr(args, "no_cache", False):
        try:
            from .cache import MetricsCache
            from .scanner import set_cache
            cache_dir = os.path.join(
                str(target) if target.is_dir() else str(target.parent),
                ".complexity-cache"
            )
            set_cache(MetricsCache(cache_dir=cache_dir))
        except Exception:
            pass


def _compute_factors(args, target, config):
    """Compute churn and coupling factors. Returns (churn_factor, coupling_factor)."""
    churn_factor = 1.0
    coupling_factor = 1.0

    if not args.no_coupling:
        try:
            from .coupling import analyze_directory_coupling, compute_coupling_factor
            coupling_data = analyze_directory_coupling(str(target), include_tests=config.include_tests)
            coupling_factor = compute_coupling_factor(coupling_data)
        except Exception:
            pass

    if not args.no_churn:
        try:
            from .churn import analyze_churn, compute_churn_factor
            churn_data = analyze_churn(
                str(target), days=config.churn_days, max_commits=config.churn_commits
            )
            churn_factor = compute_churn_factor(churn_data)
        except Exception:
            pass

    return churn_factor, coupling_factor


def _format_text_report(result, ncs, config, explanation, args, out):
    """Print human-readable text report."""
    print("=" * 60, file=out)
    print("  COMPLEXITY ACCOUNTING REPORT", file=out)
    print("=" * 60, file=out)
    print(file=out)

    s = result.to_dict()["summary"]
    print(f"  Net Complexity Score:  {ncs}  {_ncs_rating(ncs)}", file=out)
    print(f"  Files scanned:        {s['files_scanned']}", file=out)
    print(f"  Total functions:      {s['total_functions']}", file=out)
    print(f"  Avg cognitive/func:   {s['avg_cognitive_per_function']}", file=out)
    print(f"  Hotspots (>={config.hotspot_threshold}):     {s['hotspot_count']}", file=out)
    if config.ncs_model != "multiplicative":
        print(f"  NCS model:            {config.ncs_model}", file=out)
    churn_factor = explanation['churn_factor'] if explanation else 1.0
    coupling_factor = explanation['coupling_factor'] if explanation else 1.0
    if churn_factor != 1.0:
        print(f"  Churn factor:         {churn_factor:.3f}", file=out)
    if coupling_factor != 1.0:
        print(f"  Coupling factor:      {coupling_factor:.3f}", file=out)
    print(f"  Avg MI:               {s['avg_maintainability_index']}", file=out)
    print(file=out)

    if explanation is not None:
        _print_ncs_breakdown(explanation, config, out)

    _print_top_functions(result, config, args.top, out)
    _print_top_classes(result, out)

    print("=" * 60, file=out)


def _print_ncs_breakdown(explanation, config, out):
    """Print the NCS factor breakdown section."""
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


def _print_top_functions(result, config, top_n, out):
    """Print the top complex functions table."""
    all_funcs = [fn for fm in result.files for fn in fm.functions]
    all_funcs.sort(key=lambda f: f.cognitive_complexity, reverse=True)
    top = all_funcs[:top_n]

    if not top:
        return

    risk_icons = {"low": "  ", "moderate": "⚠️", "high": "🔥", "very_high": "💀"}
    print(f"  Top {min(len(top), top_n)} most complex functions:", file=out)
    print(f"  {'─' * 56}", file=out)
    for fn in top:
        lang = get_language(fn.file_path)
        low, mod, high = config.get_risk_levels(lang)
        icon = risk_icons.get(fn.get_risk_level(low, mod, high), "  ")
        short_path = fn.file_path
        if len(short_path) > 30:
            short_path = "..." + short_path[-27:]
        print(
            f"  {icon} {fn.cognitive_complexity:3d}  {fn.qualified_name:30s}  {short_path}:{fn.line}",
            file=out,
        )
    print(file=out)


def _print_top_classes(result, out):
    """Print the top complex classes table."""
    all_classes = [cls for fm in result.files for cls in fm.classes]
    if not all_classes:
        return

    all_classes.sort(key=lambda c: c.total_cognitive, reverse=True)
    top_classes = all_classes[:10]
    print(f"  Top {len(top_classes)} most complex classes:", file=out)
    print(f"  {'─' * 56}", file=out)
    for cls in top_classes:
        short_path = cls.file_path
        if len(short_path) > 30:
            short_path = "..." + short_path[-27:]
        print(
            f"    {cls.total_cognitive:3d} cog  {cls.wmc:3d} wmc  {cls.method_count:2d} methods  {cls.name:20s}  {short_path}:{cls.line}",
            file=out,
        )
    print(file=out)


def cmd_scan(args):
    """Run the scanner."""
    from pathlib import Path

    target = Path(args.path)
    config = _build_config(args, target)
    _setup_cache(args, target)

    # Scan
    if target.is_file():
        result = ScanResult(files=[scan_file(str(target))])
    elif target.is_dir():
        workers = getattr(args, "workers", None)
        result = scan_directory(str(target), include_tests=config.include_tests, workers=workers)
    else:
        print(f"Error: {target} not found", file=sys.stderr)
        sys.exit(1)

    # Clean up cache
    from .scanner import set_cache
    set_cache(None)

    churn_factor, coupling_factor = _compute_factors(args, target, config)
    ncs = result.compute_ncs(config, churn_factor=churn_factor, coupling_factor=coupling_factor)

    explanation = None
    if not args.brief:
        explanation = result.compute_ncs_explained(
            config, churn_factor=churn_factor, coupling_factor=coupling_factor
        )

    output_format = _get_format(args)

    with _output_stream(args) as out:
        if output_format == "json":
            data = result.to_dict()
            data["summary"]["net_complexity_score"] = ncs
            data["summary"]["churn_factor"] = round(churn_factor, 4)
            data["summary"]["coupling_factor"] = round(coupling_factor, 4)
            data["summary"]["ncs_model"] = config.ncs_model
            if explanation is not None:
                data["explanation"] = explanation
            print(json.dumps(data, indent=2), file=out)

        elif output_format == "html":
            from .html_report import generate_html_report
            data = result.to_dict()
            data["summary"]["net_complexity_score"] = ncs
            data["summary"]["churn_factor"] = round(churn_factor, 4)
            data["summary"]["coupling_factor"] = round(coupling_factor, 4)
            html = generate_html_report(
                data, ncs, config=config, explanation=explanation, top_n=args.top
            )
            print(html, file=out)

        elif output_format == "sarif":
            from .sarif import generate_sarif, sarif_to_json
            data = result.to_dict()
            sarif = generate_sarif(data, config=config)
            print(sarif_to_json(sarif), file=out)

        else:
            _format_text_report(result, ncs, config, explanation, args, out)

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


def cmd_list_plugins(args):
    """List discovered language plugins."""
    from .plugin import list_plugins

    plugins = list_plugins()
    if not plugins:
        print("No language plugins found.")
        print()
        print("Built-in languages: Python, Go, Java, JavaScript, TypeScript, Rust, C/C++")
        print()
        print("To create a plugin, implement the LanguagePlugin protocol and register")
        print("it as an entry point under 'complexity_accounting.languages'.")
    else:
        print(f"{'Name':20s}  {'Extensions'}")
        print(f"{'─' * 20}  {'─' * 30}")
        for p in plugins:
            print(f"{p['name']:20s}  {p['extensions']}")


def main():
    parser = argparse.ArgumentParser(
        prog="complexity-accounting",
        description="Complexity Accounting Tool — measure and track Net Complexity Score",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # scan
    scan_p = subparsers.add_parser("scan", help="Scan files or directories")
    scan_p.add_argument("path", help="File or directory to scan")
    scan_p.add_argument("--json", action="store_true", help="Output as JSON (shorthand for --format json)")
    scan_p.add_argument(
        "--format",
        choices=["text", "json", "html", "sarif"],
        default=None,
        help="Output format (default: text)",
    )
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
        "--no-cache", action="store_true", help="Disable content-hash caching"
    )
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
        "--workers", type=int, default=None,
        help="Number of parallel workers for scanning (default: auto, 1 = sequential)",
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

    # list-plugins
    plugins_p = subparsers.add_parser("list-plugins", help="List discovered language plugins")
    plugins_p.set_defaults(func=cmd_list_plugins)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
