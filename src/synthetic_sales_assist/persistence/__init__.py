"""Local SQLite persistence surfaces for the synthetic rule-pack runtime."""

from synthetic_sales_assist.persistence.database import (
    DatabaseActivityCoordinator,
    DatabaseBusyError,
    DatabaseConfigurationError,
    DatabaseConnectionPolicy,
    DatabaseError,
    SQLiteDatabase,
)
from synthetic_sales_assist.persistence.faults import (
    FaultInjector,
    FaultPoint,
    InjectedPersistenceFault,
)
from synthetic_sales_assist.persistence.idempotency import SQLiteIdempotencyRepository
from synthetic_sales_assist.persistence.paths import (
    DataPaths,
    PathPolicyError,
    resolve_data_paths,
    validate_local_path,
)
from synthetic_sales_assist.persistence.projections import (
    ProjectionVerification,
    ProjectionVerifier,
    verify_sales_credit_projections,
)
from synthetic_sales_assist.persistence.records import (
    DurableCommandResult,
    PersistenceRecordError,
    SalesCreditPurgeResult,
    StoredSalesCreditCase,
    StoredSalesCreditEvent,
)
from synthetic_sales_assist.persistence.retention import SalesCreditRetentionService
from synthetic_sales_assist.persistence.sales_credit_repository import (
    SalesCreditPersistenceConflict,
    SalesCreditRepository,
    SalesCreditRepositoryError,
)
from synthetic_sales_assist.persistence.sales_credit_services import (
    SalesCreditPersistenceService,
)
from synthetic_sales_assist.persistence.schema import (
    DatabaseVerification,
    DatabaseVerificationError,
    MigrationReceipt,
    SchemaObject,
    migration_receipts,
    schema_inventory,
    verify_database,
)


__all__ = [
    "DataPaths",
    "DatabaseActivityCoordinator",
    "DatabaseBusyError",
    "DatabaseConfigurationError",
    "DatabaseConnectionPolicy",
    "DatabaseError",
    "DatabaseVerification",
    "DatabaseVerificationError",
    "DurableCommandResult",
    "FaultInjector",
    "FaultPoint",
    "InjectedPersistenceFault",
    "MigrationReceipt",
    "PathPolicyError",
    "PersistenceRecordError",
    "ProjectionVerification",
    "ProjectionVerifier",
    "SQLiteDatabase",
    "SQLiteIdempotencyRepository",
    "SalesCreditPersistenceConflict",
    "SalesCreditPersistenceService",
    "SalesCreditPurgeResult",
    "SalesCreditRepository",
    "SalesCreditRepositoryError",
    "SalesCreditRetentionService",
    "SchemaObject",
    "StoredSalesCreditCase",
    "StoredSalesCreditEvent",
    "migration_receipts",
    "resolve_data_paths",
    "schema_inventory",
    "validate_local_path",
    "verify_database",
    "verify_sales_credit_projections",
]
