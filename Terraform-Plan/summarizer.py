#!/usr/bin/env python3
import argparse
import datetime
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, List

from dotenv import load_dotenv

from azure_services import AzureServices

load_dotenv()


def load_plan(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_plan_id(plan_path: str) -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    file_hash = hashlib.md5(Path(plan_path).read_bytes()).hexdigest()[:8]
    return f"plan_{file_hash}_{ts}"


def summarize_change(change: Dict[str, Any]) -> Dict[str, Any]:
    address = change.get("address", "unknown")
    rtype = change.get("type", "unknown")
    name = change.get("name", "unknown")
    actions: List[str] = change.get("change", {}).get("actions", [])

    action_map = {
        ("create",): "create",
        ("delete",): "delete",
        ("update",): "update",
        ("create", "delete"): "replace",
        ("delete", "create"): "replace",
    }
    op = action_map.get(tuple(actions), ",".join(actions) if actions else "no-op")

    explanation = f"Terraform will {op} {rtype} '{name}' at address '{address}'."

    return {
        "address": address,
        "type": rtype,
        "name": name,
        "operation": op,
        "actions": actions,
        "short_explanation": explanation,
    }


def summarize_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    resource_changes = plan.get("resource_changes", [])
    summaries = [summarize_change(c) for c in resource_changes if c.get("type")]

    ops_count: Dict[str, int] = {}
    for s in summaries:
        ops_count[s["operation"]] = ops_count.get(s["operation"], 0) + 1

    summary_text_lines = [
        f"Total resources with changes: {len(summaries)}",
        f"Operations breakdown: {ops_count}",
    ]
    for s in summaries:
        summary_text_lines.append(
            f"- {s['operation'].upper()} {s['type']} '{s['name']}' at {s['address']}"
        )
    summary_text = "\n".join(summary_text_lines)

    return {
        "total_changes": len(summaries),
        "operations_breakdown": ops_count,
        "resources": summaries,
        "summary_text": summary_text,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Summarize Terraform plan and index to Azure AI Search with embeddings."
    )
    parser.add_argument("plan_json", help="Path to terraform plan JSON (terraform show -json)")
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Ask Azure OpenAI to generate a natural-language explanation for the plan.",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Do not index to Azure AI Search (local summary only).",
    )
    args = parser.parse_args()

    plan = load_plan(args.plan_json)
    summary = summarize_plan(plan)
    plan_id = generate_plan_id(args.plan_json)

    print("=== Parsed summary ===")
    print(json.dumps(summary, indent=2))

    services = AzureServices()
    services.create_index_if_not_exists()

    if not args.no_index:
        services.index_plan_with_embeddings(plan_id, summary["resources"])

    if args.explain:
        explanation = services.explain_plan(summary["summary_text"])
        print("\n=== AI Explanation ===")
        print(explanation)

    print(f"\nPlan ID: {plan_id}")


if __name__ == "__main__":
    main()
