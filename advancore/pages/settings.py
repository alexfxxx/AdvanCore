"""Local application readiness and owner-triggered backup controls."""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from advancore.config import APP_NAME, APP_VERSION
from advancore.services.local_backup_service import (
    BackupInventory,
    LocalBackupService,
)
from advancore.services.readiness_service import ReadinessService
from advancore.services.recovery_evidence_service import RecoveryEvidenceService


def _readiness_service() -> ReadinessService:
    load_dotenv()
    database_configured = bool(os.getenv("DATABASE_URL"))
    if not database_configured:
        return ReadinessService(False)

    try:
        from advancore.services.database import test_database_connection
    except Exception:
        return ReadinessService(True)

    return ReadinessService(True, test_database_connection)


def _local_backup_service() -> LocalBackupService | None:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    repository_root = Path(__file__).resolve().parents[2]
    configured_directory = os.getenv("ADVANCORE_BACKUP_DIR")
    backup_directory = Path(configured_directory) if configured_directory else None
    return LocalBackupService(repository_root, database_url, backup_directory)


def _recovery_evidence_service() -> RecoveryEvidenceService:
    return RecoveryEvidenceService(Path(__file__).resolve().parents[2])


def _format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("bytes", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            precision = 0 if unit == "bytes" else 1
            return f"{amount:.{precision}f} {unit}"
        amount /= 1024
    return f"{amount:.1f} GB"


def _render_backup_inventory(inventory: BackupInventory) -> None:
    if not inventory.records:
        st.info("No valid local backup is available yet.")
    else:
        latest = inventory.records[0]
        created = latest.created_at.strftime("%Y-%m-%d %H:%M UTC")
        st.success(f"Latest valid local backup: {created}.")
        st.write(f"Verified backup files: {len(inventory.records)}")
        st.write(f"Local backup storage used: {_format_bytes(inventory.total_size_bytes)}")
    if inventory.invalid_entries:
        st.warning(
            "Some local backup entries are incomplete or invalid. They were not "
            "treated as recoverable backups."
        )


def _render_recovery_evidence(inventory: BackupInventory) -> None:
    try:
        evidence = _recovery_evidence_service().load()
    except Exception:
        st.warning(
            "Saved recovery rehearsal evidence is invalid or unavailable. "
            "Do not treat recovery as proven."
        )
        return
    if evidence is None:
        st.info("No saved disposable recovery rehearsal evidence is available yet.")
        return
    completed = evidence.completed_at.strftime("%Y-%m-%d %H:%M UTC")
    latest = inventory.records[0] if inventory.records else None
    if latest is not None and latest.backup_id == evidence.backup_id:
        st.success(
            "Latest valid backup passed a disposable recovery rehearsal at "
            f"{completed}; cleanup was confirmed."
        )
    else:
        st.warning(
            "A disposable recovery rehearsal passed at "
            f"{completed}, but it does not prove the latest valid backup."
        )
    st.caption(
        f"Recovery evidence: migration {evidence.migration_head}; "
        f"{evidence.required_table_count} required tables checked."
    )


def _render_local_backups() -> None:
    st.subheader("Local backup and recovery readiness")
    st.write(
        "Create and verify an owner-only PostgreSQL backup on this Mac. "
        "This page cannot restore or overwrite the saved database."
    )
    try:
        service = _local_backup_service()
    except Exception:
        service = None
        st.error("Local backup configuration is unavailable.")
    if service is None:
        st.warning("Configure the local database before creating a backup.")
        return

    try:
        inventory = service.get_inventory()
    except Exception:
        st.error("Local backup status could not be checked.")
        return
    _render_backup_inventory(inventory)
    _render_recovery_evidence(inventory)

    create_column, verify_column = st.columns(2)
    create_requested = create_column.button(
        "Create and verify local backup",
        key="settings_create_local_backup",
    )
    verify_requested = verify_column.button(
        "Verify latest local backup",
        key="settings_verify_local_backup",
        disabled=not inventory.records,
    )
    if create_requested:
        try:
            with st.spinner("Creating and verifying local backup..."):
                record = service.create_backup()
        except Exception:
            st.error("Local backup could not be created. No partial backup was kept.")
        else:
            st.success(
                "Local backup created and verified at "
                f"{record.created_at.strftime('%Y-%m-%d %H:%M UTC')}."
            )
    elif verify_requested:
        try:
            with st.spinner("Verifying latest local backup..."):
                record = service.verify_latest()
        except Exception:
            st.error("The latest local backup could not be verified.")
        else:
            st.success(
                "Latest local backup verified at "
                f"{record.created_at.strftime('%Y-%m-%d %H:%M UTC')}."
            )
    st.caption(
        "Backups stay local. Only a cleanup-confirmed disposable rehearsal for "
        "the same backup counts as recovery evidence."
    )


def render():
    st.header("Settings")
    st.write("Local setup status and safe backup controls. No credentials are shown.")

    st.subheader("Application")
    st.write(f"Name: {APP_NAME}")
    st.write(f"Version: {APP_VERSION}")

    st.subheader("Database")
    with st.spinner("Checking local readiness..."):
        summary = _readiness_service().get_summary()

    if not summary.database_configured:
        st.warning(
            "Database is not configured. Follow the Local quick start in README.md."
        )
    elif summary.database_available:
        st.success("Database is configured and available.")
    else:
        st.error(
            "Database is configured but unavailable. Check that the local database "
            "is running, then try again."
        )

    st.caption("Configuration remains file- and environment-managed.")
    _render_local_backups()
