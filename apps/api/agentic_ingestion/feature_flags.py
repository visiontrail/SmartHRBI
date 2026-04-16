from __future__ import annotations

from fastapi import HTTPException


def ensure_agentic_ingestion_enabled(enabled: bool) -> None:
    if enabled:
        return
    raise HTTPException(
        status_code=404,
        detail={
            "code": "AGENTIC_INGESTION_DISABLED",
            "message": "Agentic ingestion endpoints are disabled by feature flag",
        },
    )


def ensure_legacy_dataset_upload_enabled(enabled: bool) -> None:
    if enabled:
        return
    raise HTTPException(
        status_code=404,
        detail={
            "code": "LEGACY_UPLOAD_DISABLED",
            "message": "Legacy /datasets/upload is disabled by feature flag",
        },
    )
