#!/usr/bin/env python3
"""Offline smoke test for onto.py (no live WebProtégé needed).

Run with the project venv:  .venv/bin/python test/onto_test.py
Asserts the anti-hallucination guard, add/remove deltas, IRI preservation, validate.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap

ONTO = pathlib.Path(__file__).resolve().parent.parent / "onto.py"
PY = sys.executable
SAMPLE = textwrap.dedent("""\
    @prefix : <http://example.org/t#> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    <http://example.org/t> a owl:Ontology .
    :A a owl:Class .
    :B a owl:Class ; rdfs:subClassOf :A .
""")

passed = failed = 0


def check(label, cond):
    global passed, failed
    print(("  ok   " if cond else "  FAIL ") + label)
    passed += cond
    failed += not cond


def run(f, *args, expect=0):
    r = subprocess.run([PY, str(ONTO), args[0], f, *args[1:]], capture_output=True, text=True)
    check(f"exit {r.returncode}=={expect}: {' '.join(args)}", r.returncode == expect)
    return r


def main():
    d = tempfile.mkdtemp()
    f = os.path.join(d, "t.ttl")
    with open(f, "w") as fh:
        fh.write(SAMPLE)

    # anti-hallucination: referencing a non-existent parent must be refused, file untouched
    run(f, "add-subclass", "--child", ":B", "--parent", ":Ghost", expect=1)
    check("Ghost not written", "Ghost" not in open(f).read())

    # add a class under an existing parent
    run(f, "add-class", "--iri", ":C", "--label", "Cee", "--parent", ":A")
    body = open(f).read()
    check(":C added", ":C" in body and "subClassOf :A" in body)

    # ontology IRI preserved
    check("IRI preserved", "<http://example.org/t>" in body and "owl:Ontology" in body)

    # remove it again ("Cee" is the unique label; avoid ":C" which is a substring of "owl:Class")
    run(f, "remove", "--iri", ":C")
    check(":C removed", "Cee" not in open(f).read() and ":C " not in open(f).read())

    # axiom commands: add-characteristic / add-disjoint / add-inverse
    run(f, "add-objprop", "--iri", ":rel", "--domain", ":A", "--range", ":A")
    run(f, "add-characteristic", "--prop", ":rel", "--type", "transitive")
    check("characteristic written", "owl:TransitiveProperty" in open(f).read())
    run(f, "add-characteristic", "--prop", ":ghostProp", "--type", "functional", expect=1)
    run(f, "add-characteristic", "--prop", ":rel", "--type", "functional")  # functional ok on objprop
    run(f, "add-class", "--iri", ":D", "--label", "Dee")
    run(f, "add-disjoint", "--classes", ":A", ":D")
    check("pairwise disjointWith written", "owl:disjointWith" in open(f).read())
    run(f, "add-disjoint", "--classes", ":A", ":B", ":D")
    check("AllDisjointClasses written", "AllDisjointClasses" in open(f).read())
    r = run(f, "add-disjoint", "--classes", ":D", ":A", ":B")  # reordered -> idempotent
    check("AllDisjointClasses idempotent", "no change" in r.stdout)
    run(f, "add-inverse", "--prop", ":rel", "--inverse", ":ghostRel", expect=1)  # inverse must exist

    # validate clean
    run(f, "validate")

    # Issue #8 regression: WebProtégé export mangles "@"-bearing literals into bogus
    # language tags ("user@dept.edu" -> "user"@dept.edu). The load sanitizer must repair
    # BOTH the simple case AND the embedded case, where the original text continues past
    # the bogus tag ("...bob-x"@e.ntu.edu.sg, NPGS ok).) — that trailing run must be pulled
    # back inside the quotes or the stray ", NPGS ..." parses as a Turtle objectList and dies.
    mf = os.path.join(d, "mangled.ttl")
    with open(mf, "w") as fh:
        fh.write(textwrap.dedent("""\
            @prefix : <http://example.org/t#> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            <http://example.org/t> a owl:Ontology .
            :A a owl:Class .
            :note a owl:AnnotationProperty .
            :i a owl:NamedIndividual, :A ;
               :note "ping alice"@dept.edu ;
               :note "MMLab recruiting bob-x"@e.ntu.edu.sg, NPGS ok). .
        """))
    r = run(mf, "info")  # must parse (exit 0) despite both mangled shapes
    check("sanitizer repaired both mangled literals", "repaired 2" in r.stderr)
    r = run(mf, "query", "SELECT ?n WHERE { ?s <http://example.org/t#note> ?n }")
    check("simple email rejoined", "ping alice@dept.edu" in r.stdout)
    check("embedded email + trailing rejoined", "bob-x@e.ntu.edu.sg, NPGS ok)." in r.stdout)

    # S2: validate --reason must not abort on a datatype outside the OWL 2 map
    # (xsd:gYear). The reasoner needs Java; skip cleanly if it's unavailable.
    if shutil.which("java"):
        gy = os.path.join(d, "gy.ttl")
        with open(gy, "w") as fh:
            fh.write(SAMPLE + textwrap.dedent("""\
                @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
                :born a owl:DatatypeProperty ; rdfs:range xsd:gYear .
                :x a owl:NamedIndividual, :A ; :born "1990"^^xsd:gYear .
            """))
        r = run(gy, "validate", "--reason")
        check("reason: relaxed gYear (no abort)", "relaxed" in r.stdout and "gYear" in r.stdout)
        check("reason: ran consistency check", "consistent" in r.stdout)
    else:
        print("  skip  validate --reason (no java)")

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
