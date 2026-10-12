# AGENTS.md — AutoREST

Guidance for AI agents working in this repository.

## What this project is

AutoREST is a **DSH Skill** (Markdown instructions discovered by DSH's Skill subsystem)
that helps users generate REST electronic-structure input cards through interactive
selection panels. It is also a standalone Python CLI (`pip install -e .`).

The skill lives at `.dsh/skills/autorest/SKILL.md`. DSH discovers it automatically
when you open a project containing this directory.

**The single most important rule**: never generate an input card without asking
the user first. Always use `ask_user_question` panels.

## Repository layout

```
AutoREST/
├── .dsh/skills/autorest/        # DSH Skill — this is the core
│   ├── SKILL.md                 # YAML frontmatter + 3-step panel instructions
│   ├── references/              # REST manual, GW-BSE guide, method tables
│   └── scripts/                 # Python tools (input_gen, parser, validator...)
├── autorest/                    # Standalone Python CLI library
│   ├── core/                    # task_ir, diagnose, provenance, pipeline...
│   ├── cli.py                   # CLI entry: autorest run/pair/analyze...
│   ├── input_generator.py       # REST TOML card generation
│   ├── output_parser.py         # REST output parsing
│   ├── rest_runner.py           # REST execution + monitoring
│   ├── scientific_validator.py  # 10 scientific QA checks
│   └── gwbse_parser.py          # GW-BSE specialized parser + golden regression
├── examples/                    # Runnable examples (H2O energy, GW-BSE, acetone workflow)
├── tests/                       # Unit tests + integration tests
│   └── fixtures/                # Captured real REST output for parser tests
├── install.ps1                  # Windows skill installer
├── pyproject.toml               # pip install -e . entry
├── README.md                    # Project documentation
└── AGENTS.md                    # ← this file
```

## Hard rules

1. Never generate an input card without `ask_user_question` panels.
2. `spin` (ground-state multiplicity) ≠ `bse_spin` (excitation channel).
3. HOMO/LUMO from `Fermi Surface` separator, not energy sign.
4. REST orbital indices are 0-based.
5. Triplet oscillator strength = 0 is normal (no SOC).
6. "First 0 excitations" = Davidson failure, not "no excitations".
7. REST input cards are TOML format, not JSON.
8. `charge` and `spin` go in `[ctrl]`, not `[geom]`.
9. `empirical_dispersion` is a separate keyword (never appended to `xc`).
10. Double-hybrid/RPA methods must NOT have empirical dispersion.

## How to run things

- **Tests**: `python -m unittest discover -s tests -v` (no REST needed)
- **CLI**: `python -m autorest.cli --help`
- **Smoke example**: `python examples/water_energy.py`

## DSH Skill discovery

DSH scans these directories (highest priority first):
- Rank 100: `<project>/.dsh/skills/<name>/SKILL.md`
- Rank 200: `<project>/.agents/skills/<name>/SKILL.md`
- Rank 400: `~/.dsh/skills/<name>/SKILL.md`

No `package.json`, Cordis patch, or TypeScript compilation needed.