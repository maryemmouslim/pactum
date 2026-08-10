import psycopg

from pactum.settings import settings

url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")

query = """
SELECT
    id,
    dataset_id,
    detected_at,
    kind,
    severity,
    signature,
    payload::text,
    contract_version_id
FROM incidents
ORDER BY detected_at DESC
LIMIT 20
"""

with psycopg.connect(url) as conn:
    rows = conn.execute(query).fetchall()
    for row in rows:
        print(row)
