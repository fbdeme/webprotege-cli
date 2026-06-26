#!/usr/bin/env python3
"""onto — structured, validated ontology edit engine (the safe half of the hybrid flow).

The point: never let an LLM rewrite raw Turtle. Instead expose a fixed set of *typed,
validated delta operations*. Each command resolves IRIs, checks that referenced entities
exist (refusing to invent them), applies exactly one change, re-parses, and prints the delta.
This makes the classic ontology-edit hallucinations structurally impossible:
  - no whole-file regeneration  -> no silent triple loss
  - existence checks            -> no references to non-existent entities
  - re-parse (+ optional reasoner) -> no malformed / inconsistent output

The ontology IRI is never modified, so the result can be pushed straight back into a live
WebProtégé project via `wp apply-edits` (which requires a matching ontology IRI).

Usage:
  onto info        FILE
  onto add-class   FILE --iri :Foo [--label "..."] [--comment "..."] [--parent :Bar] [--create-missing]
  onto add-subclass FILE --child :Foo --parent :Bar
  onto add-objprop FILE --iri :rel [--label "..."] [--domain :A] [--range :B]
  onto add-dataprop FILE --iri :age [--label "..."] [--domain :A] [--range xsd:integer]
  onto add-individual FILE --iri :inst [--type :Foo] [--label "..."]
  onto add-annotation FILE --entity :Foo --prop rdfs:comment --text "..." [--lang en]
  onto remove      FILE --iri :Foo            # remove entity + every triple mentioning it
  onto remove-subclass FILE --child :Foo --parent :Bar
  onto validate    FILE [--reason]            # parse + structural checks (+ HermiT consistency)
  onto query       FILE "SPARQL..."  [--json]

IRIs accept: full http(s) IRIs, prefixed names bound in the file (rdfs:comment, ex:Foo),
or :Name / Name resolved against the ontology's default namespace.
"""
import argparse
import json
import os
import re
import sys
import tempfile

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

# WebProtégé/OWLAPI round-trips a plain literal like "user@dept.edu" out as
#   "user"@dept.edu  — i.e. it treats the domain as a language tag. But a BCP47
# language tag can never contain a '.', so this is invalid Turtle/RDF and rdflib
# (correctly) refuses to load it. Any "..."@<tag-with-a-dot> is therefore an
# unambiguously mangled literal; re-join it into the quoted string.
_MANGLED_LANGTAG = re.compile(r'"((?:[^"\\]|\\.)*)"@([A-Za-z0-9-]+(?:\.[A-Za-z0-9.-]+))')


def _sanitize_turtle(text):
    return _MANGLED_LANGTAG.subn(r'"\1@\2"', text)

KIND_TYPE = {
    "class": OWL.Class,
    "objprop": OWL.ObjectProperty,
    "dataprop": OWL.DatatypeProperty,
    "annprop": OWL.AnnotationProperty,
    "individual": OWL.NamedIndividual,
}


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load(path):
    if not os.path.exists(path):
        die(f"file not found: {path}")
    g = Graph(bind_namespaces="none")  # keep only the file's own prefixes (clean output)
    is_xml = path.lower().endswith((".owl", ".rdf", ".xml"))
    try:
        if is_xml:
            g.parse(path, format="xml")
        else:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            text, n = _sanitize_turtle(text)
            if n:
                print(f"note: repaired {n} mangled language-tag literal(s) from WebProtégé "
                      f"export (e.g. emails)", file=sys.stderr)
            g.parse(data=text, format="turtle")
    except Exception as e:
        die(f"could not parse {path}: {e}")
    bound = dict(g.namespaces())
    for pfx, ns in (("rdf", RDF), ("rdfs", RDFS), ("owl", OWL), ("xsd", XSD)):
        if pfx not in bound:
            g.bind(pfx, ns)
    _ensure_default_ns(g)
    return g


def ontology_iri(g):
    for s in g.subjects(RDF.type, OWL.Ontology):
        if isinstance(s, URIRef):
            return s
    return None


def _ensure_default_ns(g):
    """Make sure the empty prefix resolves, so :Name works and serializes cleanly."""
    if any(p == "" for p, _ in g.namespaces()):
        return
    oi = ontology_iri(g)
    base = (str(oi) + ("" if str(oi).endswith(("#", "/")) else "#")) if oi else None
    if base:
        g.bind("", Namespace(base))


def expand(g, term):
    """Resolve a user term to a URIRef using the graph's prefixes / default ns."""
    if term is None:
        return None
    t = term.strip()
    if t.startswith(("http://", "https://", "urn:")):
        return URIRef(t)
    nsmap = dict(g.namespaces())
    if t.startswith(":"):
        local = t[1:]
        if "" in nsmap:
            return URIRef(str(nsmap[""]) + local)
        die("no default namespace in file; use a full IRI or prefix:Name")
    if ":" in t:
        pfx, local = t.split(":", 1)
        if pfx in nsmap:
            return URIRef(str(nsmap[pfx]) + local)
        die(f"unknown prefix '{pfx}:' (not bound in file)")
    # bare name -> default ns
    if "" in nsmap:
        return URIRef(str(nsmap[""]) + t)
    die(f"cannot resolve '{term}'; bind a default namespace or use a full IRI")


def short(g, uri):
    try:
        return g.namespace_manager.normalizeUri(uri)
    except Exception:
        return str(uri)


def is_kind(g, uri, kind):
    return (uri, RDF.type, KIND_TYPE[kind]) in g


def require(g, uri, kind, what):
    if not is_kind(g, uri, kind):
        die(f"{what} {short(g, uri)} is not a declared {kind} in this ontology "
            f"(refusing to reference a non-existent entity; declare it first or use --create-missing)")


def save(g, path, out=None):
    target = out or path
    before_iri = ontology_iri(g)
    data = g.serialize(format="turtle")
    with open(target, "w", encoding="utf-8") as f:
        f.write(data)
    # re-parse guard: the file we just wrote must load, and keep its ontology IRI
    chk = Graph()
    try:
        chk.parse(target, format="turtle")
    except Exception as e:
        die(f"internal: produced unparseable Turtle ({e}) — aborted")
    after_iri = ontology_iri(chk)
    if before_iri and after_iri != before_iri:
        die(f"internal: ontology IRI changed ({before_iri} -> {after_iri}) — aborted")
    return target


def added(g, triples, path, out, note):
    new = [t for t in triples if t not in g]
    for t in new:
        g.add(t)
    if not new:
        print("no change (already present)")
        return
    save(g, path, out)
    print(f"{note}  (+{len(new)} triple(s))")
    for s, p, o in new:
        print(f"  + {short(g, s)} {short(g, p)} {_fmt_o(g, o)}")


def _fmt_o(g, o):
    if isinstance(o, Literal):
        return f'"{o}"' + (f"@{o.language}" if o.language else "")
    return short(g, o)


# ---- commands --------------------------------------------------------------

def cmd_info(g, a):
    oi = ontology_iri(g)
    counts = {k: len(set(g.subjects(RDF.type, t))) for k, t in KIND_TYPE.items()}
    classes = set(g.subjects(RDF.type, OWL.Class))
    # "instances" = anything typed with a declared class (covers individuals that are only
    # `a :SomeClass`, not just explicit owl:NamedIndividual)
    instances = {s for s, _, o in g.triples((None, RDF.type, None)) if o in classes}
    print(f"ontology IRI : {oi or '(anonymous!)'}")
    if not oi:
        print("  WARNING: anonymous ontology — `wp apply-edits` will NOT apply changes")
    print(f"triples      : {len(g)}")
    for k in ("class", "objprop", "dataprop", "annprop"):
        print(f"{k:12s} : {counts[k]}")
    print(f"individuals  : {counts['individual']} owl:NamedIndividual, {len(instances)} class instance(s)")
    print("prefixes     :")
    for p, n in sorted(g.namespaces()):
        print(f"  {p or '(default)'}: {n}")


def cmd_add_class(g, a):
    iri = expand(g, a.iri)
    triples = [(iri, RDF.type, OWL.Class)]
    if a.label:
        triples.append((iri, RDFS.label, Literal(a.label, lang=a.lang)))
    if a.comment:
        triples.append((iri, RDFS.comment, Literal(a.comment, lang=a.lang)))
    if a.parent:
        parent = expand(g, a.parent)
        if a.create_missing and not is_kind(g, parent, "class"):
            g.add((parent, RDF.type, OWL.Class))
            print(f"(created missing parent {short(g, parent)})")
        require(g, parent, "class", "parent")
        triples.append((iri, RDFS.subClassOf, parent))
    added(g, triples, a.file, a.out, f"added class {a.iri}")


def cmd_add_subclass(g, a):
    child, parent = expand(g, a.child), expand(g, a.parent)
    require(g, child, "class", "child")
    require(g, parent, "class", "parent")
    added(g, [(child, RDFS.subClassOf, parent)], a.file, a.out,
          f"{a.child} subClassOf {a.parent}")


def cmd_add_objprop(g, a):
    iri = expand(g, a.iri)
    triples = [(iri, RDF.type, OWL.ObjectProperty)]
    if a.label:
        triples.append((iri, RDFS.label, Literal(a.label, lang=a.lang)))
    if a.domain:
        d = expand(g, a.domain); require(g, d, "class", "domain")
        triples.append((iri, RDFS.domain, d))
    if a.range:
        r = expand(g, a.range); require(g, r, "class", "range")
        triples.append((iri, RDFS.range, r))
    added(g, triples, a.file, a.out, f"added object property {a.iri}")


def cmd_add_dataprop(g, a):
    iri = expand(g, a.iri)
    triples = [(iri, RDF.type, OWL.DatatypeProperty)]
    if a.label:
        triples.append((iri, RDFS.label, Literal(a.label, lang=a.lang)))
    if a.domain:
        d = expand(g, a.domain); require(g, d, "class", "domain")
        triples.append((iri, RDFS.domain, d))
    if a.range:
        r = expand(g, a.range)  # an xsd datatype or class; no existence check for datatypes
        triples.append((iri, RDFS.range, r))
    added(g, triples, a.file, a.out, f"added data property {a.iri}")


def cmd_add_individual(g, a):
    iri = expand(g, a.iri)
    triples = [(iri, RDF.type, OWL.NamedIndividual)]
    if a.type:
        t = expand(g, a.type); require(g, t, "class", "type")
        triples.append((iri, RDF.type, t))
    if a.label:
        triples.append((iri, RDFS.label, Literal(a.label, lang=a.lang)))
    added(g, triples, a.file, a.out, f"added individual {a.iri}")


def cmd_add_annotation(g, a):
    ent = expand(g, a.entity)
    if not any(g.triples((ent, RDF.type, None))):
        die(f"entity {a.entity} is not declared in this ontology")
    prop = expand(g, a.prop)
    added(g, [(ent, prop, Literal(a.text, lang=a.lang))], a.file, a.out,
          f"annotated {a.entity} with {a.prop}")


def cmd_remove(g, a):
    iri = expand(g, a.iri)
    triples = set(g.triples((iri, None, None))) | set(g.triples((None, None, iri)))
    triples = {t for t in triples if t[0] != ontology_iri(g)}  # never touch the ontology decl
    if not triples:
        print("no change (entity not present)")
        return
    for t in triples:
        g.remove(t)
    save(g, a.file, a.out)
    print(f"removed {a.iri}  (-{len(triples)} triple(s))")
    for s, p, o in triples:
        print(f"  - {short(g, s)} {short(g, p)} {_fmt_o(g, o)}")


def cmd_remove_subclass(g, a):
    child, parent = expand(g, a.child), expand(g, a.parent)
    t = (child, RDFS.subClassOf, parent)
    if t not in g:
        print("no change (axiom not present)")
        return
    g.remove(t)
    save(g, a.file, a.out)
    print(f"removed {a.child} subClassOf {a.parent}  (-1 triple)")


def cmd_validate(g, a):
    problems = []
    classes = set(g.subjects(RDF.type, OWL.Class))
    # structural: subClassOf / domain / range pointing at undeclared classes
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
        if isinstance(o, URIRef) and o not in classes and not str(o).startswith(str(OWL)):
            problems.append(f"subClassOf target not declared as class: {short(g,s)} -> {short(g,o)}")
    for pred, lbl in ((RDFS.domain, "domain"), (RDFS.range, "range")):
        for s, _, o in g.triples((None, pred, None)):
            if isinstance(o, URIRef) and o not in classes \
               and not str(o).startswith((str(OWL), str(RDFS), str(XSD))):
                problems.append(f"{lbl} target not declared as class: {short(g,s)} -> {short(g,o)}")
    print(f"parse: OK ({len(g)} triples)")
    if problems:
        print(f"structural warnings ({len(problems)}):")
        for p in problems:
            print(f"  ! {p}")
    else:
        print("structural: OK")
    if a.reason:
        _reason(a.file)


def _reason(path):
    """Run HermiT (via owlready2) for consistency / unsatisfiable classes. Best-effort."""
    try:
        import owlready2
    except Exception:
        print("reasoner: owlready2 not installed — skipped"); return
    g = Graph(); g.parse(path)
    tmp = tempfile.NamedTemporaryFile(suffix=".owl", delete=False).name
    g.serialize(destination=tmp, format="xml")
    try:
        w = owlready2.World()
        onto = w.get_ontology("file://" + os.path.abspath(tmp)).load()
        try:
            with onto:
                owlready2.sync_reasoner(w, debug=0)
        except owlready2.OwlReadyInconsistentOntologyError:
            print("reasoner: INCONSISTENT ontology"); return
        unsat = [c.iri for c in w.inconsistent_classes()]
        if unsat:
            print(f"reasoner: {len(unsat)} unsatisfiable class(es):")
            for u in unsat:
                print(f"  ! {u}")
        else:
            print("reasoner: consistent, no unsatisfiable classes")
    except Exception as e:
        print(f"reasoner: could not run ({e}) — check Java is available")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def cmd_query(g, a):
    try:
        res = g.query(a.sparql)
    except Exception as e:
        die(f"bad SPARQL: {e}")
    rows = [[_fmt_o(g, v) if v is not None else "" for v in row] for row in res]
    if a.json:
        cols = [str(v) for v in res.vars] if res.vars else []
        print(json.dumps([dict(zip(cols, r)) for r in rows], ensure_ascii=False, indent=2))
    else:
        for r in rows:
            print("\t".join(r))
        print(f"({len(rows)} row(s))", file=sys.stderr)


# ---- arg parsing -----------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="onto", description="structured, validated ontology editing")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("file", help="ontology file (.ttl/.owl)")
        sp.add_argument("--out", help="write here instead of editing in place")
        sp.add_argument("--lang", help="language tag for labels/comments/annotations")

    s = sub.add_parser("info"); s.add_argument("file"); s.set_defaults(fn=cmd_info, out=None, lang=None)

    s = sub.add_parser("add-class"); common(s)
    s.add_argument("--iri", required=True); s.add_argument("--label"); s.add_argument("--comment")
    s.add_argument("--parent"); s.add_argument("--create-missing", action="store_true", dest="create_missing")
    s.set_defaults(fn=cmd_add_class)

    s = sub.add_parser("add-subclass"); common(s)
    s.add_argument("--child", required=True); s.add_argument("--parent", required=True)
    s.set_defaults(fn=cmd_add_subclass)

    s = sub.add_parser("add-objprop"); common(s)
    s.add_argument("--iri", required=True); s.add_argument("--label")
    s.add_argument("--domain"); s.add_argument("--range")
    s.set_defaults(fn=cmd_add_objprop)

    s = sub.add_parser("add-dataprop"); common(s)
    s.add_argument("--iri", required=True); s.add_argument("--label")
    s.add_argument("--domain"); s.add_argument("--range")
    s.set_defaults(fn=cmd_add_dataprop)

    s = sub.add_parser("add-individual"); common(s)
    s.add_argument("--iri", required=True); s.add_argument("--type"); s.add_argument("--label")
    s.set_defaults(fn=cmd_add_individual)

    s = sub.add_parser("add-annotation"); common(s)
    s.add_argument("--entity", required=True); s.add_argument("--prop", required=True)
    s.add_argument("--text", required=True)
    s.set_defaults(fn=cmd_add_annotation)

    s = sub.add_parser("remove"); common(s); s.add_argument("--iri", required=True)
    s.set_defaults(fn=cmd_remove)

    s = sub.add_parser("remove-subclass"); common(s)
    s.add_argument("--child", required=True); s.add_argument("--parent", required=True)
    s.set_defaults(fn=cmd_remove_subclass)

    s = sub.add_parser("validate"); s.add_argument("file")
    s.add_argument("--reason", action="store_true"); s.set_defaults(fn=cmd_validate, out=None, lang=None)

    s = sub.add_parser("query"); s.add_argument("file"); s.add_argument("sparql")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_query, out=None, lang=None)
    return p


def main():
    a = build_parser().parse_args()
    g = load(a.file)
    a.fn(g, a)


if __name__ == "__main__":
    main()
