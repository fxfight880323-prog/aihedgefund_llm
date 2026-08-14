"""AI Investment Fund Framework — a LangGraph-powered hedge fund engine.

Architecture:
    FUND      = capital slices over STRATEGIES   (master risk on the netted book)
    STRATEGY  = a blend policy over MODELS       (a "pod")
    MODEL     = an alpha model -> Signal         (conviction + thesis)

Flow:
    Data (PIT) -> Alpha Models -> Portfolio -> Risk -> Execution -> Ledger

Built with LangGraph for workflow orchestration. Every component is
pluggable — implement the interface and it drops in.
"""

__version__ = "0.1.0"
