"""Admin database models."""

from .base import (
    Base,
    BigInteger,
    Column,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    datetime,
    relationship,
)


class AdminFile(Base):
    __tablename__ = "admin_files"

    id = Column(Integer, primary_key=True, index=True)
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(80), unique=True, index=True, nullable=False)
    content_type = Column(String(120), nullable=False)
    file_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    uploader = relationship("User")


class TransferSession(Base):
    __tablename__ = "transfer_sessions"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    public_token = Column(String(128), unique=True, nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    total_bytes = Column(BigInteger, default=0, nullable=False)
    max_bytes = Column(BigInteger, default=2 * 1024**3, nullable=False)
    last_activity_at = Column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    creator = relationship("User")
    files = relationship(
        "TransferFile", back_populates="session", cascade="all, delete-orphan"
    )


class TransferFile(Base):
    __tablename__ = "transfer_files"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey("transfer_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(120), unique=True, nullable=False, index=True)
    storage_path = Column(Text, nullable=False)
    file_size = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("TransferSession", back_populates="files")


class TusUploadReservation(Base):
    """Tracks private, administrator-authorized tus uploads and their quota."""

    __tablename__ = "tus_upload_reservations"
    __table_args__ = (
        UniqueConstraint("upload_id", name="uq_tus_upload_reservation_upload_id"),
        CheckConstraint(
            "purpose IN ('admin_file', 'transfer_file')",
            name="ck_tus_upload_reservation_purpose",
        ),
        CheckConstraint(
            "status IN ('creating', 'active', 'complete', 'cancelled', 'failed')",
            name="ck_tus_upload_reservation_status",
        ),
        CheckConstraint("upload_length >= 0", name="ck_tus_upload_length_nonnegative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(String(128), nullable=True)
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose = Column(String(24), nullable=False)
    transfer_session_id = Column(
        Integer,
        ForeignKey("transfer_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_name = Column(String(255), nullable=False)
    content_type = Column(String(120), nullable=True)
    upload_length = Column(BigInteger, nullable=False)
    upload_offset = Column(BigInteger, default=0, nullable=False)
    status = Column(String(20), nullable=False, index=True)
    result_payload = Column(Text, nullable=True)
    failure_code = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity_at = Column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    expires_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)


class AdminTransferNote(Base):
    __tablename__ = "admin_transfer_notes"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False, default="")
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    updater = relationship("User")


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(80), nullable=False, index=True)
    resource_type = Column(String(80), nullable=False)
    resource_id = Column(String(128), nullable=True)
    outcome = Column(String(20), nullable=False, default="success", index=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    actor = relationship("User")


class HomepageSetting(Base):
    __tablename__ = "homepage_settings"

    id = Column(Integer, primary_key=True)
    config_json = Column(Text, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    updater = relationship("User")


class RealtimeEventAuditLog(Base):
    __tablename__ = "realtime_event_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_name = Column(String(80), nullable=False, index=True)
    room_id = Column(Integer, nullable=True, index=True)
    outcome = Column(String(20), nullable=False, default="success", index=True)
    detail = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    actor = relationship("User")
