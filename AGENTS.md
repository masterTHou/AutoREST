# AGENTS.md — AutoREST

Guidance for AI agents working in this repository.

## What this project is

AutoREST drives the REST electronic-structure program through a verifiable
closed loop: Task IR → input generation → execution → parsing → scientific
QA → failure diagnosis/recovery → provenance → report.

**The single most important rule**: "the program finished" is not the same as
"the science is trustworthy." Never treat `Mission accomplished` as sufficient
on its own.

This project is dual-use:
- **DSH Plugin** (`package.json` + `assets/skills/autorest/`) — chat-driven, interactive Q&A
- **Python CLI** (`autorest/`) — standalone, `pip install -e .`

## Repository layout

```
AutoREST/
├── AGENTS.md                 # ← this file
├── package.json              # DSH plugin metadata
├── cordis.patch.yml          # Cordis registration
├── pyproject.toml            # pip install entry
├── lib/index.js              # DSH plugin activation
├── assets/skills/autorest/   # DSH Skill bundle
│   ├── SKILL.md              # Skill instructions (the "brain")
│   ├── references/           # REST manual, GW-BSE guide
│   ├── scripts/              # Python tools (copied from autorest/)
│   └── templates/            # Input card templates
├── autorest/                 # Python core library
│   ├── core/                 # Deterministic execution arm (LLM-free)
│   │   ├── task_ir.py        # Chemical task intermediate representation
│   │   ├── input_gen.py      # REST TOML card generation
│   │   ├── runner.py         # REST execution + monitoring
│   │   ├── parser.py         # Layered output parsing
│   │   ├── verify.py         # Scientific QA/verification
│   │   ├── diagnose.py       # Failure classification + auto-recovery
│   │   ├── provenance.py     # Hashable run records
│   │   └── report.py         # Human-readable result templates
│   ├── pipeline.py           # End-to-end closed loop
│   ├── cli.py                # CLI: autorest run/pair/golden/analyze/diagnose
│   └── skills/rest_gwbse/    # GW-BSE specific: golden data + regression
├── examples/                 # Runnable end-to-end examples
└── tests/                    # Unit tests + integration tests
    └── fixtures/             # Captured real REST output for parser tests
```

## Hard rules when editing

1. Keep ground-state spin (`spin`) separate from BSE excitation spin
   (`bse_spin`). A triplet excitation must not change a `spin=1` closed-shell
   reference.
2. HOMO/LUMO must be derived from the `Fermi Surface` separator, never from
   the sign of a QP energy.
3. REST orbital indices are 0-based internally.
4. Triplet oscillator strength of 0 is normal (no SOC), not a failure.
5. `First 0 excitations` is a Davidson/solver failure, not "no excitations".
6. Numerical solver settings and physical method settings stay separate.
7. Every run records provenance (REST version, input hash, geometry, threads, warnings).
8. The `core/` modules are deterministic, LLM-free, and well-tested. The
   LLM/skill sits above them, deciding what to submit and how to interpret
   borderline science.

## How to run things

- **Tests**: `python -m unittest discover -s tests -v` (no REST needed)
- **Integration**: `python tests/test_integration.py`
- **Smoke example**: `python examples/water_energy.py`
- **GW-BSE smoke**: `python examples/water_gwbse.py`
- **CLI**: `python -m autorest.cli --help`
- **DSH plugin**: Install `.tgz` via "插件 → 添加插件"

## Working with REST

- AutoREST invokes the resolved `rest(.exe)` path directly, not `conda run`
  (which may crash on Windows GBK encoding). The runner sets up PATH itself.
- On slow machines use `--num-threads 4`. The golden cards were generated at
  30 threads; small numerical differences across builds/thread counts are
  expected and handled by regression tolerance.
- REST input cards use TOML format. Key gotchas:
  - `charge` and `spin` go in `[ctrl]`, NOT `[geom]`
  - `empirical_dispersion` is a separate keyword (not appended to `xc`)
  - Double-hybrid/RPA methods must NOT have empirical dispersion
  - `position` uses triple-quoted strings
  - `system_name` goes in `[geom].name`

## Before submitting changes

- Run the full test suite: `python -m unittest discover -s tests -v`
- If you touch the parser, re-run parser tests against test fixtures
- If you change physical defaults, update golden regression data together
- If you add a new REST keyword, verify it against REST documentation
- Note the REST version in provenance records

## Architecture principles

The project follows a **three-layer architecture** (inspired by AIFS):

| Layer | Core responsibility | When extending |
|-------|-------------------|----------------|
| Science planning (Skill/LLM) | Understand user goals, propose computation steps, recommend methods, confirm parameters | Organize plans by actual requirements; avoid hardcoded molecule-specific workflows |
| Universal workflow (`core/`) | Save tasks/parameters, manage dependencies, waiting, invalidation, versioning, recovery | Reuse general rules; add new result type's data and checks |
| REST capability adapter | Describe REST keywords and parameter constraints, generate and validate input cards | Cross-check source code, verify with actual runs, expand coverage and tests |

## Reference

- REST: Z. Li et al., *Chin. J. Chem. Phys.* DOI: 10.1063/1674-0068/cjcp2510156
- GW-BSE in REST: Q. Gao, I. Y. Zhang, X. Xu, *J. Chem. Phys.* 164, 214116 (2026)
- Full REST manual: `assets/skills/autorest/references/rest_readme.txt`