"""
Merchant Authentication and Dashboard Blueprint

Provides:
- Merchant self-registration (/merchant/register)
- Merchant login (/merchant/login)
- Merchant dashboard (/merchant/dashboard)
- API key management (/merchant/api-keys)
- Transaction history (/merchant/transactions)
- Balance overview (/merchant/balances)
- Settings management (/merchant/settings)
"""

import functools
from decimal import Decimal

from flask import (
    Blueprint, flash, g, redirect, render_template,
    request, session, url_for, jsonify
)
from flask import current_app as app

from shkeeper import db
from shkeeper.models import (
    Merchant, MerchantStatus, MerchantBalance, Invoice, Transaction,
    CommissionRecord, PlatformSettings, MerchantPayout, MerchantPayoutStatus
)
from shkeeper.auth import merchant_login_required


bp = Blueprint("merchant_auth", __name__, url_prefix="/merchant")


@bp.context_processor
def inject_theme():
    """Inject theme variable for all merchant templates."""
    return {"theme": request.cookies.get("theme", "light")}


# ============================================================================
# Authentication Routes
# ============================================================================

@bp.route("/register", methods=["GET", "POST"])
def register():
    """Public merchant registration - no login required."""
    if request.method == "POST":
        security_phrase = request.form.get("security_phrase", "").strip()
        security_phrase_confirm = request.form.get("security_phrase_confirm", "").strip()

        error = None

        if not security_phrase:
            error = "Security phrase is required."
        elif len(security_phrase) < 8:
            error = "Security phrase must be at least 8 characters."
        elif security_phrase != security_phrase_confirm:
            error = "Security phrase confirmation does not match."

        if error is None:
            # Get platform settings for auto-approve
            platform = PlatformSettings.get()
            initial_status = (
                MerchantStatus.ACTIVE
                if platform.auto_approve_merchants
                else MerchantStatus.PENDING
            )

            login_id = Merchant.generate_login_id()
            while Merchant.query.filter_by(login_id=login_id).first():
                login_id = Merchant.generate_login_id()
            login_secret = Merchant.generate_login_secret()
            merchant_name = f"merchant-{login_id[:8]}"

            # Create merchant account
            merchant = Merchant(
                name=merchant_name,
                login_id=login_id,
                login_secret_hash=Merchant.hash_secret(login_secret),
                security_phrase_hash=Merchant.hash_secret(security_phrase),
                # keep email column non-identifying to satisfy legacy schema
                email=f"{login_id}@torpay.local",
                api_key=Merchant.generate_api_key(),
                webhook_secret=Merchant.generate_webhook_secret(),
                status=initial_status,
            )
            db.session.add(merchant)
            db.session.commit()

            # Auto-login after registration
            session["merchant_id"] = merchant.id
            session["merchant_credentials"] = {
                "login_id": login_id,
                "login_secret": login_secret,
                "message": "Save these credentials now. They will not be shown again.",
            }

            if initial_status == MerchantStatus.PENDING:
                flash("Account created! Your account is pending approval.")
            else:
                flash("Account created! Credentials generated.")

            return redirect(url_for("merchant_auth.credentials"))

        flash(error)

    return render_template("merchant/register.j2")


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Merchant login."""
    if request.method == "POST":
        login_id = request.form.get("login_id", "").strip()
        login_secret = request.form.get("login_secret", "")

        error = None
        merchant = Merchant.query.filter_by(login_id=login_id).first()

        if merchant is None:
            error = "Invalid login ID or secret."
        elif not merchant.verify_login_secret(login_secret):
            error = "Invalid login ID or secret."
        elif merchant.status == MerchantStatus.SUSPENDED:
            error = "Your account has been suspended. Please contact support."
        elif merchant.status == MerchantStatus.PENDING:
            error = "Your account is pending approval."

        if error is None:
            session["merchant_id"] = merchant.id
            return redirect(url_for("merchant_auth.dashboard"))

        flash(error)

    return render_template("merchant/login.j2")


@bp.route("/credentials")
@merchant_login_required
def credentials():
    """One-time credential reveal screen after registration/rotation."""
    creds = session.pop("merchant_credentials", None)
    if not creds:
        return redirect(url_for("merchant_auth.dashboard"))
    return render_template("merchant/credentials.j2", credentials=creds)


@bp.route("/logout")
def logout():
    """Log out merchant."""
    session.pop("merchant_id", None)
    session.pop("merchant_credentials", None)
    flash("You have been logged out.")
    return redirect(url_for("merchant_auth.login"))


# ============================================================================
# Dashboard Routes
# ============================================================================

@bp.route("/dashboard")
@merchant_login_required
def dashboard():
    """Merchant dashboard - overview of balances and recent transactions."""
    merchant = g.current_merchant

    # Get balances
    balances = MerchantBalance.query.filter_by(merchant_id=merchant.id).all()

    # Calculate total balances grouped by fiat to avoid mixing currencies
    total_balances_by_fiat = {}
    for b in balances:
        fiat = (b.fiat or "USD").upper()
        total_balances_by_fiat[fiat] = total_balances_by_fiat.get(fiat, Decimal(0)) + (b.available_balance or Decimal(0))

    # Get recent invoices
    recent_invoices = (
        Invoice.query
        .filter_by(merchant_id=merchant.id)
        .order_by(Invoice.created_at.desc())
        .limit(10)
        .all()
    )

    # Get recent commissions
    recent_commissions = (
        CommissionRecord.query
        .filter_by(merchant_id=merchant.id)
        .order_by(CommissionRecord.created_at.desc())
        .limit(10)
        .all()
    )

    # Get pending payouts
    pending_payouts = (
        MerchantPayout.query
        .filter_by(merchant_id=merchant.id)
        .filter(MerchantPayout.status.in_([
            MerchantPayoutStatus.PENDING,
            MerchantPayoutStatus.APPROVED,
            MerchantPayoutStatus.PROCESSING
        ]))
        .all()
    )

    return render_template(
        "merchant/dashboard.j2",
        merchant=merchant,
        balances=balances,
        total_balances_by_fiat=total_balances_by_fiat,
        recent_invoices=recent_invoices,
        recent_commissions=recent_commissions,
        pending_payouts=pending_payouts,
    )


@bp.route("/api-keys")
@merchant_login_required
def api_keys():
    """View and manage API keys."""
    merchant = g.current_merchant
    base_url = request.host_url.rstrip('/')
    return render_template("merchant/api_keys.j2", merchant=merchant, base_url=base_url)


@bp.route("/api-keys/regenerate", methods=["POST"])
@merchant_login_required
def regenerate_api_key():
    """Generate new API key (invalidates old one)."""
    merchant = g.current_merchant
    merchant.api_key = Merchant.generate_api_key()
    db.session.commit()
    flash(f"New API Key generated: {merchant.api_key}")
    return redirect(url_for("merchant_auth.api_keys"))


@bp.route("/api-keys/regenerate-webhook", methods=["POST"])
@merchant_login_required
def regenerate_webhook_secret():
    """Generate new webhook secret."""
    merchant = g.current_merchant
    merchant.webhook_secret = Merchant.generate_webhook_secret()
    db.session.commit()
    flash(f"New Webhook Secret generated: {merchant.webhook_secret}")
    return redirect(url_for("merchant_auth.api_keys"))


@bp.route("/transactions")
@merchant_login_required
def transactions():
    """View transaction history."""
    merchant = g.current_merchant

    page = request.args.get("page", 1, type=int)
    per_page = 20

    # Get invoices with pagination
    invoices = (
        Invoice.query
        .filter_by(merchant_id=merchant.id)
        .order_by(Invoice.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return render_template(
        "merchant/transactions.j2",
        merchant=merchant,
        invoices=invoices,
    )


@bp.route("/balances")
@merchant_login_required
def balances():
    """View detailed balance breakdown."""
    merchant = g.current_merchant

    balances = MerchantBalance.query.filter_by(merchant_id=merchant.id).all()

    # Get commission totals
    total_commission = (
        db.session.query(db.func.sum(CommissionRecord.commission_amount))
        .filter(CommissionRecord.merchant_id == merchant.id)
        .scalar() or Decimal(0)
    )

    total_received = (
        db.session.query(db.func.sum(CommissionRecord.gross_amount))
        .filter(CommissionRecord.merchant_id == merchant.id)
        .scalar() or Decimal(0)
    )

    return render_template(
        "merchant/balances.j2",
        merchant=merchant,
        balances=balances,
        total_commission=total_commission,
        total_received=total_received,
    )


@bp.route("/settings", methods=["GET", "POST"])
@merchant_login_required
def settings():
    """Manage merchant settings."""
    merchant = g.current_merchant

    if request.method == "POST":
        # Update callback URL
        callback_url = request.form.get("callback_url_base", "").strip()
        merchant.callback_url_base = callback_url if callback_url else None

        # Update payout addresses (JSON)
        import json
        payout_addresses = {}
        for key in request.form:
            if key.startswith("payout_address_"):
                crypto = key.replace("payout_address_", "")
                addr = request.form[key].strip()
                if addr:
                    payout_addresses[crypto] = addr
        merchant.payout_addresses = json.dumps(payout_addresses)

        # Update auto payout setting
        merchant.auto_payout = request.form.get("auto_payout") == "on"

        # Update min payout amount
        try:
            min_payout = Decimal(request.form.get("min_payout_amount", "100"))
            merchant.min_payout_amount = min_payout
        except:
            pass

        db.session.commit()
        flash("Settings updated successfully.")
        return redirect(url_for("merchant_auth.settings"))

    return render_template("merchant/settings.j2", merchant=merchant)


@bp.route("/rotate-secret", methods=["POST"])
@merchant_login_required
def rotate_secret():
    """Rotate the login secret after validating the security phrase."""
    merchant = g.current_merchant
    phrase = request.form.get("security_phrase", "").strip()

    if not phrase:
        flash("Security phrase is required to rotate your login secret.")
        return redirect(url_for("merchant_auth.settings"))

    if merchant.security_phrase_hash:
        if not merchant.verify_security_phrase(phrase):
            flash("Invalid security phrase.")
            return redirect(url_for("merchant_auth.settings"))
    else:
        merchant.security_phrase_hash = Merchant.hash_secret(phrase)

    if not merchant.security_phrase_hash:
        flash("Invalid security phrase.")
        return redirect(url_for("merchant_auth.settings"))

    new_secret = Merchant.generate_login_secret()
    merchant.login_secret_hash = Merchant.hash_secret(new_secret)
    db.session.commit()

    session["merchant_credentials"] = {
        "login_id": merchant.login_id,
        "login_secret": new_secret,
        "message": "Login secret rotated. Store the new secret safely.",
    }
    flash("Login secret rotated.")
    return redirect(url_for("merchant_auth.credentials"))


@bp.route("/payouts")
@merchant_login_required
def payouts():
    """View payout history and request new payouts."""
    merchant = g.current_merchant

    page = request.args.get("page", 1, type=int)
    per_page = 20

    payout_list = (
        MerchantPayout.query
        .filter_by(merchant_id=merchant.id)
        .order_by(MerchantPayout.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    balances = MerchantBalance.query.filter_by(merchant_id=merchant.id).all()

    return render_template(
        "merchant/payouts.j2",
        merchant=merchant,
        payouts=payout_list,
        balances=balances,
    )


@bp.route("/payouts/request", methods=["POST"])
@merchant_login_required
def request_payout():
    """Request a payout."""
    merchant = g.current_merchant

    crypto = request.form.get("crypto")
    amount_str = request.form.get("amount", "0")
    security_phrase = request.form.get("security_phrase", "").strip()

    if not security_phrase:
        flash("Security phrase is required to request a payout.")
        return redirect(url_for("merchant_auth.payouts"))

    if merchant.security_phrase_hash:
        if not merchant.verify_security_phrase(security_phrase):
            flash("Invalid security phrase.")
            return redirect(url_for("merchant_auth.payouts"))
    else:
        merchant.security_phrase_hash = Merchant.hash_secret(security_phrase)
        db.session.commit()

    try:
        amount = Decimal(amount_str)
    except:
        flash("Invalid amount.")
        return redirect(url_for("merchant_auth.payouts"))

    # Pick a balance with funds for this crypto (respecting fiat bucket)
    fiat_preference = request.form.get("fiat")
    balances = [
        b for b in MerchantBalance.query.filter_by(merchant_id=merchant.id, crypto=crypto).all()
        if (b.available_balance or Decimal(0)) > 0
    ]

    balance = None
    if fiat_preference:
        balance = next((b for b in balances if (b.fiat or "").upper() == fiat_preference.upper()), None)
    if not balance and balances:
        # Default to the balance with the most available funds
        balance = max(balances, key=lambda b: b.available_balance or Decimal(0))

    if not balance or (balance.available_balance or Decimal(0)) <= 0:
        flash("No balance available for this currency.")
        return redirect(url_for("merchant_auth.payouts"))

    # If amount is 0, withdraw all
    if amount <= 0:
        amount = balance.available_balance

    if amount > balance.available_balance:
        flash("Insufficient balance.")
        return redirect(url_for("merchant_auth.payouts"))

    # Get payout address
    dest_address = merchant.get_payout_address(crypto)
    if not dest_address:
        flash(f"No payout address configured for {crypto}. Please update your settings.")
        return redirect(url_for("merchant_auth.settings"))

    # Check minimum payout
    platform = PlatformSettings.get()
    min_payout = platform.min_payout_amount or Decimal(50)
    if amount < min_payout:
        flash(f"Minimum payout amount is ${min_payout}.")
        return redirect(url_for("merchant_auth.payouts"))

    # Create payout request
    payout = MerchantPayout(
        merchant_id=merchant.id,
        crypto=crypto,
        fiat=balance.fiat or "USD",
        amount_fiat=amount,
        dest_address=dest_address,
        status=MerchantPayoutStatus.PENDING,
    )
    db.session.add(payout)

    # Move from available to pending balance
    balance.available_balance -= amount
    balance.pending_balance = (balance.pending_balance or Decimal(0)) + amount

    db.session.commit()

    flash(f"Payout request submitted for ${amount} in {crypto}.")
    return redirect(url_for("merchant_auth.payouts"))


# ============================================================================
# API Endpoints for Merchant Dashboard (AJAX)
# ============================================================================

@bp.route("/api/stats")
@merchant_login_required
def api_stats():
    """Get merchant statistics for dashboard."""
    merchant = g.current_merchant

    # Calculate stats
    total_invoices = Invoice.query.filter_by(merchant_id=merchant.id).count()
    paid_invoices = Invoice.query.filter_by(
        merchant_id=merchant.id
    ).filter(Invoice.status.in_(["PAID", "OVERPAID"])).count()

    total_commission = (
        db.session.query(db.func.sum(CommissionRecord.commission_amount))
        .filter_by(merchant_id=merchant.id)
        .scalar() or Decimal(0)
    )

    total_received = (
        db.session.query(db.func.sum(CommissionRecord.gross_amount))
        .filter_by(merchant_id=merchant.id)
        .scalar() or Decimal(0)
    )

    total_available = sum(
        (b.available_balance or Decimal(0))
        for b in MerchantBalance.query.filter_by(merchant_id=merchant.id).all()
    )

    return jsonify({
        "total_invoices": total_invoices,
        "paid_invoices": paid_invoices,
        "total_received": str(total_received),
        "total_commission": str(total_commission),
        "total_available": str(total_available),
    })


@bp.route("/docs")
@merchant_login_required
def docs():
    """API documentation page for merchants."""
    merchant = Merchant.query.get(session["merchant_id"])

    # Get list of available cryptocurrencies
    from shkeeper.modules.classes.crypto import Crypto
    cryptos = list(Crypto.instances.keys())

    # Build base URL for API examples
    base_url = request.host_url.rstrip('/')

    return render_template(
        "merchant/docs.j2",
        merchant=merchant,
        cryptos=cryptos,
        base_url=base_url
    )


@bp.route("/integration")
@merchant_login_required
def integration():
    """Widget integration and embed code generator."""
    merchant = Merchant.query.get(session["merchant_id"])

    # Get list of available cryptocurrencies, ordered with BTC first
    from shkeeper.modules.classes.crypto import Crypto
    cryptos = list(Crypto.instances.keys())

    # Sort with BTC first, then alphabetically
    preferred_order = ['BTC', 'ETH', 'LTC', 'XMR', 'USDT-TRC20', 'USDT-ERC20', 'TRX', 'DOGE']
    def sort_key(c):
        try:
            return preferred_order.index(c)
        except ValueError:
            return len(preferred_order) + ord(c[0])
    cryptos.sort(key=sort_key)

    # Build base URL
    base_url = request.host_url.rstrip('/')

    return render_template(
        "merchant/integration.j2",
        merchant=merchant,
        cryptos=cryptos,
        base_url=base_url
    )
