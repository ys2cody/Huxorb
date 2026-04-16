"""
Dashboard Module
================
Terminal UI, alerts, and trade export for Huxorb Pro.

Components:
- display: Rich-based terminal dashboard
- alerts: Event-driven alert system (console + optional webhook)
- exporter: CSV/JSON trade journal export
"""

from core.dashboard.display import PortfolioDashboard
from core.dashboard.alerts import AlertManager, AlertLevel, Alert
from core.dashboard.exporter import TradeExporter

__all__ = [
    "PortfolioDashboard",
    "AlertManager",
    "AlertLevel",
    "Alert",
    "TradeExporter",
]
