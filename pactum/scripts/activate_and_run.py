import json
import sys

from pactum.contract_schema import parse_contract_yaml
from pactum.monitoring.runner import evaluate_contract
from pactum.registry.contract_registry import activate_version, get_active, list_history
from pactum.sources.registry import load_persisted_registrations

DATASET = "orders"

active = get_active(DATASET)
load_persisted_registrations()
if active is None:
    history = list_history(DATASET)
    drafts = [h for h in history if h.status == "draft"]
    if not drafts:
        print("NO_DRAFT")
        sys.exit(0)
    to_activate = drafts[-1].version
    activated = activate_version(DATASET, to_activate)
    print("ACTIVATED", activated.version, str(activated.id))
    active = activated
else:
    print("ALREADY_ACTIVE", active.version, str(active.id))

parsed = parse_contract_yaml(active.yaml)
outcomes = evaluate_contract(DATASET, parsed, active.id, incremental=False)
print(json.dumps([o.model_dump() for o in outcomes], default=str, indent=2))
