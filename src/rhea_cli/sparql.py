from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SparqlPreset:
    name: str
    description: str
    query_template: str

    def render(self, *, limit: int) -> str:
        return self.query_template.format(limit=limit)


SPARQL_PRESETS: dict[str, SparqlPreset] = {
    "graphs": SparqlPreset(
        name="graphs",
        description="List named graphs exposed by the endpoint.",
        query_template="""
SELECT ?graph
WHERE {{
  GRAPH ?graph {{
    ?s ?p ?o .
  }}
}}
GROUP BY ?graph
ORDER BY ?graph
LIMIT {limit}
""".strip(),
    ),
    "classes": SparqlPreset(
        name="classes",
        description="List RDF classes with instance counts.",
        query_template="""
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?class (COUNT(?entity) AS ?entityCount)
WHERE {{
  ?entity a ?class .
}}
GROUP BY ?class
ORDER BY DESC(xsd:integer(?entityCount)) ?class
LIMIT {limit}
""".strip(),
    ),
    "predicates": SparqlPreset(
        name="predicates",
        description="List predicates in the dataset with triple counts.",
        query_template="""
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?predicate (COUNT(*) AS ?tripleCount)
WHERE {{
  ?subject ?predicate ?object .
}}
GROUP BY ?predicate
ORDER BY DESC(xsd:integer(?tripleCount)) ?predicate
LIMIT {limit}
""".strip(),
    ),
    "predicate-examples": SparqlPreset(
        name="predicate-examples",
        description="Show one sample subject and object for each predicate.",
        query_template="""
SELECT ?predicate
       (SAMPLE(?subject) AS ?exampleSubject)
       (SAMPLE(?object) AS ?exampleObject)
WHERE {{
  ?subject ?predicate ?object .
}}
GROUP BY ?predicate
ORDER BY ?predicate
LIMIT {limit}
""".strip(),
    ),
    "reaction-predicates": SparqlPreset(
        name="reaction-predicates",
        description="List predicates used on top-level Rhea reaction resources.",
        query_template="""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rh: <http://rdf.rhea-db.org/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?predicate (COUNT(*) AS ?tripleCount)
WHERE {{
  ?reaction rdfs:subClassOf rh:Reaction .
  ?reaction ?predicate ?value .
}}
GROUP BY ?predicate
ORDER BY DESC(xsd:integer(?tripleCount)) ?predicate
LIMIT {limit}
""".strip(),
    ),
    "reaction-shape": SparqlPreset(
        name="reaction-shape",
        description="Show reaction predicates with one sample value for schema orientation.",
        query_template="""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rh: <http://rdf.rhea-db.org/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?predicate
       (COUNT(*) AS ?tripleCount)
       (SAMPLE(?value) AS ?exampleValue)
WHERE {{
  ?reaction rdfs:subClassOf rh:Reaction .
  ?reaction ?predicate ?value .
}}
GROUP BY ?predicate
ORDER BY DESC(xsd:integer(?tripleCount)) ?predicate
LIMIT {limit}
""".strip(),
    ),
}


def list_sparql_presets() -> list[dict[str, str]]:
    return [
        {"name": preset.name, "description": preset.description}
        for preset in sorted(SPARQL_PRESETS.values(), key=lambda item: item.name)
    ]


def render_sparql_preset(name: str, *, limit: int) -> str:
    try:
        preset = SPARQL_PRESETS[name]
    except KeyError as exc:
        raise KeyError(f"unknown SPARQL preset: {name}") from exc
    return preset.render(limit=limit)


def sparql_accept_header(output_format: str, accept: str | None = None) -> str:
    if accept:
        return accept
    if output_format == "json":
        return "application/sparql-results+json, application/json;q=0.9"
    if output_format == "csv":
        return "text/csv"
    if output_format == "tsv":
        return "text/tab-separated-values"
    if output_format == "text":
        return "application/sparql-results+json, application/json;q=0.9, text/plain;q=0.8"
    return "*/*"


def parse_sparql_json(payload: dict[str, Any]) -> dict[str, Any]:
    if "boolean" in payload:
        return {"kind": "ask", "boolean": bool(payload["boolean"])}
    variables = list(payload.get("head", {}).get("vars", []))
    bindings = list(payload.get("results", {}).get("bindings", []))
    items = [
        {variable: _term_value(binding.get(variable)) for variable in variables}
        for binding in bindings
    ]
    return {
        "kind": "select",
        "variables": variables,
        "count": len(items),
        "items": items,
        "bindings": bindings,
    }


def _term_value(term: dict[str, Any] | None) -> str:
    if not term:
        return ""
    value = str(term.get("value", ""))
    lang = term.get("xml:lang") or term.get("lang")
    datatype = term.get("datatype")
    if lang:
        return f"{value}@{lang}"
    if datatype and datatype != "http://www.w3.org/2001/XMLSchema#string":
        return f"{value}^^{datatype}"
    return value


__all__ = [
    "SPARQL_PRESETS",
    "SparqlPreset",
    "list_sparql_presets",
    "parse_sparql_json",
    "render_sparql_preset",
    "sparql_accept_header",
]
