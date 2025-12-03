# SHKeeper Multi-Tenant + Commission Implementation Plan

## Overview

Transform SHKeeper from a single-tenant payment processor into a multi-merchant payment gateway platform (like Stripe for crypto) where:
- **Admin** manages the platform, merchants, and commission settings
- **Merchants** get API keys to integrate payments on their own websites
- **Platform** automatically deducts commission from each payment

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TORPAY PLATFORM                          │
│                    (Your SHKeeper)                          │
├─────────────────────────────────────────────────────────────┤
│  ADMIN DASHBOARD (Existing Web UI)                          │
│  - Manage merchants (create, suspend, view)                 │
│  - Set platform commission (global default)                 │
│  - View all transactions & commissions                      │
│  - Manage crypto wallets                                    │
├─────────────────────────────────────────────────────────────┤
│  MERCHANT API                                               │
│  - Each merchant gets unique API key                        │
│  - Create invoices: POST /api/v1/<crypto>/payment_request   │
│  - Check status: GET /api/v1/invoices/<id>                  │
│  - Receive callbacks with payment notifications             │
├─────────────────────────────────────────────────────────────┤
│  PAYMENT FLOW                                               │
│  1. Merchant creates invoice via API                        │
│  2. Customer pays to generated address                      │
│  3. Platform receives full payment                          │
│  4. Commission deducted, net amount tracked                 │
│  5. Callback sent to merchant with payment details          │
│  6. Merchant can request payout (manual or auto)            │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Database Schema Changes

### 1.1 New `Merchant` Model

```python
class MerchantStatus(enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"

class Merchant(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Basic Info
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)

    # API Authentication
    api_key = db.Column(db.String(64), unique=True, nullable=False)
    api_secret = db.Column(db.String(128))  # Optional: for signed requests

    # Commission Settings (overrides platform default if set)
    commission_percent = db.Column(db.Numeric, default=None)  # NULL = use platform default
    commission_fixed = db.Column(db.Numeric, default=0)

    # Payout Settings
    payout_address = db.Column(db.String(512))  # JSON: {"BTC": "addr", "ETH": "addr"}
    auto_payout = db.Column(db.Boolean, default=False)
    min_payout_amount = db.Column(db.Numeric, default=100)  # in USD

    # Status & Metadata
    status = db.Column(db.Enum(MerchantStatus), default=MerchantStatus.ACTIVE)
    callback_url_base = db.Column(db.String(512))  # Optional default callback
    webhook_secret = db.Column(db.String(64))  # For signing webhooks

    # Timestamps
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, onupdate=db.func.current_timestamp())

    # Relationships
    invoices = db.relationship("Invoice", backref="merchant", lazy=True)
    balances = db.relationship("MerchantBalance", backref="merchant", lazy=True)

    @staticmethod
    def generate_api_key():
        import secrets
        return secrets.token_hex(32)
```

### 1.2 New `MerchantBalance` Model (Track per-crypto balances)

```python
class MerchantBalance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)
    crypto = db.Column(db.String, nullable=False)

    # Balances
    total_received = db.Column(db.Numeric, default=0)      # Total ever received
    total_commission = db.Column(db.Numeric, default=0)    # Total commission paid
    total_paid_out = db.Column(db.Numeric, default=0)      # Total withdrawn
    available_balance = db.Column(db.Numeric, default=0)   # Can withdraw now
    pending_balance = db.Column(db.Numeric, default=0)     # Awaiting confirmation

    updated_at = db.Column(db.DateTime, onupdate=db.func.current_timestamp())

    __table_args__ = (db.UniqueConstraint("merchant_id", "crypto"),)
```

### 1.3 New `PlatformSettings` Model

```python
class PlatformSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Commission
    default_commission_percent = db.Column(db.Numeric, default=2.0)  # 2% default
    default_commission_fixed = db.Column(db.Numeric, default=0)

    # Platform wallet for collecting commissions
    commission_wallet = db.Column(db.String(512))  # JSON: {"BTC": "addr", ...}

    # Payout settings
    min_payout_amount = db.Column(db.Numeric, default=50)  # USD
    payout_fee_percent = db.Column(db.Numeric, default=0)  # Fee on payouts

    updated_at = db.Column(db.DateTime, onupdate=db.func.current_timestamp())
```

### 1.4 New `CommissionRecord` Model

```python
class CommissionRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transaction.id"))

    crypto = db.Column(db.String, nullable=False)
    gross_amount = db.Column(db.Numeric, nullable=False)      # Full payment
    commission_amount = db.Column(db.Numeric, nullable=False) # Our cut
    net_amount = db.Column(db.Numeric, nullable=False)        # Merchant gets
    commission_percent = db.Column(db.Numeric)
    commission_fixed = db.Column(db.Numeric)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
```

### 1.5 Modify Existing `Invoice` Model

Add merchant reference:

```python
class Invoice(db.Model):
    # ... existing fields ...

    # NEW: Link to merchant
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=True)

    # NEW: Commission tracking
    commission_amount = db.Column(db.Numeric, default=0)
    net_amount = db.Column(db.Numeric, default=0)  # amount after commission
```

### 1.6 Modify `User` Model (Admin users)

```python
class UserRole(enum.Enum):
    ADMIN = "admin"
    VIEWER = "viewer"  # Read-only admin

class User(db.Model):
    # ... existing fields ...
    role = db.Column(db.Enum(UserRole), default=UserRole.ADMIN)
    # Remove api_key - it moves to Merchant model
```

---

## Phase 2: Authentication Changes

### 2.1 Update `auth.py` - API Key Lookup

```python
def api_key_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if "X-Shkeeper-Api-Key" not in request.headers:
            return {"status": "error", "message": "No API key"}, 401

        apikey = request.headers["X-Shkeeper-Api-Key"]

        # NEW: Look up merchant by API key
        merchant = Merchant.query.filter_by(api_key=apikey, status=MerchantStatus.ACTIVE).first()
        if merchant:
            g.merchant = merchant  # Store merchant in request context
            return view(**kwargs)
        else:
            return {"status": "error", "message": "Invalid API key or merchant suspended"}, 401

    return wrapped_view
```

### 2.2 Add Merchant Context to All API Requests

Every API endpoint that uses `@api_key_required` will automatically have `g.merchant` available.

---

## Phase 3: API Endpoint Changes

### 3.1 Invoice Creation (`POST /api/v1/<crypto>/payment_request`)

**File:** `api_v1.py`

```python
@bp.route("/<crypto_name>/payment_request", methods=["POST"])
@api_key_required
def payment_request(crypto_name):
    merchant = g.merchant  # From auth decorator

    # Validate merchant is active
    if merchant.status != MerchantStatus.ACTIVE:
        return {"status": "error", "message": "Merchant account suspended"}, 403

    # Create invoice with merchant_id
    invoice = Invoice.add(crypto, request.json, merchant_id=merchant.id)

    return {
        "status": "success",
        "id": invoice.id,
        # ... rest of response
    }
```

### 3.2 Invoice Listing (`GET /api/v1/invoices`)

Filter by merchant:

```python
@bp.route("/invoices", methods=["GET"])
@api_key_required
def list_invoices():
    merchant = g.merchant
    invoices = Invoice.query.filter_by(merchant_id=merchant.id).all()
    return {"status": "success", "invoices": [i.to_json() for i in invoices]}
```

### 3.3 Transaction Listing - Filter by Merchant

All transaction queries must include merchant filter:

```python
# Before (single tenant):
transactions = Transaction.query.all()

# After (multi-tenant):
transactions = Transaction.query.join(Invoice).filter(Invoice.merchant_id == g.merchant.id).all()
```

---

## Phase 4: Commission Calculation

### 4.1 Update `callback.py` - Add Commission on Payment

```python
def calculate_commission(merchant, amount_fiat):
    """Calculate commission for a payment."""
    platform = PlatformSettings.query.first()

    # Use merchant override or platform default
    percent = merchant.commission_percent if merchant.commission_percent is not None else platform.default_commission_percent
    fixed = merchant.commission_fixed or platform.default_commission_fixed

    commission = (amount_fiat * percent / 100) + fixed
    net_amount = amount_fiat - commission

    return commission, net_amount, percent, fixed


def send_notification(tx):
    """Modified to include commission calculation."""
    invoice = tx.invoice
    merchant = invoice.merchant

    # Calculate commission
    commission, net_amount, pct, fixed = calculate_commission(merchant, invoice.balance_fiat)

    # Update invoice with commission info
    invoice.commission_amount = commission
    invoice.net_amount = net_amount
    db.session.commit()

    # Record commission
    CommissionRecord.create(
        merchant_id=merchant.id,
        invoice_id=invoice.id,
        transaction_id=tx.id,
        crypto=tx.crypto,
        gross_amount=invoice.balance_fiat,
        commission_amount=commission,
        net_amount=net_amount,
        commission_percent=pct,
        commission_fixed=fixed
    )

    # Update merchant balance
    balance = MerchantBalance.get_or_create(merchant.id, tx.crypto)
    balance.total_received += tx.amount_fiat
    balance.total_commission += commission
    balance.available_balance += net_amount
    db.session.commit()

    # Build notification with commission info
    notification = {
        "external_id": invoice.external_id,
        "gross_amount": str(invoice.balance_fiat),
        "commission": str(commission),
        "commission_percent": str(pct),
        "net_amount": str(net_amount),
        # ... rest of existing fields
    }

    # Send to merchant callback
    # ...
```

---

## Phase 5: Admin Dashboard Changes

### 5.1 Merchant Self-Registration (Public)

**File:** `merchant_auth.py` (new file)

| Route | Description |
|-------|-------------|
| `/merchant/register` | Public signup form |
| `/merchant/login` | Merchant login |
| `/merchant/dashboard` | Merchant's own dashboard |
| `/merchant/api-keys` | View/regenerate API keys |
| `/merchant/transactions` | View their transactions |
| `/merchant/payouts` | Request payouts |
| `/merchant/settings` | Update callback URL, payout addresses |

```python
bp = Blueprint("merchant_auth", __name__, url_prefix="/merchant")

@bp.route("/register", methods=["GET", "POST"])
def register():
    """Public merchant registration - no login required."""
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        business_name = request.form["business_name"]

        # Check if email already exists
        if Merchant.query.filter_by(email=email).first():
            flash("Email already registered")
            return render_template("merchant/register.j2")

        # Create merchant account
        merchant = Merchant(
            name=business_name,
            email=email,
            password_hash=Merchant.get_password_hash(password),
            api_key=Merchant.generate_api_key(),
            status=MerchantStatus.ACTIVE,  # Auto-approve (or PENDING for manual review)
        )
        db.session.add(merchant)
        db.session.commit()

        # Auto-login after registration
        session["merchant_id"] = merchant.id

        flash(f"Account created! Your API Key: {merchant.api_key}")
        return redirect(url_for("merchant_auth.dashboard"))

    return render_template("merchant/register.j2")


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Merchant login."""
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        merchant = Merchant.query.filter_by(email=email).first()

        if merchant and merchant.verify_password(password):
            if merchant.status == MerchantStatus.SUSPENDED:
                flash("Account suspended. Contact support.")
                return render_template("merchant/login.j2")

            session["merchant_id"] = merchant.id
            return redirect(url_for("merchant_auth.dashboard"))

        flash("Invalid email or password")
    return render_template("merchant/login.j2")


@bp.route("/dashboard")
@merchant_login_required
def dashboard():
    """Merchant dashboard - view balances, recent transactions."""
    merchant = g.current_merchant
    balances = MerchantBalance.query.filter_by(merchant_id=merchant.id).all()
    recent_invoices = Invoice.query.filter_by(merchant_id=merchant.id)\
        .order_by(Invoice.created_at.desc()).limit(10).all()

    return render_template("merchant/dashboard.j2",
        merchant=merchant,
        balances=balances,
        invoices=recent_invoices
    )


@bp.route("/api-keys")
@merchant_login_required
def api_keys():
    """Show API keys and allow regeneration."""
    merchant = g.current_merchant
    return render_template("merchant/api_keys.j2", merchant=merchant)


@bp.route("/api-keys/regenerate", methods=["POST"])
@merchant_login_required
def regenerate_api_key():
    """Generate new API key (invalidates old one)."""
    merchant = g.current_merchant
    merchant.api_key = Merchant.generate_api_key()
    db.session.commit()
    flash(f"New API Key: {merchant.api_key}")
    return redirect(url_for("merchant_auth.api_keys"))


@bp.route("/logout")
def logout():
    session.pop("merchant_id", None)
    return redirect(url_for("merchant_auth.login"))


# Decorator for merchant-only pages
def merchant_login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if "merchant_id" not in session:
            return redirect(url_for("merchant_auth.login"))
        g.current_merchant = Merchant.query.get(session["merchant_id"])
        if not g.current_merchant:
            session.pop("merchant_id", None)
            return redirect(url_for("merchant_auth.login"))
        return view(**kwargs)
    return wrapped_view
```

### 5.2 Admin Pages (Platform Management)

**File:** `admin.py`

| Route | Description |
|-------|-------------|
| `/admin/merchants` | List all merchants (view/suspend) |
| `/admin/merchants/<id>` | View merchant details |
| `/admin/merchants/<id>/suspend` | Suspend merchant |
| `/admin/merchants/<id>/activate` | Reactivate merchant |
| `/admin/settings` | Platform settings (commission %) |
| `/admin/commissions` | Commission reports |
| `/admin/payouts` | Process/approve merchant payouts |

```python
@bp.route("/admin/merchants", methods=["GET"])
@login_required
def list_merchants():
    merchants = Merchant.query.order_by(Merchant.created_at.desc()).all()
    return render_template("admin/merchants.j2", merchants=merchants)

@bp.route("/admin/merchants/<int:id>")
@login_required
def view_merchant(id):
    merchant = Merchant.query.get_or_404(id)
    balances = MerchantBalance.query.filter_by(merchant_id=id).all()
    invoices = Invoice.query.filter_by(merchant_id=id).order_by(Invoice.created_at.desc()).limit(50).all()
    commissions = CommissionRecord.query.filter_by(merchant_id=id).order_by(CommissionRecord.created_at.desc()).limit(50).all()
    return render_template("admin/merchant_detail.j2",
        merchant=merchant, balances=balances, invoices=invoices, commissions=commissions)

@bp.route("/admin/merchants/<int:id>/suspend", methods=["POST"])
@login_required
def suspend_merchant(id):
    merchant = Merchant.query.get_or_404(id)
    merchant.status = MerchantStatus.SUSPENDED
    db.session.commit()
    flash(f"Merchant {merchant.name} suspended")
    return redirect(url_for("admin.list_merchants"))

@bp.route("/admin/merchants/<int:id>/activate", methods=["POST"])
@login_required
def activate_merchant(id):
    merchant = Merchant.query.get_or_404(id)
    merchant.status = MerchantStatus.ACTIVE
    db.session.commit()
    flash(f"Merchant {merchant.name} activated")
    return redirect(url_for("admin.list_merchants"))
```

### 5.3 New Templates

```
templates/
  admin/
    merchants.j2          # List all merchants
    merchant_form.j2      # Create/edit merchant
    merchant_detail.j2    # View merchant + transactions
    settings.j2           # Platform commission settings
    commissions.j2        # Commission reports
```

---

## Phase 6: Merchant Payouts

### 6.1 Payout Request Endpoint

```python
@bp.route("/api/v1/payout/request", methods=["POST"])
@api_key_required
def request_payout():
    merchant = g.merchant
    crypto = request.json["crypto"]
    amount = Decimal(request.json.get("amount", 0))  # 0 = all available

    balance = MerchantBalance.query.filter_by(
        merchant_id=merchant.id,
        crypto=crypto
    ).first()

    if not balance or balance.available_balance <= 0:
        return {"status": "error", "message": "No balance available"}

    payout_amount = amount if amount > 0 else balance.available_balance

    if payout_amount > balance.available_balance:
        return {"status": "error", "message": "Insufficient balance"}

    # Create payout request (admin approves or auto-process)
    payout = MerchantPayout(
        merchant_id=merchant.id,
        crypto=crypto,
        amount=payout_amount,
        dest_address=merchant.payout_address.get(crypto),
        status="pending"
    )
    db.session.add(payout)

    # Deduct from available balance
    balance.available_balance -= payout_amount
    balance.pending_balance += payout_amount
    db.session.commit()

    return {"status": "success", "payout_id": payout.id}
```

---

## File Changes Summary

| File | Changes |
|------|---------|
| `models.py` | Add Merchant, MerchantBalance, PlatformSettings, CommissionRecord models. Modify Invoice, User |
| `auth.py` | Update api_key_required to look up Merchant, add g.merchant |
| `api_v1.py` | Add merchant_id to all operations, filter queries by merchant |
| `callback.py` | Add commission calculation, update balances |
| `wallet.py` | Add admin merchant management routes |
| `templates/admin/*` | New admin pages for merchant management |
| `migrations/` | New migration for schema changes |

---

## Migration Script

```python
"""Add multi-tenant support

Revision ID: add_multi_tenant
"""

from alembic import op
import sqlalchemy as sa

def upgrade():
    # Create merchant table
    op.create_table('merchant',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('api_key', sa.String(64), unique=True, nullable=False),
        sa.Column('commission_percent', sa.Numeric()),
        sa.Column('commission_fixed', sa.Numeric(), default=0),
        sa.Column('payout_address', sa.String(512)),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    # Create merchant_balance table
    op.create_table('merchant_balance',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('merchant_id', sa.Integer(), sa.ForeignKey('merchant.id')),
        sa.Column('crypto', sa.String(), nullable=False),
        sa.Column('total_received', sa.Numeric(), default=0),
        sa.Column('total_commission', sa.Numeric(), default=0),
        sa.Column('available_balance', sa.Numeric(), default=0),
        sa.UniqueConstraint('merchant_id', 'crypto'),
    )

    # Create platform_settings table
    op.create_table('platform_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('default_commission_percent', sa.Numeric(), default=2.0),
        sa.Column('default_commission_fixed', sa.Numeric(), default=0),
        sa.Column('commission_wallet', sa.String(512)),
    )

    # Create commission_record table
    op.create_table('commission_record',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('merchant_id', sa.Integer(), sa.ForeignKey('merchant.id')),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoice.id')),
        sa.Column('crypto', sa.String()),
        sa.Column('gross_amount', sa.Numeric()),
        sa.Column('commission_amount', sa.Numeric()),
        sa.Column('net_amount', sa.Numeric()),
        sa.Column('created_at', sa.DateTime()),
    )

    # Add merchant_id to invoice
    op.add_column('invoice', sa.Column('merchant_id', sa.Integer(), sa.ForeignKey('merchant.id')))
    op.add_column('invoice', sa.Column('commission_amount', sa.Numeric(), default=0))
    op.add_column('invoice', sa.Column('net_amount', sa.Numeric(), default=0))

    # Insert default platform settings
    op.execute("""
        INSERT INTO platform_settings (id, default_commission_percent, default_commission_fixed)
        VALUES (1, 2.0, 0)
    """)

def downgrade():
    op.drop_column('invoice', 'net_amount')
    op.drop_column('invoice', 'commission_amount')
    op.drop_column('invoice', 'merchant_id')
    op.drop_table('commission_record')
    op.drop_table('platform_settings')
    op.drop_table('merchant_balance')
    op.drop_table('merchant')
```

---

## Implementation Order

1. **Phase 1**: Database models + migration (1-2 hours)
2. **Phase 2**: Authentication changes (30 min)
3. **Phase 3**: API endpoint updates (1-2 hours)
4. **Phase 4**: Commission calculation (1 hour)
5. **Phase 5**: Admin dashboard (2-3 hours)
6. **Phase 6**: Merchant payouts (1-2 hours)

**Total Estimated Time**: 8-12 hours

---

## API Documentation for Merchants

After implementation, merchants will use:

```bash
# Create invoice
curl -X POST https://torpay.me/api/v1/BTC/payment_request \
  -H "X-Shkeeper-Api-Key: merchant_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "order_123",
    "fiat": "USD",
    "amount": 99.99,
    "callback_url": "https://mystore.com/webhook"
  }'

# Response
{
  "status": "success",
  "id": 456,
  "wallet": "bc1q...",
  "amount": "0.00234",
  "exchange_rate": "42735.00"
}

# Callback received by merchant
{
  "external_id": "order_123",
  "status": "PAID",
  "gross_amount": "99.99",
  "commission": "2.00",
  "commission_percent": "2.0",
  "net_amount": "97.99",
  "crypto": "BTC",
  "transactions": [...]
}
```

---

## Next Steps

1. Review this plan
2. Approve or suggest changes
3. Begin implementation phase by phase
