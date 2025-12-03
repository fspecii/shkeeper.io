import click
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from decimal import Decimal
from shkeeper import requests

from flask import Blueprint, json
from flask import current_app as app

from shkeeper.modules.classes.crypto import Crypto
from shkeeper.models import (
    db, Invoice, InvoiceAddress, Transaction, UnconfirmedTransaction,
    InvoiceStatus, FeeCalculationPolicy, Merchant, MerchantBalance,
    PlatformSettings, CommissionRecord
)
from shkeeper.utils import format_decimal, remove_exponent


bp = Blueprint("callback", __name__)


# ============================================================================
# Webhook Signature Generation
# ============================================================================

def generate_webhook_signature(payload: dict, secret: str, timestamp: int) -> str:
    """
    Generate HMAC-SHA256 signature for webhook payload.

    The signature is computed over: "{timestamp}.{json_payload}"
    This allows merchants to verify both the payload integrity and prevent replay attacks.

    Args:
        payload: The notification payload dict
        secret: The merchant's webhook_secret
        timestamp: Unix timestamp of when the webhook is sent

    Returns:
        Hex-encoded HMAC-SHA256 signature
    """
    message = f"{timestamp}.{json.dumps(payload, separators=(',', ':'), sort_keys=True)}"
    return hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()


# ============================================================================
# Commission Calculation (Multi-Tenant Platform)
# ============================================================================

def calculate_commission(merchant, amount_fiat):
    """
    Calculate commission for a payment.

    Args:
        merchant: The Merchant object (or None for legacy invoices)
        amount_fiat: The gross payment amount in fiat

    Returns:
        tuple: (commission_amount, net_amount, commission_percent, commission_fixed)
    """
    if not merchant:
        # Legacy invoice without merchant - no commission
        return Decimal(0), amount_fiat, Decimal(0), Decimal(0)

    # Get platform settings
    platform = PlatformSettings.get()

    # Use merchant override if set, otherwise use platform default
    commission_percent = (
        merchant.commission_percent
        if merchant.commission_percent is not None
        else platform.default_commission_percent
    )
    commission_fixed = merchant.commission_fixed or platform.default_commission_fixed or Decimal(0)

    # Calculate commission: percentage + fixed fee
    commission_amount = (amount_fiat * commission_percent / 100) + commission_fixed
    net_amount = amount_fiat - commission_amount

    # Ensure net_amount is not negative
    if net_amount < 0:
        net_amount = Decimal(0)
        commission_amount = amount_fiat

    return commission_amount, net_amount, commission_percent, commission_fixed


def record_commission(invoice, tx, commission_amount, commission_percent, commission_fixed):
    """
    Record commission and update merchant balance.

    Args:
        invoice: The Invoice object
        tx: The Transaction object
        commission_amount: Commission amount in fiat
        commission_percent: Commission percentage applied
        commission_fixed: Fixed commission fee applied
    """
    if not invoice.merchant_id:
        return

    merchant = Merchant.query.get(invoice.merchant_id)
    if not merchant:
        return

    net_amount = invoice.balance_fiat - commission_amount

    # Update invoice with commission info
    invoice.commission_amount = commission_amount
    invoice.net_amount = net_amount

    # Create commission record
    commission_record = CommissionRecord(
        merchant_id=merchant.id,
        invoice_id=invoice.id,
        transaction_id=tx.id,
        tx_hash=tx.txid,
        crypto=tx.crypto,
        gross_amount=invoice.balance_fiat,
        commission_amount=commission_amount,
        net_amount=net_amount,
        commission_percent=commission_percent,
        commission_fixed=commission_fixed,
        status="recorded"
    )
    db.session.add(commission_record)

    # Update merchant balance (track per-crypto AND per-fiat)
    balance = MerchantBalance.get_or_create(merchant.id, tx.crypto, invoice.fiat)
    balance.total_received = (balance.total_received or Decimal(0)) + invoice.balance_fiat
    balance.total_commission = (balance.total_commission or Decimal(0)) + commission_amount
    balance.available_balance = (balance.available_balance or Decimal(0)) + net_amount

    db.session.commit()
    app.logger.info(
        f"[{tx.crypto}/{tx.txid}] Commission recorded: "
        f"gross={invoice.balance_fiat}, commission={commission_amount} ({commission_percent}%), "
        f"net={net_amount}, merchant={merchant.id}"
    )


def send_unconfirmed_notification(utx: UnconfirmedTransaction):
    app.logger.info(
        f"send_unconfirmed_notification started for {utx.crypto} {utx.txid}, {utx.addr}, {utx.amount_crypto}"
    )

    invoice_address = InvoiceAddress.query.filter_by(
        crypto=utx.crypto, addr=utx.addr
    ).first()
    invoice = Invoice.query.filter_by(id=invoice_address.invoice_id).first()
    crypto = Crypto.instances[utx.crypto]
    apikey = crypto.wallet.apikey

    notification = {
        "status": "unconfirmed",
        "external_id": invoice.external_id,
        "crypto": utx.crypto,
        "addr": utx.addr,
        "txid": utx.txid,
        "amount": format_decimal(utx.amount_crypto, precision=crypto.precision),
    }

    # Build headers with backward-compatible API key + new signature for merchants
    headers = {
        "X-Torpay-Api-Key": apikey,
        "X-Shkeeper-Api-Key": apikey,  # backward compatibility
    }
    if invoice.merchant_id:
        merchant = Merchant.query.get(invoice.merchant_id)
        if merchant and merchant.webhook_secret:
            timestamp = int(time.time())
            signature = generate_webhook_signature(notification, merchant.webhook_secret, timestamp)
            headers["X-Shkeeper-Signature"] = signature
            headers["X-Shkeeper-Timestamp"] = str(timestamp)

    app.logger.warning(
        f"[{utx.crypto}/{utx.txid}] Posting {notification} to {invoice.callback_url} with api key {apikey}"
    )
    try:
        r = requests.post(
            invoice.callback_url,
            json=notification,
            headers=headers,
            timeout=app.config.get("REQUESTS_NOTIFICATION_TIMEOUT"),
        )
    except Exception as e:
        app.logger.error(
            f"[{utx.crypto}/{utx.txid}] Unconfirmed TX notification failed: {e}"
        )
        return False

    if r.status_code != 202:
        app.logger.warning(
            f"[{utx.crypto}/{utx.txid}] Unconfirmed TX notification failed with HTTP code {r.status_code}"
        )
        return False

    utx.callback_confirmed = True
    db.session.commit()
    app.logger.info(
        f"[{utx.crypto}/{utx.txid}] Unconfirmed TX notification has been accepted"
    )

    return True


def send_notification(tx):
    app.logger.info(f"[{tx.crypto}/{tx.txid}] Notificator started")

    invoice = tx.invoice

    # Calculate commission if this is a merchant invoice and payment is complete
    commission_amount = Decimal(0)
    net_amount = invoice.balance_fiat
    commission_percent = Decimal(0)

    if invoice.merchant_id and invoice.status in (InvoiceStatus.PAID, InvoiceStatus.OVERPAID):
        merchant = Merchant.query.get(invoice.merchant_id)
        commission_amount, net_amount, commission_percent, commission_fixed = calculate_commission(
            merchant, invoice.balance_fiat
        )
        # Record commission (only if not already recorded)
        if not invoice.commission_amount or invoice.commission_amount == 0:
            record_commission(invoice, tx, commission_amount, commission_percent, commission_fixed)

    transactions = []
    for t in invoice.transactions:
        amount_fiat_without_fee = t.rate.get_orig_amount(t.amount_fiat)
        transactions.append(
            {
                "txid": t.txid,
                "date": str(t.created_at),
                "amount_crypto": remove_exponent(t.amount_crypto),
                "amount_fiat": remove_exponent(t.amount_fiat),
                "amount_fiat_without_fee": remove_exponent(amount_fiat_without_fee),
                "fee_fiat": remove_exponent(t.amount_fiat - amount_fiat_without_fee),
                "trigger": tx.id == t.id,
                "crypto": t.crypto,
            }
        )

    notification = {
        "external_id": invoice.external_id,
        "crypto": invoice.crypto,
        "addr": invoice.addr,
        "fiat": invoice.fiat,
        "balance_fiat": remove_exponent(invoice.balance_fiat),
        "balance_crypto": remove_exponent(invoice.balance_crypto),
        "paid": invoice.status in (InvoiceStatus.PAID, InvoiceStatus.OVERPAID),
        "status": invoice.status.name,
        "transactions": transactions,
        "fee_percent": remove_exponent(invoice.rate.fee),
        "fee_fixed": remove_exponent(invoice.rate.fixed_fee),
        "fee_policy": (
            invoice.rate.fee_policy.name
            if invoice.rate.fee_policy
            else FeeCalculationPolicy.PERCENT_FEE.name
        ),
    }

    # Add commission info for merchant invoices
    if invoice.merchant_id:
        notification["commission_amount"] = remove_exponent(commission_amount)
        notification["commission_percent"] = remove_exponent(commission_percent)
        notification["net_amount"] = remove_exponent(net_amount)

    overpaid_fiat = invoice.balance_fiat - (
        invoice.amount_fiat * (invoice.wallet.ulimit / 100)
    )
    notification["overpaid_fiat"] = (
        str(round(overpaid_fiat.normalize(), 2)) if overpaid_fiat > 0 else "0.00"
    )

    apikey = Crypto.instances[tx.crypto].wallet.apikey

    # Build headers with backward-compatible API key + new signature for merchants
    headers = {"X-Shkeeper-Api-Key": apikey}
    if invoice.merchant_id:
        merchant = Merchant.query.get(invoice.merchant_id)
        if merchant and merchant.webhook_secret:
            timestamp = int(time.time())
            signature = generate_webhook_signature(notification, merchant.webhook_secret, timestamp)
            headers["X-Shkeeper-Signature"] = signature
            headers["X-Shkeeper-Timestamp"] = str(timestamp)

    app.logger.warning(
        f"[{tx.crypto}/{tx.txid}] Posting {json.dumps(notification)} to {invoice.callback_url} with api key {apikey}"
    )
    try:
        r = requests.post(
            invoice.callback_url,
            json=notification,
            headers=headers,
            timeout=app.config.get("REQUESTS_NOTIFICATION_TIMEOUT"),
        )
    except Exception as e:
        app.logger.error(f"[{tx.crypto}/{tx.txid}] Notification failed: {e}")
        return False

    if r.status_code != 202:
        app.logger.warning(
            f"[{tx.crypto}/{tx.txid}] Notification failed by {invoice.callback_url} with HTTP code {r.status_code}"
        )
        return False

    tx.callback_confirmed = True
    db.session.commit()
    app.logger.info(
        f"[{tx.crypto}/{tx.txid}] Notification has been accepted by {invoice.callback_url}"
    )
    return True


def list_unconfirmed():
    for tx in Transaction.query.filter_by(callback_confirmed=False):
        print(tx)
    else:
        print("No unconfirmed transactions found!")


def send_callbacks():
    for utx in UnconfirmedTransaction.query.filter_by(callback_confirmed=False):
        try:
            send_unconfirmed_notification(utx)
        except Exception as e:
            app.logger.exception(
                f"Exception while sending callback for UTX {utx.crypto}/{utx.txid}"
            )

    for tx in Transaction.query.filter_by(
        callback_confirmed=False, need_more_confirmations=False
    ):
        try:
            delay_until_date = tx.created_at + timedelta(
                seconds=app.config.get("NOTIFICATION_TASK_DELAY")
            )
            if datetime.now() > delay_until_date:
                app.logger.info(
                    f"[{tx.crypto}/{tx.txid}] created at {tx.created_at}, delayed until {delay_until_date}"
                )
                if tx.invoice.status == InvoiceStatus.OUTGOING:
                    tx.callback_confirmed = True
                    db.session.commit()
                else:
                    app.logger.info(f"[{tx.crypto}/{tx.txid}] Notification is pending")
                    send_notification(tx)
            else:
                app.logger.info(
                    f"[{tx.crypto}/{tx.txid}] delaying notification created at {tx.created_at} until {delay_until_date}"
                )
        except Exception as e:
            app.logger.exception(
                f"Exception while sending callback for TX {tx.crypto}/{tx.txid}"
            )


def update_confirmations():
    for tx in Transaction.query.filter_by(
        callback_confirmed=False, need_more_confirmations=True
    ):
        try:
            app.logger.info(f"[{tx.crypto}/{tx.txid}] Updating confirmations")
            if not tx.is_more_confirmations_needed():
                app.logger.info(f"[{tx.crypto}/{tx.txid}] Got enough confirmations")
            else:
                app.logger.info(f"[{tx.crypto}/{tx.txid}] Not enough confirmations yet")
        except Exception as e:
            app.logger.exception(
                f"Exception while updating tx confirmations for {tx.crypto}/{tx.txid}"
            )


@bp.cli.command()
def list():
    """Shows list of transaction notifications to be sent"""
    list_unconfirmed()


@bp.cli.command()
def send():
    """Send transaction notification"""
    send_callbacks()


@bp.cli.command()
def update():
    """Update number of confirmation"""
    update_confirmations()


@bp.cli.command()
@click.option("-c", "--confirmations", default=1)
def add(confirmations):
    import time

    crypto = Crypto.instances["BTC"]
    invoice = Invoice.add(
        crypto,
        {
            "external_id": str(time.time()),
            "fiat": "USD",
            "amount": 1000,
            "callback_url": "http://localhost:5000/api/v1/wp_callback",
        },
    )
    tx = Transaction.add(
        crypto,
        {
            "txid": invoice.id * 100,
            "addr": invoice.addr,
            "amount": invoice.amount_crypto,
            "confirmations": confirmations,
        },
    )
