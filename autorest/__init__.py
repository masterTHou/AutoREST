"""
AutoREST — AI-Driven REST Electronic Structure Automation
=========================================================

Core package providing REST input generation, execution, parsing,
scientific validation, and GW-BSE support.
"""

__version__ = "1.0.0"
__author__ = "Zhehan Tong"
__license__ = "MIT"

from .auto_rest import AutoREST
from .input_generator import InputGenerator
from .rest_runner import RestRunner, RunResult
from .output_parser import OutputParser, ParsedResult
from .scientific_validator import ScientificValidator, ValidationCheck
from .gwbse_parser import GWBSEModule, GWBSEResult, BSEState, GOLDEN_REGRESSION

__all__ = [
    "AutoREST",
    "InputGenerator",
    "RestRunner",
    "RunResult",
    "OutputParser",
    "ParsedResult",
    "ScientificValidator",
    "ValidationCheck",
    "GWBSEModule",
    "GWBSEResult",
    "BSEState",
    "GOLDEN_REGRESSION",
]
