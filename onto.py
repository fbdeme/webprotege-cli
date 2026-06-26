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
  onto add-disjoint FILE --classes :A :B [:C ...]     # disjointWith (2) / AllDisjointClasses (3+)
  onto add-characteristic FILE --prop :p --type functional|inverse-functional|transitive|symmetric|asymmetric|reflexive|irreflexive
  onto add-inverse FILE --prop :p --inverse :q        # :p owl:inverseOf :q
  onto remove      FILE --iri :Foo            # remove entity + every triple mentioning it
  onto remove-subclass FILE --child :Foo --parent :Bar
  onto validate    FILE [--reason]            # parse + structural checks (+ HermiT consistency)
  onto query       FILE "SPARQL..."  [--json]
  onto diff        FILE OTHER                  # structural round-trip diff: what OTHER loses/adds vs FILE

IRIs accept: full http(s) IRIs, prefixed names bound in the file (rdfs:comment, ex:Foo),
or :Name / Name resolved against the ontology's default namespace.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.compare import isomorphic
from rdflib.namespace import OWL, RDF, RDFS, XSD

# WebProtégé/OWLAPI round-trips a plain literal like "user@dept.edu" out as
#   "user"@dept.edu  — i.e. it treats the domain as a language tag. But a BCP47
# language tag can never contain a '.', so this is invalid Turtle/RDF and rdflib
# (correctly) refuses to load it. Any "..."@<tag-with-a-dot> is therefore an
# unambiguously mangled literal; re-join it into the quoted string.
#
# Two shapes occur in real exports:
#   1. the email is the whole value     -> ... "user"@dept.edu ;
#   2. the email is *embedded* in text  -> ... "...contact"@e.ntu.edu.sg, NPGS 무본드). ;
# In (2) the original text continues past the bogus tag, so we must also pull that
# trailing run (up to the statement terminator at end-of-line) back inside the quotes,
# otherwise the stray ", NPGS ..." reads as a Turtle objectList and parsing dies.
# group 3 captures that trailing run (empty for shape 1); the terminator stays outside.
_MANGLED_LANGTAG = re.compile(
    r'"((?:[^"\\]|\\.)*)"'                    # 1: literal body up to the spurious close-quote
    r'@([A-Za-z0-9-]+(?:\.[A-Za-z0-9.-]+))'   # 2: the bogus "language tag" (a dotted domain)
    r'([^"\n]*?)'                             # 3: any trailing original text on the same line
    r'(?=[ \t]*[;,.]?[ \t]*$)',              # ...stopping at the statement terminator / EOL
    re.MULTILINE,
)


def _sanitize_turtle(text):
    return _MANGLED_LANGTAG.subn(r'"\1@\2\3"', text)

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


def reified_statements(g):
    """Nodes using RDF reification (rdf:Statement + rdf:subject/predicate/object).

    OWLAPI (and therefore WebProtégé) does NOT model RDF reification: on import it
    keeps the node's annotations but drops rdf:subject/predicate/object, so a
    push->export round-trip silently orphans the provenance (verified — docs/issues.md
    #14). We surface these so the user is warned before treating an export as truth."""
    return set(g.subjects(RDF.type, RDF.Statement)) | set(g.subjects(RDF.subject, None))


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
    reif = reified_statements(g)
    if reif:
        print(f"reification  : {len(reif)} rdf:Statement node(s) "
              f"— dropped by a WebProtégé round-trip (see issues.md #14)")
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


# property characteristics, mapped to their OWL class. functional applies to
# object *and* data properties; the rest are object-property only.
CHARACTERISTIC = {
    "functional": OWL.FunctionalProperty,
    "inverse-functional": OWL.InverseFunctionalProperty,
    "transitive": OWL.TransitiveProperty,
    "symmetric": OWL.SymmetricProperty,
    "asymmetric": OWL.AsymmetricProperty,
    "reflexive": OWL.ReflexiveProperty,
    "irreflexive": OWL.IrreflexiveProperty,
}
_OBJECT_ONLY = set(CHARACTERISTIC) - {"functional"}


def prop_kind(g, uri):
    if is_kind(g, uri, "objprop"):
        return "objprop"
    if is_kind(g, uri, "dataprop"):
        return "dataprop"
    return None


def cmd_add_disjoint(g, a):
    cls = []
    for c in a.classes:
        u = expand(g, c)
        require(g, u, "class", "disjoint member")
        if u not in cls:
            cls.append(u)
    if len(cls) < 2:
        die("need at least 2 distinct classes for --classes")
    if len(cls) == 2:
        added(g, [(cls[0], OWL.disjointWith, cls[1])], a.file, a.out,
              f"declared {short(g, cls[0])} disjointWith {short(g, cls[1])}")
        return
    # n-ary: owl:AllDisjointClasses, deduped by member set
    target = set(cls)
    for ax in g.subjects(RDF.type, OWL.AllDisjointClasses):
        for members in g.objects(ax, OWL.members):
            if set(Collection(g, members)) == target:
                print("no change (equivalent AllDisjointClasses already present)")
                return
    axiom, lst = BNode(), BNode()
    Collection(g, lst, cls)
    g.add((axiom, RDF.type, OWL.AllDisjointClasses))
    g.add((axiom, OWL.members, lst))
    save(g, a.file, a.out)
    names = ", ".join(short(g, c) for c in cls)
    print(f"declared AllDisjointClasses over {len(cls)} classes: {names}")


def cmd_add_characteristic(g, a):
    p = expand(g, a.prop)
    kind = prop_kind(g, p)
    if kind is None:
        die(f"property {a.prop} is not a declared object/data property "
            f"(refusing to characterize a non-existent property; declare it first)")
    if a.type in _OBJECT_ONLY and kind != "objprop":
        die(f"characteristic '{a.type}' applies only to object properties; "
            f"{a.prop} is a {kind}")
    added(g, [(p, RDF.type, CHARACTERISTIC[a.type])], a.file, a.out,
          f"declared {a.prop} as {a.type} property")


def cmd_add_inverse(g, a):
    p = expand(g, a.prop)
    require(g, p, "objprop", "property")
    q = expand(g, a.inverse)
    require(g, q, "objprop", "inverse")
    added(g, [(p, OWL.inverseOf, q)], a.file, a.out,
          f"declared {a.prop} inverseOf {a.inverse}")


def _split_named(g):
    """Partition triples into (bnode-free set, bnode-bearing list).

    Bnode-free triples have stable identity, so a plain set-diff is exact. Bnode-bearing
    ones (reification, lists, restrictions) can't be paired by identity across files, so
    we compare them by per-predicate count instead."""
    named, bn = set(), []
    for t in g:
        s, _, o = t
        (bn.append(t) if isinstance(s, BNode) or isinstance(o, BNode) else named.add(t))
    return named, bn


# rdf:type objects that WebProtégé/OWLAPI legitimately *materializes* on import
# (explicit declarations) — additions of these are normalization, not corruption.
_BENIGN_TYPES = {OWL.NamedIndividual, OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty,
                 OWL.AnnotationProperty, RDFS.Datatype, OWL.Ontology}
_SPO = (RDF.subject, RDF.predicate, RDF.object)


def cmd_diff(g, a):
    """Structural round-trip differential — what does B lose / add vs A.

    The WebProtégé boundary is lossy by design (RDF<->OWL is not 1:1) and the losses are
    SILENT: the export still parses and the counts look healthy. The only way they can't
    hide is a differential. Use `onto diff <canonical> <export>` after a round-trip (or to
    check any two ontology files agree). Exit 1 if any A assertion is missing from B.

    Method: bnode-free triples are diffed exactly; bnode-bearing structures (reification,
    lists, restrictions) are compared by per-predicate count (a dropped count = structural
    loss) plus an explicit RDF-reification check (issue #14)."""
    A = g                       # already loaded from a.file
    B = load(a.other)
    print(f"A: {a.file}  ({len(A)} triples)")
    print(f"B: {a.other}  ({len(B)} triples)")
    if isomorphic(A, B):
        print("\nverdict: IDENTICAL — A and B are isomorphic (no loss, no additions).")
        return

    NA, bnA = _split_named(A)
    NB, bnB = _split_named(B)
    lost, added = NA - NB, NB - NA

    print("\nnamed (bnode-free) triples:")
    print(f"  lost  (in A, not B): {len(lost)}")
    print(f"  added (in B, not A): {len(added)}")
    if lost:
        print("  LOST by predicate:")
        for p, n in Counter(p for _, p, _ in lost).most_common():
            print(f"    {n:4d}  {short(A, p)}")
        for t in list(lost)[:8]:
            print("      e.g. " + "  ".join(short(A, x) for x in t))
    if added:
        tb = Counter(o for _, p, o in added if p == RDF.type)
        benign = sum(n for o, n in tb.items() if o in _BENIGN_TYPES)
        print(f"  added breakdown: {benign} benign type declaration(s) "
              f"(NamedIndividual/Class/Datatype/...), {len(added) - benign} other")

    cA, cB = Counter(p for _, p, _ in bnA), Counter(p for _, p, _ in bnB)
    drops = {p: (cA[p], cB.get(p, 0)) for p in cA if cA[p] > cB.get(p, 0)}
    print("\nblank-node structures (reification / lists / restrictions):")
    print(f"  bnode-bearing triples: A={len(bnA)}  B={len(bnB)}")
    if drops:
        print("  predicate counts that DROPPED A->B (structural loss signal):")
        for p, (na, nb) in sorted(drops.items(), key=lambda kv: kv[1][1] - kv[1][0]):
            print(f"    {short(A, p):42s} {na:4d} -> {nb}")

    reifA, reifB = reified_statements(A), reified_statements(B)
    spoA = sum(len(list(A.triples((None, q, None)))) for q in _SPO)
    spoB = sum(len(list(B.triples((None, q, None)))) for q in _SPO)
    reif_loss = bool(reifA) and spoB < spoA
    if reifA or reifB:
        msg = ("  <-- DROPPED: provenance orphaned (issue #14)" if reif_loss else "")
        print(f"  reification: rdf:Statement nodes A={len(reifA)} B={len(reifB)}; "
              f"s/p/o link triples A={spoA} B={spoB}{msg}")

    lost_bn = sum(na - nb for na, nb in drops.values())
    print()
    if lost or drops:
        parts = []
        if lost:
            parts.append(f"{len(lost)} named triple(s)")
        if drops:
            parts.append(f"{lost_bn} bnode-structure triple(s)")
        print("verdict: LOSS DETECTED — " + " + ".join(parts) + " in A are missing from B.")
        if reif_loss:
            print("  this includes RDF reification (provenance links) — see docs/issues.md #14.")
        sys.exit(1)
    extra = f" (B adds {len(added)} triple(s), all normalization)" if added else ""
    print(f"verdict: NO LOSS — every A assertion is present in B{extra}.")


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
    reif = reified_statements(g)
    if reif:
        print(f"round-trip warning: {len(reif)} RDF-reified statement(s) "
              "(rdf:subject/predicate/object)")
        print("  WebProtégé/OWLAPI does not model RDF reification — `wp apply-edits` then")
        print("  `wp export` will silently DROP the subject/predicate/object links and orphan")
        print("  their annotations. Keep the canonical file as the source of truth; push to")
        print("  WebProtégé for viewing only, never edit a fresh export (see issues.md #14).")
    if a.reason:
        _reason(a.file)


# HermiT supports only the OWL 2 datatype map; a literal typed e.g. xsd:gYear
# makes it abort with this message (the datatype IRI is quoted in it).
_HERMIT_UNSUPPORTED_DT = re.compile(r"datatype '([^']+)' is not part")


def _short_dt(iri):
    s = str(iri)
    if s.startswith(str(XSD)):
        return "xsd:" + s[len(str(XSD)):]
    return s.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _relax_datatypes(src, relax):
    """Copy `src`, rewriting every literal (and rdfs:range target) that uses a
    datatype in `relax` to an opaque string, so a reasoner lacking that datatype
    can still run. The caller's file is never touched."""
    if not relax:
        return src
    relaxU = {URIRef(x) for x in relax}
    ng = Graph()
    for pfx, ns in src.namespaces():
        ng.bind(pfx, ns)
    for s, p, o in src:
        if isinstance(o, Literal) and o.datatype in relaxU:
            o = Literal(str(o))
        elif isinstance(o, URIRef) and o in relaxU:
            o = XSD.string
        ng.add((s, p, o))
    return ng


def _reason(path):
    """Check consistency / unsatisfiable classes with HermiT (via owlready2).

    HermiT only supports the OWL 2 datatype map, so a literal typed e.g.
    xsd:gYear makes it abort. When that happens we relax the offending datatype
    to an opaque string in a temp copy used *only* for reasoning and retry, so
    class-level reasoning still runs. Best-effort: never raises. (Pellet is the
    textbook fallback, but owlready2's bundled Pellet needs a newer JRE than this
    environment ships — class file 69 vs 65 — so we relax instead.)"""
    try:
        import owlready2
    except Exception:
        print("reasoner: owlready2 not installed — skipped"); return

    base = Graph(); base.parse(path)
    relaxed, seen = [], set()
    for _ in range(16):  # bounded: one pass per distinct unsupported datatype
        g = _relax_datatypes(base, seen)
        tmp = tempfile.NamedTemporaryFile(suffix=".owl", delete=False).name
        g.serialize(destination=tmp, format="xml")
        try:
            w = owlready2.World()
            onto = w.get_ontology("file://" + os.path.abspath(tmp)).load()
            with onto:
                owlready2.sync_reasoner_hermit(w, debug=0)
        except owlready2.OwlReadyInconsistentOntologyError:
            _report_relaxed(relaxed)
            print("reasoner: INCONSISTENT ontology")
            return
        except Exception as e:
            m = _HERMIT_UNSUPPORTED_DT.search(str(e))
            if m and m.group(1) not in seen:
                seen.add(m.group(1)); relaxed.append(m.group(1))
                continue
            if m or "UnsupportedDatatype" in str(e):
                dt = _short_dt(m.group(1)) if m else "an unsupported datatype"
                print(f"reasoner: skipped — {dt} is outside the OWL 2 datatype map "
                      f"and could not be relaxed; parse/structural checks above still apply.")
            else:
                print(f"reasoner: could not run ({str(e)[:160]}) — check Java is available")
            return
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        _report_relaxed(relaxed)
        unsat = [c.iri for c in w.inconsistent_classes()]
        if unsat:
            print(f"reasoner: {len(unsat)} unsatisfiable class(es):")
            for u in unsat:
                print(f"  ! {u}")
        else:
            print("reasoner: consistent, no unsatisfiable classes")
        return
    print("reasoner: skipped — too many unsupported datatypes to relax")


def _report_relaxed(relaxed):
    if relaxed:
        names = ", ".join(_short_dt(x) for x in relaxed)
        print(f"reasoner: relaxed {len(relaxed)} unsupported datatype(s) to strings "
              f"for reasoning: {names}")


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

    s = sub.add_parser("add-disjoint"); common(s)
    s.add_argument("--classes", required=True, nargs="+", metavar="CLASS",
                   help="2 classes -> disjointWith; 3+ -> AllDisjointClasses")
    s.set_defaults(fn=cmd_add_disjoint)

    s = sub.add_parser("add-characteristic"); common(s)
    s.add_argument("--prop", required=True)
    s.add_argument("--type", required=True, choices=sorted(CHARACTERISTIC))
    s.set_defaults(fn=cmd_add_characteristic)

    s = sub.add_parser("add-inverse"); common(s)
    s.add_argument("--prop", required=True); s.add_argument("--inverse", required=True)
    s.set_defaults(fn=cmd_add_inverse)

    s = sub.add_parser("remove"); common(s); s.add_argument("--iri", required=True)
    s.set_defaults(fn=cmd_remove)

    s = sub.add_parser("remove-subclass"); common(s)
    s.add_argument("--child", required=True); s.add_argument("--parent", required=True)
    s.set_defaults(fn=cmd_remove_subclass)

    s = sub.add_parser("validate"); s.add_argument("file")
    s.add_argument("--reason", action="store_true"); s.set_defaults(fn=cmd_validate, out=None, lang=None)

    s = sub.add_parser("query"); s.add_argument("file"); s.add_argument("sparql")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_query, out=None, lang=None)

    s = sub.add_parser("diff"); s.add_argument("file"); s.add_argument("other")
    s.set_defaults(fn=cmd_diff, out=None, lang=None)
    return p


def main():
    a = build_parser().parse_args()
    g = load(a.file)
    a.fn(g, a)


if __name__ == "__main__":
    main()
