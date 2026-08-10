import json
import sys
from uuid import UUID

from pactum.agents.causal_explainer import build_causal_explainer_graph
from pactum.agents.state import CausalExplainerState
from pactum.monitoring.incident_store import get_incident
from pactum.sources.registry import load_persisted_registrations

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python pactum/scripts/run_causal_agent.py <incident_id>")
        sys.exit(1)

    incident_id = UUID(sys.argv[1])
    load_persisted_registrations()

    incident = get_incident(incident_id)
    if incident is None:
        print(f"NOT_FOUND incident {incident_id}")
        sys.exit(1)

    app = build_causal_explainer_graph()
    result = app.invoke(CausalExplainerState(incident=incident))

    print(json.dumps(result["explanation"].model_dump(), default=str, indent=2))
    refinement_proposal = result.get("refinement_proposal")
    if refinement_proposal is not None:
        print(json.dumps(refinement_proposal.model_dump(), default=str, indent=2))
