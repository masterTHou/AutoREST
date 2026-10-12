"""
AutoREST core — Deterministic execution arm (LLM-free).

The ``core/`` subpackage provides the universal, LLM-free building blocks
for AutoREST's closed-loop pipeline: task intermediate representation,
failure diagnosis, provenance tracking, report generation, and the
end-to-end pipeline orchestrator.

All modules in this package are deterministic, well-tested, and do not
depend on any LLM or network service.
"""

from .task_ir import (
    Atom,
    CalculationTask,
    Geometry,
    MethodPlan,
    MolecularCharacter,
    ResourcePlan,
    TaskIntent,
    VerificationPlan,
)
from .diagnose import Diagnosis, FailureStage, classify
from .provenance import build_provenance, save_provenance
from .report import report
from .pipeline import PipelineResult, run_pipeline

__all__ = [
    # task_ir
    "TaskIntent",
    "MolecularCharacter",
    "Atom",
    "Geometry",
    "MethodPlan",
    "ResourcePlan",
    "VerificationPlan",
    "CalculationTask",
    # diagnose
    "FailureStage",
    "Diagnosis",
    "classify",
    # provenance
    "build_provenance",
    "save_provenance",
    # report
    "report",
    # pipeline
    "run_pipeline",
    "PipelineResult",
]