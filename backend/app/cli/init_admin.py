"""
AGGRIX Platform Administrator Initial Provisioning CLI.

One-time secure bootstrap tool to initialize the first platform administrator
account for a fresh AGGRIX deployment.

Features:
- Enforces strict one-time bootstrap: refuses execution if any platform_admin already exists.
- Secure interactive prompts using getpass (hidden password entry).
- Cryptographic password hashing via bcrypt (12 salt rounds) using app.core.security.hash_password.
- Strict email and password validation (format, length, bcrypt limits).
- Transactional database execution with automatic rollback on error.
- Zero plaintext password persistence and zero credential exposure in logs or terminal output.

Usage:
    # Interactive mode (prompts for email, full name, and hidden password):
    python -m app.cli.init_admin

    # Providing email as argument (prompts for hidden password):
    python -m app.cli.init_admin --email admin@aggrix.com --full-name "System Administrator"

    # Headless / automation mode (reads password from stdin):
    echo "SecurePassword123!" | python -m app.cli.init_admin --email admin@aggrix.com --password-stdin

    # Check whether an initial admin is needed:
    python -m app.cli.init_admin --check-only
"""
from __future__ import annotations

import argparse
import getpass
import sys
import uuid
from pathlib import Path
from typing import Callable, Optional, TextIO

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

# Ensure backend directory is in sys.path when executed directly as a script
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.security import hash_password
from app.database.connection import get_db_session
from app.models.user import User, UserRole


# ==============================================================================
# Custom Exceptions
# ==============================================================================

class AdminProvisioningError(Exception):
    """Base exception for administrator provisioning errors."""


class PlatformAdminAlreadyExistsError(AdminProvisioningError):
    """Raised when an initial platform admin bootstrap is attempted but an admin already exists."""


class InvalidCredentialsError(AdminProvisioningError):
    """Raised when provided credentials fail validation constraints."""


class DuplicateUserError(AdminProvisioningError):
    """Raised when a user with the specified email address already exists."""


# ==============================================================================
# Validation Functions
# ==============================================================================

def validate_admin_email(email: str) -> str:
    """
    Validate and normalize email address.

    Constraints:
    - Non-empty, non-whitespace.
    - Maximum 255 characters (DB column limit).
    - Valid RFC 5322 email syntax.

    Returns:
        Normalized lowercase email string.

    Raises:
        InvalidCredentialsError: If email is invalid.
    """
    if not email or not email.strip():
        raise InvalidCredentialsError("Email address cannot be empty.")

    cleaned = email.strip()
    if len(cleaned) > 255:
        raise InvalidCredentialsError("Email address exceeds maximum length of 255 characters.")

    try:
        valid = validate_email(cleaned, check_deliverability=False)
        return valid.normalized.lower()
    except EmailNotValidError as exc:
        raise InvalidCredentialsError(f"Invalid email address '{cleaned}': {str(exc)}") from exc


def validate_admin_password(password: str) -> None:
    """
    Validate password strength and technical constraints.

    Constraints:
    - Non-empty.
    - Minimum 8 characters (matches API schema and security baseline).
    - Maximum 72 bytes (Bcrypt algorithm hard limit).

    Raises:
        InvalidCredentialsError: If password validation fails.
    """
    if not password:
        raise InvalidCredentialsError("Password cannot be empty.")

    if len(password) < 8:
        raise InvalidCredentialsError("Password must be at least 8 characters long.")

    if len(password.encode("utf-8")) > 72:
        raise InvalidCredentialsError(
            "Password exceeds 72 bytes, which is the maximum supported length for bcrypt hashing."
        )


def check_platform_admin_exists(session: Session) -> bool:
    """
    Check whether any user with role 'platform_admin' already exists.

    Returns:
        True if at least one platform_admin exists, False otherwise.
    """
    stmt = select(func.count(User.id)).where(User.role == UserRole.PLATFORM_ADMIN.value)
    count = session.execute(stmt).scalar_one()
    return count > 0


# ==============================================================================
# Core Provisioning Logic
# ==============================================================================

def provision_initial_platform_admin(
    session: Session,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    commit: bool = True,
) -> User:
    """
    Safely provisions the initial platform administrator account.

    Guarantees:
    - Fails if any platform administrator already exists in the database.
    - Validates email syntax and password technical constraints.
    - Hashes password using bcrypt (12 salt rounds) via app.core.security.hash_password.
    - Never stores plaintext passwords.
    - Refuses to overwrite or duplicate existing user emails.
    - Transactional: rolls back changes if an exception occurs during commit.

    Args:
        session: Active SQLAlchemy database session.
        email: Administrator email address.
        password: Plaintext password (validated and immediately hashed).
        full_name: Optional display name.
        commit: Whether to commit the transaction. Defaults to True.

    Returns:
        User: Created User instance with role=platform_admin.

    Raises:
        PlatformAdminAlreadyExistsError: If a platform administrator already exists.
        DuplicateUserError: If a user with the email already exists.
        InvalidCredentialsError: If email or password validation fails.
    """
    # 1. Enforce strict single-bootstrap rule
    if check_platform_admin_exists(session):
        raise PlatformAdminAlreadyExistsError(
            "A platform administrator already exists in the system. "
            "Initial CLI bootstrap is restricted to one-time initialization. "
            "Subsequent administrators must be provisioned by an existing "
            "platform administrator via POST /api/v1/auth/provision."
        )

    # 2. Validate email and password
    normalized_email = validate_admin_email(email)
    validate_admin_password(password)

    # 3. Check for existing user with identical email
    existing_user = session.execute(
        select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()
    if existing_user:
        raise DuplicateUserError(
            f"User with email '{normalized_email}' already exists in the database."
        )

    # 4. Hash password using bcrypt (12 rounds) via core security helper
    hashed = hash_password(password)

    # 5. Instantiate user model with platform_admin role
    admin_user = User(
        id=uuid.uuid4(),
        email=normalized_email,
        hashed_password=hashed,
        full_name=full_name.strip() if full_name and full_name.strip() else None,
        role=UserRole.PLATFORM_ADMIN.value,
        is_active=True,
        tenant_id=None,
    )

    try:
        session.add(admin_user)
        if commit:
            session.commit()
            session.refresh(admin_user)
        else:
            session.flush()
    except Exception:
        if commit:
            session.rollback()
        raise

    return admin_user


# ==============================================================================
# Interactive Prompts & CLI Interface
# ==============================================================================

def prompt_credentials(
    email_arg: Optional[str] = None,
    full_name_arg: Optional[str] = None,
    password_stdin: bool = False,
    input_func: Callable[[str], str] = input,
    getpass_func: Callable[[str], str] = getpass.getpass,
) -> tuple[str, str, Optional[str]]:
    """
    Prompt user for administrative credentials securely.

    Args:
        email_arg: Email passed via CLI flag.
        full_name_arg: Full name passed via CLI flag.
        password_stdin: If True, reads password from standard input.
        input_func: Callable for reading text input (defaults to builtin input).
        getpass_func: Callable for hidden password input (defaults to getpass.getpass).

    Returns:
        tuple[str, str, Optional[str]]: (email, password, full_name)
    """
    # 1. Email
    if email_arg:
        email = email_arg.strip()
    else:
        email = input_func("Enter platform administrator email: ").strip()

    # 2. Full Name (optional)
    if full_name_arg is not None:
        full_name = full_name_arg.strip() or None
    elif email_arg is not None:
        # If email is supplied via flag, default full_name to None without prompt
        full_name = None
    else:
        name_input = input_func("Enter full name (optional, press Enter to skip): ").strip()
        full_name = name_input if name_input else None

    # 3. Password
    if password_stdin:
        line = sys.stdin.readline()
        password = line.rstrip("\r\n")
        if not password:
            raise InvalidCredentialsError("Empty password provided via stdin.")
    else:
        password = getpass_func("Enter administrator password: ")
        confirm_password = getpass_func("Confirm administrator password: ")
        if password != confirm_password:
            raise InvalidCredentialsError("Passwords do not match.")

    return email, password, full_name


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI options for admin initialization."""
    parser = argparse.ArgumentParser(
        description="AGGRIX Initial Platform Administrator Provisioning CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Email address for the initial platform administrator (prompts if omitted)",
    )
    parser.add_argument(
        "--full-name",
        type=str,
        default=None,
        help="Display name for the administrator (optional)",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        default=False,
        help="Read password from stdin instead of interactive hidden prompt",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        default=False,
        help="Check whether a platform administrator already exists without creating one",
    )
    return parser.parse_args(args)


def main(
    argv: Optional[list[str]] = None,
    session_factory: Optional[sessionmaker[Session]] = None,
    input_func: Callable[[str], str] = input,
    getpass_func: Callable[[str], str] = getpass.getpass,
    out: Optional[TextIO] = None,
    err: Optional[TextIO] = None,
) -> int:
    """
    Main entry point for the platform admin provisioning CLI.

    Exit Codes:
    - 0: Success (or check-only confirmed admin exists/does not exist cleanly)
    - 1: Invalid input, validation failure, or database error
    - 2: Platform administrator already exists (bootstrap refused)
    """
    stdout = out or sys.stdout
    stderr = err or sys.stderr

    args = parse_args(argv)

    try:
        with get_db_session(session_factory) as session:
            # Handle --check-only flag
            if args.check_only:
                admin_exists = check_platform_admin_exists(session)
                if admin_exists:
                    stdout.write("Status: Platform administrator already exists. Bootstrap is disabled.\n")
                    return 2
                else:
                    stdout.write("Status: No platform administrator exists. Ready for initial bootstrap.\n")
                    return 0

            # Check if admin already exists before prompting
            if check_platform_admin_exists(session):
                stderr.write(
                    "ERROR: A platform administrator already exists in the database.\n"
                    "Initial provisioning is strictly one-time. Refusing to create another administrator.\n"
                    "To provision additional accounts, use the authenticated API: POST /api/v1/auth/provision\n"
                )
                return 2

            # Prompt for credentials
            try:
                email, password, full_name = prompt_credentials(
                    email_arg=args.email,
                    full_name_arg=args.full_name,
                    password_stdin=args.password_stdin,
                    input_func=input_func,
                    getpass_func=getpass_func,
                )
            except InvalidCredentialsError as cred_err:
                stderr.write(f"ERROR: {cred_err}\n")
                return 1

            # Execute safe provisioning
            admin_user = provision_initial_platform_admin(
                session=session,
                email=email,
                password=password,
                full_name=full_name,
                commit=True,
            )

            stdout.write(
                "\n"
                "============================================================\n"
                "AGGRIX Platform Administrator Initialized Successfully\n"
                "============================================================\n"
                f"User ID:    {admin_user.id}\n"
                f"Email:      {admin_user.email}\n"
                f"Full Name:  {admin_user.full_name or '(None)'}\n"
                f"Role:       {admin_user.role}\n"
                f"Status:     {'Active' if admin_user.is_active else 'Inactive'}\n"
                f"Created At: {admin_user.created_at.isoformat() if admin_user.created_at else 'Just now'}\n"
                "============================================================\n"
                "SECURITY NOTICE:\n"
                "- Store administrator credentials in a secure password manager.\n"
                "- Public self-registration remains disabled.\n"
                "- All further user accounts must be provisioned via the API:\n"
                "  POST /api/v1/auth/provision (requires platform_admin JWT token).\n"
                "============================================================\n"
            )
            return 0

    except PlatformAdminAlreadyExistsError as exc:
        stderr.write(f"ERROR: {exc}\n")
        return 2
    except (InvalidCredentialsError, DuplicateUserError) as exc:
        stderr.write(f"ERROR: {exc}\n")
        return 1
    except Exception as exc:
        stderr.write(f"UNEXPECTED DATABASE ERROR: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
