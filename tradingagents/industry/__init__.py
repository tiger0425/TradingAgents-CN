"""Industry classification service.

Provides a structured wrapper around get_industry() from a_stock_data,
returning IndustryResult dataclass with primary/secondary/confidence/source.
"""
from .classifier import IndustryClassifier, IndustryResult
from .frameworks import IndustryFramework
from .verifier import IndustryVerifier

__all__ = [
    "IndustryClassifier",
    "IndustryResult",
    "IndustryFramework",
    "IndustryVerifier",
]
