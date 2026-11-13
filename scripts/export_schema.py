"""Write the JSON Schema of the demo data models; `npm run types` turns it into TypeScript.

uv run python scripts/export_schema.py
"""

import json
from pathlib import Path

from pydantic.json_schema import models_json_schema

from docintel.demo_models import DemoContract, DemoIndex

OUT = Path(__file__).resolve().parents[1] / "web" / "src" / "types" / "schema.json"


def tuples_to_draft7(node):
    """Pydantic writes tuples as JSON Schema 2020-12 `prefixItems`; json-schema-to-typescript
    reads the draft-07 form (`items` as a list). Without this, (start, end) spans become
    `[unknown, unknown]` in TypeScript."""
    if isinstance(node, dict):
        if "prefixItems" in node:
            node["items"] = node.pop("prefixItems")
            node["minItems"] = node["maxItems"] = len(node["items"])
        for v in node.values():
            tuples_to_draft7(v)
    elif isinstance(node, list):
        for v in node:
            tuples_to_draft7(v)
    return node


_, schema = models_json_schema(
    [(DemoContract, "serialization"), (DemoIndex, "serialization")], title="DocintelDemo"
)
OUT.write_text(json.dumps(tuples_to_draft7(schema), indent=1) + "\n")
print(f"wrote {OUT}")
