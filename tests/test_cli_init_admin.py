"""
Unit and Integration Tests for AGGRIX Initial Platform Administrator Provisioning CLI.

Verifies:
1. Successful initial administrator creation with bcrypt password hashing.
2. Refusal of duplicate bootstrap when a platform administrator already exists.
3. Rejection of duplicate email addresses.
4. Input validation for email format and password strength (>= 8 chars, <= 72 bytes).
5. Database rollback on exception/failure.
6. Hidden password prompt handling via getpass and password mismatch detection.
7. Non-interactive standard input (--password-stdin) support.
8. Status verification mode (--check-only).
9. Absolute prevention of plaintext password exposure or logging.
"""
from __future__ import annotations

import io
import uuid
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cli.init_admin import (
    DuplicateUserError,
    InvalidCredentialsError,
    PlatformAdminAlreadyExistsError,
    check_platform_admin_exists,
    main as init_admin_main,
    prompt_credentials,
    provision_initial_platform_admin,
    validate_admin_email,
    validate_admin_password,
)
from app.core.security import verify_password
from app.database.base import Base
from app.models.tenant import Tenant
from app.models.user import User, UserRole


# ==============================================================================
# Isolated SQLite Test Fixtures
# ==============================================================================

@pytest.fixture
def cli_engine() -> Generator[sa.Engine, None, None]:
    """Isolated, thread-safe in-memory SQLite engine for CLI testing."""
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa.event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def cli_session_factory(cli_engine: sa.Engine) -> sessionmaker:
    """Session factory bound to isolated in-memory test engine."""
    return sessionmaker(bind=cli_engine, expire_on_commit=False)


@pytest.fixture
def cli_session(cli_session_factory: sessionmaker) -> Generator[Session, None, None]:
    """Yields a database session against the isolated test engine."""
    session = cli_session_factory()
    yield session
    session.close()


# ==============================================================================
# Unit Tests: Validation Functions
# ==============================================================================

class TestValidationFunctions:
    """Tests for email and password validation rules."""

    def test_validate_admin_email_valid(self):
        assert validate_admin_email("admin@aggrix.com") == "admin@aggrix.com"
        assert validate_admin_email("  ADMIN@Aggrix.COM  ") == "admin@aggrix.com"
        assert validate_admin_email("first.last+sub@domain.co.uk") == "first.last+sub@domain.co.uk"

    def test_validate_admin_email_invalid(self):
        with pytest.raises(InvalidCredentialsError, match="cannot be empty"):
            validate_admin_email("")
        with pytest.raises(InvalidCredentialsError, match="cannot be empty"):
            validate_admin_email("   ")
        with pytest.raises(InvalidCredentialsError, match="Invalid email address"):
            validate_admin_email("not-an-email")
        with pytest.raises(InvalidCredentialsError, match="Invalid email address"):
            validate_admin_email("@missinguser.com")
        with pytest.raises(InvalidCredentialsError, match="maximum length"):
            validate_admin_email("a" * 250 + "@example.com")

    def test_validate_admin_password_valid(self):
        # 8 characters or more
        validate_admin_password("password123")
        validate_admin_password("Complex#Secure@Pass2026!")

    def test_validate_admin_password_invalid(self):
        with pytest.raises(InvalidCredentialsError, match="cannot be empty"):
            validate_admin_password("")
        with pytest.raises(InvalidCredentialsError, match="at least 8 characters"):
            validate_admin_password("short")
        with pytest.raises(InvalidCredentialsError, match="at least 8 characters"):
            validate_admin_password("1234567")
        with pytest.raises(InvalidCredentialsError, match="exceeds 72 bytes"):
            validate_admin_password("a" * 73)


# ==============================================================================
# Unit & Integration Tests: Provisioning Logic
# ==============================================================================

class TestProvisionInitialPlatformAdmin:
    """Tests for provision_initial_platform_admin core function."""

    def test_check_platform_admin_exists_empty_and_populated(self, cli_session: Session):
        # 1. Initially no users exist
        assert check_platform_admin_exists(cli_session) is False

        # 2. Add tenant user - check should still return False
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Test Store",
            domain="test-store.myshopify.com",
            timezone="UTC",
        )
        cli_session.add(tenant)
        tenant_user = User(
            id=uuid.uuid4(),
            email="tenant@test.com",
            hashed_password="dummy_hashed_password",
            role=UserRole.TENANT_USER.value,
            tenant_id=tenant.id,
            is_active=True,
        )
        cli_session.add(tenant_user)
        cli_session.commit()

        assert check_platform_admin_exists(cli_session) is False

        # 3. Add platform admin - check should now return True
        admin = User(
            id=uuid.uuid4(),
            email="admin@test.com",
            hashed_password="dummy_hashed_password",
            role=UserRole.PLATFORM_ADMIN.value,
            is_active=True,
        )
        cli_session.add(admin)
        cli_session.commit()

        assert check_platform_admin_exists(cli_session) is True

    def test_successful_platform_admin_creation(self, cli_session: Session):
        email = "FirstAdmin@Aggrix.COM"
        password = "SuperSecurePassword123!"
        full_name = "Master Administrator"

        user = provision_initial_platform_admin(
            session=cli_session,
            email=email,
            password=password,
            full_name=full_name,
            commit=True,
        )

        assert user.id is not None
        assert user.email == "firstadmin@aggrix.com"
        assert user.full_name == "Master Administrator"
        assert user.role == UserRole.PLATFORM_ADMIN.value
        assert user.is_active is True
        assert user.tenant_id is None

        # Verify password is encrypted with bcrypt and verify_password works
        assert user.hashed_password != password
        assert user.hashed_password.startswith("$2b$") or user.hashed_password.startswith("$2a$")
        assert verify_password(password, user.hashed_password) is True
        assert verify_password("WrongPassword!", user.hashed_password) is False

    def test_refuse_duplicate_bootstrap_when_admin_exists(self, cli_session: Session):
        # Create first admin
        provision_initial_platform_admin(
            session=cli_session,
            email="admin1@aggrix.com",
            password="Password123456!",
            commit=True,
        )

        # Attempt to create second admin via CLI bootstrap
        with pytest.raises(PlatformAdminAlreadyExistsError, match="A platform administrator already exists"):
            provision_initial_platform_admin(
                session=cli_session,
                email="admin2@aggrix.com",
                password="Password123456!",
                commit=True,
            )

        # Confirm only 1 admin remains in database
        admins = cli_session.execute(
            sa.select(User).where(User.role == UserRole.PLATFORM_ADMIN.value)
        ).scalars().all()
        assert len(admins) == 1
        assert admins[0].email == "admin1@aggrix.com"

    def test_refuse_duplicate_email(self, cli_session: Session):
        # Add a tenant user with email staff@aggrix.com
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Test Store",
            domain="test-store.myshopify.com",
            timezone="UTC",
        )
        cli_session.add(tenant)
        existing_user = User(
            id=uuid.uuid4(),
            email="staff@aggrix.com",
            hashed_password="some_hashed_password",
            role=UserRole.TENANT_USER.value,
            tenant_id=tenant.id,
            is_active=True,
        )
        cli_session.add(existing_user)
        cli_session.commit()

        # Attempt to provision platform admin with same email
        with pytest.raises(DuplicateUserError, match="already exists"):
            provision_initial_platform_admin(
                session=cli_session,
                email="staff@aggrix.com",
                password="Password123456!",
                commit=True,
            )

    def test_database_rollback_on_commit_failure(self, cli_session: Session):
        # Mock commit to simulate a database failure during commit
        mock_session = MagicMock(wraps=cli_session)
        mock_session.commit.side_effect = sa.exc.OperationalError(
            statement="COMMIT", params={}, orig=Exception("Disk I/O failure")
        )

        with pytest.raises(sa.exc.OperationalError):
            provision_initial_platform_admin(
                session=mock_session,
                email="admin@test.com",
                password="Password123456!",
                commit=True,
            )

        # Verify rollback was called on mock session
        mock_session.rollback.assert_called_once()


# ==============================================================================
# CLI Entry Point & Command Tests
# ==============================================================================

class TestCLIInteractiveAndHeadless:
    """Tests for main() CLI entrypoint, argument parsing, prompts, and output."""

    def test_cli_interactive_success(self, cli_session_factory: sessionmaker):
        # Mock inputs: email, full_name, password, confirm_password
        mock_inputs = iter(["admin@test.com", "Chief Admin"])
        mock_passwords = iter(["SuperPass123456!", "SuperPass123456!"])

        out = io.StringIO()
        err = io.StringIO()

        exit_code = init_admin_main(
            argv=[],
            session_factory=cli_session_factory,
            input_func=lambda prompt: next(mock_inputs),
            getpass_func=lambda prompt: next(mock_passwords),
            out=out,
            err=err,
        )

        assert exit_code == 0
        output = out.getvalue()
        assert "AGGRIX Platform Administrator Initialized Successfully" in output
        assert "Email:      admin@test.com" in output
        assert "Full Name:  Chief Admin" in output
        assert "Role:       platform_admin" in output
        assert "Active" in output

        # Ensure plaintext password is NEVER leaked in output
        assert "SuperPass123456!" not in output
        assert "SuperPass123456!" not in err.getvalue()

    def test_cli_password_mismatch(self, cli_session_factory: sessionmaker):
        mock_inputs = iter(["admin@test.com", "Chief Admin"])
        mock_passwords = iter(["Password123!", "DifferentPassword123!"])

        out = io.StringIO()
        err = io.StringIO()

        exit_code = init_admin_main(
            argv=[],
            session_factory=cli_session_factory,
            input_func=lambda prompt: next(mock_inputs),
            getpass_func=lambda prompt: next(mock_passwords),
            out=out,
            err=err,
        )

        assert exit_code == 1
        assert "Passwords do not match" in err.getvalue()

    def test_cli_refuse_duplicate_bootstrap(self, cli_session_factory: sessionmaker):
        # 1. Create first admin
        with cli_session_factory() as sess:
            provision_initial_platform_admin(
                session=sess,
                email="admin1@test.com",
                password="Password123456!",
                commit=True,
            )

        # 2. Attempt second creation through CLI
        out = io.StringIO()
        err = io.StringIO()

        exit_code = init_admin_main(
            argv=["--email", "admin2@test.com"],
            session_factory=cli_session_factory,
            out=out,
            err=err,
        )

        assert exit_code == 2
        assert "A platform administrator already exists in the database" in err.getvalue()

    def test_cli_invalid_email_argument(self, cli_session_factory: sessionmaker):
        mock_passwords = iter(["SuperPass123456!", "SuperPass123456!"])
        out = io.StringIO()
        err = io.StringIO()

        exit_code = init_admin_main(
            argv=["--email", "invalid-email-address"],
            session_factory=cli_session_factory,
            getpass_func=lambda prompt: next(mock_passwords),
            out=out,
            err=err,
        )

        assert exit_code == 1
        assert "Invalid email address" in err.getvalue()

    def test_cli_password_too_short(self, cli_session_factory: sessionmaker):
        mock_passwords = iter(["short", "short"])
        out = io.StringIO()
        err = io.StringIO()

        exit_code = init_admin_main(
            argv=["--email", "valid@test.com"],
            session_factory=cli_session_factory,
            getpass_func=lambda prompt: next(mock_passwords),
            out=out,
            err=err,
        )

        assert exit_code == 1
        assert "at least 8 characters long" in err.getvalue()

    def test_cli_stdin_password_mode(self, cli_session_factory: sessionmaker):
        out = io.StringIO()
        err = io.StringIO()

        with patch("sys.stdin", io.StringIO("AutomatedPassword123!\n")):
            exit_code = init_admin_main(
                argv=["--email", "stdin_admin@test.com", "--password-stdin", "--full-name", "CI Admin"],
                session_factory=cli_session_factory,
                out=out,
                err=err,
            )

        assert exit_code == 0
        assert "AGGRIX Platform Administrator Initialized Successfully" in out.getvalue()
        assert "stdin_admin@test.com" in out.getvalue()
        assert "AutomatedPassword123!" not in out.getvalue()

    def test_cli_check_only_flag(self, cli_session_factory: sessionmaker):
        out = io.StringIO()
        err = io.StringIO()

        # 1. No admin -> exit code 0
        exit_code = init_admin_main(
            argv=["--check-only"],
            session_factory=cli_session_factory,
            out=out,
            err=err,
        )
        assert exit_code == 0
        assert "No platform administrator exists" in out.getvalue()

        # 2. Create an admin
        with cli_session_factory() as sess:
            provision_initial_platform_admin(
                session=sess,
                email="admin@test.com",
                password="Password123456!",
                commit=True,
            )

        # 3. Check again -> exit code 2
        out2 = io.StringIO()
        err2 = io.StringIO()
        exit_code = init_admin_main(
            argv=["--check-only"],
            session_factory=cli_session_factory,
            out=out2,
            err=err2,
        )
        assert exit_code == 2
        assert "Platform administrator already exists" in out2.getvalue()


class TestCLIMainDispatcher:
    """Tests for top-level python -m app.cli dispatcher."""

    def test_top_level_cli_help(self):
        from app.cli.__main__ import main as root_cli_main
        with patch("sys.argv", ["app.cli", "--help"]):
            with pytest.raises(SystemExit) as exc:
                root_cli_main()
            assert exc.value.code == 0

    def test_top_level_cli_dispatch_init_admin(self):
        from app.cli.__main__ import main as root_cli_main
        with patch("sys.argv", ["app.cli", "init-admin", "--check-only"]):
            with patch("app.cli.__main__.init_admin_main") as mock_init:
                mock_init.return_value = 0
                code = root_cli_main()
                assert code == 0
                mock_init.assert_called_once_with(["--check-only"])

