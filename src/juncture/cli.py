"""Command-line interface for Juncture."""

from __future__ import annotations

import argparse
from pathlib import Path

from .campaign import create_run, execute_run, planned_task_count, run_status
from .config import load_config


def _run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    count = planned_task_count(config)
    print(f"planned_tasks: {count}")
    if count > args.large_run_limit and not args.confirm_large_run:
        raise ValueError(
            f"planned task count {count} exceeds {args.large_run_limit}; use --confirm-large-run"
        )
    run_dir = create_run(config, Path.cwd())
    execute_run(run_dir, workers=args.workers)
    print(run_dir)
    return 0


def _resume(args: argparse.Namespace) -> int:
    execute_run(Path(args.run_dir), workers=args.workers)
    return 0


def _status(args: argparse.Namespace) -> int:
    for name, count in run_status(Path(args.run_dir)).items():
        print(f"{name}: {count}")
    return 0


def _validate(_: argparse.Namespace) -> int:
    from .simulator import simulate_exact
    from .theory import effective_throughput, stationary_loss_probability
    from .workload import generate_workload

    for rho in (0.5, 0.8, 0.95, 1.0, 1.1):
        workload = generate_workload(
            arrival_rate=rho,
            service_rate=1.0,
            warmup_arrivals=2_000,
            measured_arrivals=20_000,
            seed=20260727 + int(rho * 100),
        )
        result = simulate_exact(workload, capacity=8)
        theoretical_loss = stationary_loss_probability(rho, 8)
        theoretical_throughput = effective_throughput(rho, rho, 8)
        print(
            f"rho={rho}: simulated_loss={result['packet_loss_probability']:.8g} "
            f"theoretical_loss={theoretical_loss:.8g} "
            f"simulated_throughput={result['throughput']:.8g} "
            f"theoretical_throughput={theoretical_throughput:.8g}"
        )
    return 0


def _analyze(args: argparse.Namespace) -> int:
    from .analysis_v2 import analyze_run_v2

    created = analyze_run_v2(Path(args.run_dir), Path(args.analysis_config) if args.analysis_config else None)
    print(created)
    return 0


def _verify_run(args: argparse.Namespace) -> int:
    import json

    from .verification import verify_run

    outcome = verify_run(Path(args.run_dir))
    print(json.dumps(outcome, indent=2, sort_keys=True))
    return 0 if outcome["ok"] else 1


def _compare_baseline(args: argparse.Namespace) -> int:
    import json

    from .verification import compare_baseline

    print(json.dumps(compare_baseline(Path(args.left_run_dir), Path(args.right_run_dir)), indent=2))
    return 0


def _paper_assets(args: argparse.Namespace) -> int:
    from .publication import build_assets

    build_assets(Path(args.analysis_dir))
    print(Path(args.analysis_dir))
    return 0


def _report_assets(args: argparse.Namespace) -> int:
    from .publication import refresh_report_assets

    refresh_report_assets(Path(args.analysis_dir))
    print(Path(args.analysis_dir))
    return 0


def _phase22_analyze(args: argparse.Namespace) -> int:
    from .phase22 import analyze_phase22

    created = analyze_phase22(
        Path(args.run_dir), Path(args.baseline_analysis), Path(args.focused_run) if args.focused_run else None
    )
    print(created)
    return 0


def _phase22_report(args: argparse.Namespace) -> int:
    from .phase22 import refresh_phase22_report

    refresh_phase22_report(Path(args.analysis_dir))
    print(Path(args.analysis_dir))
    return 0


def _phase221_publish(args: argparse.Namespace) -> int:
    from .phase221 import build_phase221

    print(build_phase221(Path(args.source_analysis)))
    return 0


def _phase221_validate(args: argparse.Namespace) -> int:
    from .phase221 import validate_phase221

    validate_phase221(Path(args.publication_dir))
    print(Path(args.publication_dir))
    return 0


def _compare_runs(args: argparse.Namespace) -> int:
    from .verification import compare_runs

    created = compare_runs([Path(value) for value in args.analysis_dir], Path(args.output_dir) if args.output_dir else None)
    print(created)
    return 0


def _plot(args: argparse.Namespace) -> int:
    from .plots import plot_run

    plot_run(Path(args.run_dir), args.language)
    return 0


def _tables(args: argparse.Namespace) -> int:
    from .tables import build_tables

    build_tables(Path(args.run_dir))
    return 0


def _report(args: argparse.Namespace) -> int:
    from .report import build_report

    build_report(Path(args.run_dir))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="juncture")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--config", required=True)
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--large-run-limit", type=int, default=100_000)
    run.add_argument("--confirm-large-run", action="store_true")
    run.set_defaults(func=_run)
    resume = commands.add_parser("resume")
    resume.add_argument("--run-dir", required=True)
    resume.add_argument("--workers", type=int, default=1)
    resume.set_defaults(func=_resume)
    status = commands.add_parser("status")
    status.add_argument("--run-dir", required=True)
    status.set_defaults(func=_status)
    analyze = commands.add_parser("analyze")
    analyze.add_argument("--run-dir", required=True)
    analyze.add_argument("--analysis-config")
    analyze.set_defaults(func=_analyze)
    verify = commands.add_parser("verify-run")
    verify.add_argument("--run-dir", required=True)
    verify.set_defaults(func=_verify_run)
    baseline = commands.add_parser("compare-baseline")
    baseline.add_argument("--left-run-dir", required=True)
    baseline.add_argument("--right-run-dir", required=True)
    baseline.set_defaults(func=_compare_baseline)
    assets = commands.add_parser("paper-assets")
    assets.add_argument("--analysis-dir", required=True)
    assets.set_defaults(func=_paper_assets)
    report_assets = commands.add_parser("report-assets")
    report_assets.add_argument("--analysis-dir", required=True)
    report_assets.set_defaults(func=_report_assets)
    phase22 = commands.add_parser("phase22-analyze")
    phase22.add_argument("--run-dir", required=True)
    phase22.add_argument("--baseline-analysis", required=True)
    phase22.add_argument("--focused-run")
    phase22.set_defaults(func=_phase22_analyze)
    phase22_report = commands.add_parser("phase22-report")
    phase22_report.add_argument("--analysis-dir", required=True)
    phase22_report.set_defaults(func=_phase22_report)
    phase221 = commands.add_parser("phase221-publish")
    phase221.add_argument("--source-analysis", required=True)
    phase221.set_defaults(func=_phase221_publish)
    phase221_validate = commands.add_parser("phase221-validate")
    phase221_validate.add_argument("--publication-dir", required=True)
    phase221_validate.set_defaults(func=_phase221_validate)
    compare = commands.add_parser("compare-runs")
    compare.add_argument("--analysis-dir", action="append", required=True)
    compare.add_argument("--output-dir")
    compare.set_defaults(func=_compare_runs)
    plot = commands.add_parser("plot")
    plot.add_argument("--run-dir", required=True)
    plot.add_argument("--language", choices=["en", "ru"], default="en")
    plot.set_defaults(func=_plot)
    tables = commands.add_parser("tables")
    tables.add_argument("--run-dir", required=True)
    tables.set_defaults(func=_tables)
    report = commands.add_parser("report")
    report.add_argument("--run-dir", required=True)
    report.set_defaults(func=_report)
    validate = commands.add_parser("validate")
    validate.set_defaults(func=_validate)
    trace = commands.add_parser("inspect-trace")
    trace.add_argument("--trace", required=True)
    trace.set_defaults(func=lambda a: print(Path(a.trace).read_text(encoding="utf-8")) or 0)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
