"""Command line: generate a population of proposals, then evaluate it.

    ideataste generate --method topic --model deepseek-v4-flash --area world_models --n 300 --out runs/x
    ideataste evaluate --area world_models --proposals runs/x/proposals.jsonl --out runs/x/eval
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from ideataste.catalog import AREAS, METHODS, models_with_role


def generate(args):
    from ideataste.agent.episode import Settings
    from ideataste.llm import make_client
    from ideataste.population import run_population

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    client = make_client(args.model, log_path=out / "llm_calls.jsonl")
    (out / "run.json").write_text(json.dumps(vars(args), indent=2, default=str) + "\n")
    run_population(args.method, args.area, args.n, out, client, settings=Settings(step_budget=args.steps), concurrency=args.concurrency)


def evaluate(args):
    from ideataste.evaluation.pipeline import evaluate_population
    from ideataste.jsonl import JsonlLog
    from ideataste.llm import make_client

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    proposals = [{"proposal_id": r["agent_id"], "title": r["proposal"]["title"], "abstract": r["proposal"]["abstract"], "citations": r["citations"]} for r in JsonlLog(args.proposals).read() if not r["failed"]]
    scores = evaluate_population(args.area, proposals, out, extractor=make_client(args.extractor, log_path=out / "extractor_calls.jsonl"), judge=make_client(args.judge, log_path=out / "judge_calls.jsonl"), concurrency=args.concurrency)
    print(json.dumps(scores, indent=2))


def main(argv=None):
    load_dotenv(find_dotenv(usecwd=True))  # API keys from .env; variables already set in the shell win
    parser = argparse.ArgumentParser(prog="ideataste", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("generate", help="run LLM agents to write a population of proposals")
    command.add_argument("--method", required=True, choices=METHODS)
    command.add_argument("--model", required=True, choices=models_with_role("agent"))
    command.add_argument("--area", required=True, choices=AREAS)
    command.add_argument("--n", type=int, default=300, help="number of LLM agents (paper: 300)")
    command.add_argument("--steps", type=int, default=20, help="step budget per LLM agent (paper: 20)")
    command.add_argument("--concurrency", type=int, default=8)
    command.add_argument("--out", required=True)
    command.set_defaults(run=generate)

    command = commands.add_parser("evaluate", help="score a population against the 2026 papers")
    command.add_argument("--area", required=True, choices=AREAS)
    command.add_argument("--proposals", required=True, help="proposals.jsonl written by `generate`")
    command.add_argument("--extractor", default="deepseek-v4-pro", choices=models_with_role("extractor"))
    command.add_argument("--judge", default="gpt-5.6-luna", choices=models_with_role("judge"))
    command.add_argument("--concurrency", type=int, default=8)
    command.add_argument("--out", required=True)
    command.set_defaults(run=evaluate)

    args = parser.parse_args(argv)
    return args.run(args) or 0


if __name__ == "__main__":
    sys.exit(main())
