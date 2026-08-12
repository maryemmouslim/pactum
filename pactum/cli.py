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

    args = parser.parse_args()

    if args.command == "eval":
        from pactum.eval.runner import run_eval

        run_eval(args.scenarios)
    elif args.command == "eval-contracts":
        from pactum.eval.contract_runner import run_gold_contracts

        run_gold_contracts(args.gold)
