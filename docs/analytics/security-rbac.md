# AGGRIX Authentication & Role-Based Access Control (RBAC) Architecture

## 1. Overview

Stage 4 introduces production-grade cryptographic authentication, fine-grained Role-Based Access Control (RBAC), and authorized multi-store manager & platform administrator analytics services to the AGGRIX platform.

---

## 2. Security & User Models

### 2.1 User Entity (`users` table)
* `id` (`UUID`, PK): Unique user identifier.
* `email` (`VARCHAR(255)`, UNIQUE, INDEX): Account email address.
* `hashed_password` (`VARCHAR(255)`): Cryptographically salted password hash generated via **bcrypt** with 12 rounds. Plaintext passwords are never stored.
* `full_name` (`VARCHAR(255)`, nullable): User display name.
* `role` (`VARCHAR(50)`, INDEX): User role constrained by check constraint:
  - `tenant_user`: Regular tenant staff bound strictly to a single store.
  - `store_manager`: Multi-store manager assigned to multiple stores.
  - `platform_admin`: System executive with cross-tenant administrative access.
* `is_active` (`BOOLEAN`, default `true`): Operational account status. Deactivated accounts are rejected at the authentication dependency level.
* `tenant_id` (`UUID`, FK `tenants.id` on delete `SET NULL`): Home tenant association for `tenant_user`.
* `created_at` / `updated_at`: Timestamps with timezone.

### 2.2 Manager-to-Tenant Mapping (`manager_tenant_assignments` table)
* `id` (`UUID`, PK): Assignment record identifier.
* `user_id` (`UUID`, FK `users.id` on delete `CASCADE`): Multi-store manager reference.
* `tenant_id` (`UUID`, FK `tenants.id` on delete `CASCADE`): Target store reference.
* `created_at`: Grant timestamp.
* Constraints:
  - Unique composite index on `(user_id, tenant_id)` preventing duplicate assignments.
  - Index on `tenant_id` for reverse lookup.

---

## 3. RBAC Matrix & Permission Boundary

| Endpoint / Action | Tenant User | Multi-Store Manager | Platform Admin |
| :--- | :--- | :--- | :--- |
| **GET `/api/v1/analytics/tenants/{id}/...`** (Own Store) | **Allowed** | **Allowed** (if assigned) | **Allowed** |
| **GET `/api/v1/analytics/tenants/{id}/...`** (Other Store) | **Forbidden (403)** | **Forbidden (403)** | **Allowed** |
| **GET `/api/v1/analytics/manager/summary`** | **Forbidden (403)** | **Allowed** (assigned stores) | **Allowed** (all stores) |
| **GET `/api/v1/analytics/manager/stores`** | **Forbidden (403)** | **Allowed** (assigned stores) | **Allowed** (all stores) |
| **GET `/api/v1/analytics/manager/compare`** | **Forbidden (403)** | **Allowed** (assigned stores) | **Allowed** (all stores) |
| **GET `/api/v1/analytics/platform/summary`** | **Forbidden (403)** | **Forbidden (403)** | **Allowed** |
| **GET `/api/v1/auth/me`** | **Allowed** | **Allowed** | **Allowed** |

### Authorization Enforcement Guarantees:
1. **Never Trust Client Input**: `tenant_id` in path parameters or query strings is never trusted without verifying permissions against the cryptographically decoded JWT bearer token.
2. **Explicit Manager Scoping**: Multi-store managers can **only** query stores explicitly granted in `manager_tenant_assignments`. Requesting unassigned stores returns `403 Forbidden`.
3. **Empty Assignment Gracefulness**: Managers with zero assigned stores receive a clean 200 OK empty response (`assigned_tenants_count=0`, `total_orders=0`, `currencies=[]`).
4. **Strict Currency Segregation**: Multi-tenant manager rollups never add together different currencies (e.g. USD, EUR, INR). Root sales are `null` unless a single currency is filtered, and separate currency summaries are provided.

---

## 4. Authentication Flow & Token Usage

### 4.1 Token Generation
* **Algorithm**: HMAC-SHA256 (`HS256`).
* **Secret Key**: Minimum 32-byte cryptographic secret configured via `JWT_SECRET_KEY`.
* **Payload Claims**:
  ```json
  {
    "sub": "b2f6762c-8cb4-49c8-89c0-6fe7b92ff150",
    "role": "store_manager",
    "tenant_id": null,
    "iat": 1730416800,
    "exp": 1730420400
  }
  ```

### 4.2 Login Request Example
```http
POST /api/v1/auth/login HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "email": "manager@aggrix.com",
  "password": "SecurePassword123!"
}
```

### 4.3 Login Response Example
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "b2f6762c-8cb4-49c8-89c0-6fe7b92ff150",
  "email": "manager@aggrix.com",
  "role": "store_manager",
  "tenant_id": null,
  "assigned_tenant_ids": [
    "85056a62-e8fa-4587-8a50-c979bc73d7bf",
    "20387625-bf26-4a40-9d11-71c2fb27fdeb"
  ]
}
```

### 4.4 Authorized API Invocation
Every protected endpoint requires the `Authorization: Bearer <token>` header:
```http
GET /api/v1/analytics/manager/summary HTTP/1.1
Host: localhost:8000
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Accept: application/json
```

---

## 5. Endpoints Reference & JSON Examples

### 5.1 Manager Summary (`GET /api/v1/analytics/manager/summary`)
Aggregates performance metrics across all stores assigned to the manager.

#### Example Response (Multi-Currency Assigned Stores)
```json
{
  "manager_user_id": "b2f6762c-8cb4-49c8-89c0-6fe7b92ff150",
  "assigned_tenants_count": 2,
  "assigned_tenant_ids": [
    "85056a62-e8fa-4587-8a50-c979bc73d7bf",
    "20387625-bf26-4a40-9d11-71c2fb27fdeb"
  ],
  "date_range": {
    "start_date": null,
    "end_date": null
  },
  "currency": null,
  "total_orders": 4000,
  "gross_sales": null,
  "net_sales": null,
  "pending_orders_count": null,
  "pending_sales": null,
  "cancelled_orders_count": null,
  "cancelled_sales": null,
  "currencies": [
    {
      "currency": "EUR",
      "total_orders": 2000,
      "gross_sales": "1043786.29",
      "net_sales": "885543.31",
      "pending_orders_count": 210,
      "pending_sales": "120300.00",
      "cancelled_orders_count": 90,
      "cancelled_sales": "47942.98"
    },
    {
      "currency": "USD",
      "total_orders": 2000,
      "gross_sales": "1066135.02",
      "net_sales": "892047.17",
      "pending_orders_count": 215,
      "pending_sales": "124527.25",
      "cancelled_orders_count": 95,
      "cancelled_sales": "49560.60"
    }
  ]
}
```

### 5.2 Manager Store Breakdown (`GET /api/v1/analytics/manager/stores`)
Returns individual store rollups in a single grouped SQL query without N+1 overhead.

#### Example Response
```json
{
  "manager_user_id": "b2f6762c-8cb4-49c8-89c0-6fe7b92ff150",
  "total_stores": 2,
  "date_range": {
    "start_date": null,
    "end_date": null
  },
  "currency": null,
  "stores": [
    {
      "tenant_id": "85056a62-e8fa-4587-8a50-c979bc73d7bf",
      "tenant_name": "Nordic Living Goods",
      "domain": "nordic-living.myshopify.com",
      "timezone": "Europe/Stockholm",
      "total_orders": 2000,
      "gross_sales": "1066135.02",
      "net_sales": "892047.17",
      "pending_orders_count": 215,
      "pending_sales": "124527.25",
      "cancelled_orders_count": 95,
      "cancelled_sales": "49560.60",
      "currency": "USD",
      "currencies": [
        {
          "currency": "USD",
          "total_orders": 2000,
          "gross_sales": "1066135.02",
          "net_sales": "892047.17",
          "pending_orders_count": 215,
          "pending_sales": "124527.25",
          "cancelled_orders_count": 95,
          "cancelled_sales": "49560.60"
        }
      ]
    }
  ]
}
```

### 5.3 Platform Admin Summary (`GET /api/v1/analytics/platform/summary`)
Returns platform-wide metrics across all tenants. Only Platform Administrators may access this endpoint.

#### Example Response
```json
{
  "total_tenants": 5,
  "date_range": {
    "start_date": null,
    "end_date": null
  },
  "currency": "USD",
  "total_orders": 10000,
  "gross_sales": "5332954.22",
  "net_sales": "4527904.35",
  "pending_orders_count": 1075,
  "pending_sales": "551188.47",
  "cancelled_orders_count": 475,
  "cancelled_sales": "253861.40",
  "currencies": [
    {
      "currency": "USD",
      "total_orders": 10000,
      "gross_sales": "5332954.22",
      "net_sales": "4527904.35",
      "pending_orders_count": 1075,
      "pending_sales": "551188.47",
      "cancelled_orders_count": 475,
      "cancelled_sales": "253861.40"
    }
  ]
}
```

---

## 6. Security Limitations & Production Considerations

1. **Token Invalidation & Revocation**:
   - Current tokens are stateless JWTs validated via signature and expiration (`exp`). Immediate token revocation prior to expiry (e.g., on logout or password change) requires a Redis token blacklist or jti tracking table.
2. **Refresh Token Flow**:
   - Current tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60 minutes). A refresh token rotation pattern can be implemented in a future milestone for seamless session extension.
3. **Multi-Factor Authentication (MFA)**:
   - TOTP/WebAuthn is not yet enforced for administrative roles.
4. **Rate Limiting**:
   - Login endpoints should be paired with IP/email rate limiting (e.g. slowloris protection / token-bucket) to mitigate brute-force password guessing.

---

## 7. Day-Zero Initial Platform Administrator CLI Provisioning

Because public registration (`POST /api/v1/auth/register`) is disabled and account provisioning (`POST /api/v1/auth/provision`) requires an active `platform_admin` token, a fresh AGGRIX deployment starts with zero users.

The system provides a secure, one-time offline bootstrap CLI to initialize the first platform administrator without exposing secrets or network attack surfaces.

### 7.1 Security Guarantees
1. **Strict One-Time Bootstrap**: The CLI queries the `users` table and immediately aborts if any `platform_admin` already exists (exit code 2). Subsequent accounts must be provisioned via the API.
2. **Hidden Password Prompts**: Passwords are entered using `getpass` (no terminal echo or plaintext exposure).
3. **Bcrypt 12-Round Hashing**: Plaintext passwords are never persisted to disk, database, or logs.
4. **Credential Validation**: RFC 5322 email syntax validation, minimum 8 characters, and maximum 72 bytes (bcrypt limit).
5. **Transactional Database Session**: Automatically rolls back on any unhandled exception or duplicate email conflict.

### 7.2 Usage Instructions

#### Interactive Mode (Default & Recommended)
Prompts for email, optional display name, and double-entry hidden password:
```bash
python -m app.cli.init_admin
# Or via management dispatcher:
python -m app.cli init-admin
```

Example prompt session:
```text
Enter platform administrator email: admin@aggrix.com
Enter full name (optional, press Enter to skip): Chief Admin
Enter administrator password: <hidden>
Confirm administrator password: <hidden>

============================================================
AGGRIX Platform Administrator Initialized Successfully
============================================================
User ID:    3fa85f64-5717-4562-b3fc-2c963f66afa6
Email:      admin@aggrix.com
Full Name:  Chief Admin
Role:       platform_admin
Status:     Active
Created At: 2026-10-31T22:20:00+00:00
============================================================
```

#### Providing Email as Flag
Prompts only for the hidden password:
```bash
python -m app.cli.init_admin --email admin@aggrix.com --full-name "Chief Admin"
```

#### Headless / Automated Mode (CI/CD & Container Startup)
Allows passing the password via standard input without interactive prompts:
```bash
echo "$SECURE_ADMIN_PASSWORD" | python -m app.cli.init_admin --email admin@aggrix.com --password-stdin
```

#### Check Bootstrap Status
Check whether an initial bootstrap is required without attempting creation:
```bash
python -m app.cli.init_admin --check-only
# Exit code 0: No platform admin exists (ready for bootstrap)
# Exit code 2: Platform admin already exists (bootstrap disabled)
```

