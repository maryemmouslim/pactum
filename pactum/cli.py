import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="pactum")
    subparsers = parser.add_subparsers(dest="command", required=True)

    eval_parser = subparsers.add_parser(
        "eval", help="Run the Causal Explanation Agent against injected-incident scenarios"
    )
    eval_parser.add_argument(
        "--scenarios",
        required=True,
        help="Directory of scenario subdirectories (each with setup.py, inject.py, expected.yaml)",
    )

    eval_contracts_parser = subparsers.add_parser(
        "eval-contracts",
        help="Compare the Contract Generator Agent's drafts against hand-written gold contracts",
    )
    eval_contracts_parser.add_argument(
        "--gold",
        required=True,
        help="Directory of gold contract YAML files (searched recursively)",
    )

    human_benchmark_parser = subparsers.add_parser(
        "eval-human-benchmark",
        help="Compare the Causal Explanation Agent's accuracy against a recorded human "
        "baseline on the same injected-incident scenarios",
    )
    human_benchmark_parser.add_argument(
        "--scenarios",
        default="evals/injected_incidents",
        help="Directory of scenario subdirectories (each with setup.py, inject.py, expected.yaml)",
    )
    human_benchmark_parser.add_argument(
        "--hypotheses",
        default="evals/human_benchmark/human_hypotheses.yaml",
        help="YAML file mapping scenario name -> recorded human hypothesis",
    )

    subparsers.add_parser(
        "mcp",
        help="Run Pactum's MCP server (stdio) -- exposes read-only contract/incident/"
        "explanation lookups plus run_checks to any MCP-compatible AI client",
    )

    args = parser.parse_args()

    if args.command == "eval":
        from pactum.eval.runner import run_eval

        run_eval(args.scenarios)
    elif args.command == "eval-contracts":
        from pactum.eval.contract_runner import run_gold_contracts

        run_gold_contracts(args.gold)
    elif args.command == "eval-human-benchmark":
        from pactum.eval.human_benchmark import run_human_benchmark

        run_human_benchmark(args.scenarios, args.hypotheses)
    elif args.command == "mcp":
        from pactum.mcp.server import main as run_mcp_server

        run_mcp_server()
