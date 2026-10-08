"""ORM models. Import all modules here so Alembic sees the full metadata."""

from kontor.models.account import AuthSession, Household, Person, User
from kontor.models.actuals import ActualValue, DepotTransaction
from kontor.models.asset import Asset, AssetKind
from kontor.models.cashflow import (
    AuditLog,
    CashflowItem,
    CashflowVersion,
    Category,
    CategoryKind,
    Frequency,
)
from kontor.models.catalog import CatalogEntry
from kontor.models.depot import Instrument, InstrumentKind, OneOffPayment, SavingsRate, TaxSettings
from kontor.models.financing import Financing, FinancingEvent, FinancingKind
from kontor.models.property import Property, PropertyUsage, PropertyWork

__all__ = [
    "ActualValue",
    "Asset",
    "AssetKind",
    "AuditLog",
    "AuthSession",
    "CashflowItem",
    "CashflowVersion",
    "CatalogEntry",
    "Category",
    "CategoryKind",
    "DepotTransaction",
    "Financing",
    "FinancingEvent",
    "FinancingKind",
    "Frequency",
    "Household",
    "Instrument",
    "InstrumentKind",
    "OneOffPayment",
    "Person",
    "Property",
    "PropertyUsage",
    "PropertyWork",
    "SavingsRate",
    "TaxSettings",
    "User",
]
