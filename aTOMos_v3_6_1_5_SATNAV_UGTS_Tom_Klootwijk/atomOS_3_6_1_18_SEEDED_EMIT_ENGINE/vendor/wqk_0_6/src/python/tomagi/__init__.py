"""TOMAGI - Topological Operator Machine for Analytic Geometric Inference."""
from .core import Cell, Opcode, Program, State, run, step
from .format import dump, load

__all__ = ["Cell", "Opcode", "Program", "State", "run", "step", "dump", "load"]
__version__ = "1.0.0"
