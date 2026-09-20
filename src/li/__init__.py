"""Location-intelligence package for the DICK'S DFW distribution-center study.

Modules are importable without arcpy wherever possible so that scoring,
normalization, and sensitivity logic can be unit-tested in CI (scope 6.5).
Modules that require arcpy import it lazily and say so in their docstring.
"""

__version__ = "0.1.0"
__all__ = ["config", "logging_utils", "gdb"]
