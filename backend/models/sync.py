"""Sync database models."""

from .base import (
    Base,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    datetime,
    relationship,
)


class SyncDevice(Base):
    __tablename__ = "sync_devices"
    __table_args__ = (
        UniqueConstraint("device_token_hash", name="uq_sync_device_token_hash"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    device_token_hash = Column(String(64), index=True, nullable=False)
    token_hint = Column(String(12), nullable=False)
    token_expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    rotated_at = Column(DateTime, nullable=True)
    root_name = Column(String(100), default="Public", nullable=False)
    status = Column(String(20), default="offline", nullable=False)
    is_paused = Column(Boolean, default=False, nullable=False)
    scan_requested = Column(Boolean, default=False, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SyncFile(Base):
    __tablename__ = "sync_files"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "relative_path",
            name="uq_sync_file_device_path",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("sync_devices.id"), nullable=False)
    relative_path = Column(String(1000), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    sha256 = Column(String(64), nullable=True)
    mtime = Column(DateTime, nullable=True)
    sync_status = Column(String(20), default="synced", nullable=False)
    bytes_transferred = Column(Integer, default=0, nullable=False)
    expected_size = Column(Integer, default=0, nullable=False)
    progress_percent = Column(Integer, default=100, nullable=False)
    storage_path = Column(Text, nullable=True)
    last_synced_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    device = relationship("SyncDevice")


class SyncUpload(Base):
    __tablename__ = "sync_uploads"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "upload_id",
            name="uq_sync_upload_device_upload_id",
        ),
        CheckConstraint("expected_size >= 0", name="ck_sync_upload_expected_size"),
        CheckConstraint("total_chunks > 0", name="ck_sync_upload_total_chunks"),
        CheckConstraint("received_chunks >= 0", name="ck_sync_upload_received_chunks"),
        CheckConstraint("received_bytes >= 0", name="ck_sync_upload_received_bytes"),
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(
        Integer,
        ForeignKey("sync_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    upload_id = Column(String(64), nullable=False)
    relative_path = Column(String(1000), nullable=False)
    expected_size = Column(BigInteger, nullable=False)
    expected_sha256 = Column(String(64), nullable=True)
    total_chunks = Column(Integer, nullable=False)
    received_chunks = Column(Integer, default=0, nullable=False)
    received_chunks_json = Column(Text, default="[]", nullable=False)
    received_bytes = Column(BigInteger, default=0, nullable=False)
    status = Column(String(20), default="uploading", nullable=False, index=True)
    temp_path = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    device = relationship("SyncDevice")


class SyncEvent(Base):
    __tablename__ = "sync_events"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("sync_devices.id"), nullable=False)
    relative_path = Column(String(1000), nullable=True)
    event_type = Column(String(30), nullable=False)
    status = Column(String(20), default="completed", nullable=False)
    message = Column(Text, nullable=True)
    bytes_transferred = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    device = relationship("SyncDevice")
