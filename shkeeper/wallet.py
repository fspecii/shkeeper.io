from collections import defaultdict
import copy
import csv
from decimal import Decimal, InvalidOperation
import inspect
from io import StringIO
import itertools
import segno

from flask import Blueprint
from flask import flash
from flask import g
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from werkzeug.exceptions import abort
from werkzeug.wrappers import Response
from flask import current_app as app
import prometheus_client

from shkeeper import db
from shkeeper.auth import login_required, metrics_basic_auth
from shkeeper.schemas import TronError
from shkeeper.wallet_encryption import (
    wallet_encryption,
    WalletEncryptionRuntimeStatus,
    WalletEncryptionPersistentStatus,
)
from .modules.classes.tron_token import TronToken
from .modules.classes.ethereum import Ethereum
from shkeeper.modules.rates import RateSource
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.models import (
    FeeCalculationPolicy,
    Invoice,
    InvoiceAddress,
    Payout,
    PayoutDestination,
    PayoutStatus,
    PayoutTx,
    PayoutTxStatus,
    Wallet,
    PayoutPolicy,
    ExchangeRate,
    InvoiceStatus,
    Transaction,
    # Multi-tenant models
    Merchant,
    MerchantStatus,
    MerchantBalance,
    PlatformSettings,
    CommissionRecord,
    MerchantPayout,
    MerchantPayoutStatus,
)


prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)

bp = Blueprint("wallet", __name__)


@bp.context_processor
def inject_theme():
    return {"theme": request.cookies.get("theme", "light")}


@bp.route("/")
def index():
    return redirect(url_for("wallet.wallets"))


@bp.route("/wallets")
@login_required
def wallets():
    cryptos = dict(sorted(Crypto.instances.items())).values()
    return render_template("wallet/wallets.j2", cryptos=cryptos)


@bp.get("/<crypto_name>/get-rate")
@login_required
def get_source_rate(crypto_name):
    fiat = "USD"
    rate = ExchangeRate.get(fiat, crypto_name)
    current_rate = rate.get_rate()
    return {crypto_name: current_rate}


@bp.route("/payout/<crypto_name>")
@login_required
def payout(crypto_name):
    crypto = Crypto.instances[crypto_name]
    pdest = PayoutDestination.query.filter_by(crypto=crypto_name)

    try:
        fee_deposit_qrcode = segno.make(str(crypto.fee_deposit_account.addr))
    except Exception as e:
        fee_deposit_qrcode = None

    tmpl = "wallet/payout.j2"
    if isinstance(crypto, TronToken):
        tmpl = "wallet/payout_tron.j2"

    if isinstance(crypto, Ethereum) and crypto_name != "ETH":
        tmpl = "wallet/payout_eth.j2"

    if crypto_name in ["ETH", "BNB", "XRP", "MATIC", "AVAX", "SOL"]:
        tmpl = "wallet/payout_eth_coin.j2"

    if crypto_name in ["BTC"]:
        tmpl = "wallet/payout_btc_coin.j2"

    if "BTC-LIGHTNING" == crypto_name:
        tmpl = "wallet/payout_btc_lightning.j2"

    return render_template(
        tmpl, crypto=crypto, pdest=pdest, fee_deposit_qrcode=fee_deposit_qrcode
    )


@bp.route("/wallet/<crypto_name>")
@login_required
def manage(crypto_name):
    crypto = Crypto.instances[crypto_name]
    pdest = PayoutDestination.query.filter_by(crypto=crypto_name).all()
    wallet = Wallet.query.filter_by(crypto=crypto_name).first()

    server_templates = [
        f"wallet/manage_server_{cls.__name__.lower()}.j2"
        for cls in crypto.__class__.mro()
    ][:-2]

    def f(h):
        if not h:
            return 0, 1
        for period in [24 * 7, 24, 1]:
            if h % period == 0:
                return int(h / period), period

    recalc = {
        "periods": [
            {"name": "Hours", "hours": 1},
            {"name": "Days", "hours": 1 * 24},
            {"name": "Weeks", "hours": 1 * 24 * 7},
        ]
    }
    recalc["num"], recalc["multiplier"] = f(crypto.wallet.recalc)

    return render_template(
        "wallet/manage.j2",
        crypto=crypto,
        pdest=pdest,
        ppolicy=[i.value for i in PayoutPolicy],
        recalc=recalc,
        server_templates=server_templates,
    )


@bp.get("/rates", defaults={"fiat": "USD"})
@bp.get("/rates/<fiat>")
@login_required
def list_rates(fiat):
    cryptos = copy.deepcopy(Crypto.instances).values()
    for crypto in cryptos:
        rate = ExchangeRate.get(fiat, crypto.crypto)
        if rate.fee_policy is None:
            rate.fee_policy = FeeCalculationPolicy.PERCENT_FEE
            db.session.commit()
        crypto.rate = rate

    return render_template(
        "wallet/rates.j2",
        cryptos=cryptos,
        fiat=fiat,
        rate_providers=RateSource.instances.keys(),
        invoice_statuses=[status.name for status in InvoiceStatus],
        fee_calculation_policy=FeeCalculationPolicy,
    )


@bp.post("/rates", defaults={"fiat": "USD"})
@bp.post("/rates/<fiat>")
@login_required
def save_rates(fiat):
    rates = defaultdict(dict)
    for k, v in request.form.items():
        if k.startswith("rates__"):
            _, symbol, field = k.split("__")
            rates[symbol][field] = v
    for symbol, fields in rates.items():
        for k in fields:
            if k in ("rate", "fee", "fixed_fee"):
                try:
                    fields[k] = Decimal(fields[k])
                except InvalidOperation:
                    fields[k] = Decimal(0)

        # app.logger.info(fields)
        # do not save rate from dynamic rate providers
        if fields["source"] != "manual":
            del fields["rate"]

        ExchangeRate.query.filter_by(crypto=symbol, fiat=fiat).update(fields)
    db.session.commit()
    return redirect(url_for("wallet.list_rates"))


@bp.get("/transactions")
@login_required
def transactions():
    return render_template(
        "wallet/transactions.j2",
        cryptos=Crypto.instances.keys(),
        invoice_statuses=[status.name for status in InvoiceStatus],
    )


@bp.get("/parts/transactions")
@login_required
def parts_transactions():
    query = Transaction.query

    # app.logger.info(dir(query))

    for arg in request.args:
        if hasattr(Transaction, arg):
            field = getattr(Transaction, arg)
            if isinstance(field, property):
                continue
            else:
                query = query.filter(field.contains(request.args[arg]))

    if "addr" in request.args:
        query = (
            query.join(Invoice)
            .join(InvoiceAddress, isouter=True)
            .filter(
                Invoice.addr.contains(request.args["addr"])
                | InvoiceAddress.addr.contains(request.args["addr"])
            )
        )

    if "invoice_amount_crypto" in request.args:
        query = query.join(Invoice).filter(
            Invoice.amount_crypto.contains(request.args["invoice_amount_crypto"])
        )

    if "status" in request.args:
        query = query.join(Invoice).filter(
            Invoice.status.contains(request.args["status"])
        )

    if "external_id" in request.args:
        query = query.join(Invoice).filter(
            Invoice.external_id.contains(request.args["external_id"])
        )

    if "from_date" in request.args:
        query = query.filter(
            Transaction.created_at >= f"{request.args['from_date']} 00:00:00",
            Transaction.created_at <= f"{request.args['to_date']} 24:00:00",
        )

    if "download" in request.args:
        if "csv" == request.args["download"]:

            def generate():
                data = StringIO()
                w = csv.writer(data)
                w.writerow(
                    [
                        "Transaction ID",
                        "Adress",
                        "Crypto",
                        "Amount",
                        "Amount $",
                        "Status",
                        "Date",
                        "External ID",
                        "Invoice Coin",
                        "Invoice $",
                        "Invoice Date",
                    ]
                )
                records = query.order_by(Transaction.id.desc()).all()
                for r in records:
                    if r.invoice.status.name == "OUTGOING":
                        w.writerow(
                            [
                                r.txid,
                                r.invoice.addr,
                                r.crypto,
                                r.amount_crypto,
                                r.amount_fiat,
                                r.invoice.status.name,
                                r.created_at,
                                "",
                                "",
                                "",
                                "",
                            ]
                        )
                    else:
                        w.writerow(
                            [
                                r.txid,
                                r.invoice.addr,
                                r.crypto,
                                r.amount_crypto,
                                r.amount_fiat,
                                r.invoice.status.name,
                                r.created_at,
                                r.invoice.external_id,
                                r.invoice.amount_crypto,
                                r.invoice.amount_fiat,
                                r.invoice.created_at,
                            ]
                        )
                    yield data.getvalue()
                    data.seek(0)
                    data.truncate(0)

            response = Response(generate(), mimetype="text/csv")
            response.headers.set(
                "Content-Disposition", "attachment", filename="transactions.csv"
            )

        return response

    pagination = query.order_by(Transaction.id.desc()).paginate(per_page=50)
    return render_template(
        "wallet/transactions_table.j2",
        cryptos=Crypto.instances.keys(),
        invoice_statuses=[status.name for status in InvoiceStatus],
        txs=pagination.items,
        pagination=pagination,
    )


@bp.route("/payouts")
@login_required
def payouts():
    return render_template(
        "wallet/payouts.j2",
        cryptos=Crypto.instances.keys(),
        payout_statuses=[status.name for status in PayoutStatus],
        payout_tx_statuses=[status.name for status in PayoutTxStatus],
    )


@bp.get("/parts/payouts")
@login_required
def parts_payouts():
    query = Payout.query

    for arg in request.args:
        if hasattr(Payout, arg):
            field = getattr(Payout, arg)
            query = query.filter(field.contains(request.args[arg]))

    if "from_date" in request.args:
        query = query.filter(
            Payout.created_at >= f"{request.args['from_date']} 00:00:00",
            Payout.created_at <= f"{request.args['to_date']} 24:00:00",
        )

    if "txid" in request.args:
        query = query.join(PayoutTx).filter(
            PayoutTx.txid.contains(request.args["txid"])
        )

    if "download" in request.args:
        if "csv" == request.args["download"]:

            def generate():
                data = StringIO()
                w = csv.writer(data)
                w.writerow(["Date", "Destination", "Amount", "Crypto", "Tx ID"])
                records = query.order_by(Payout.id.desc()).all()
                for r in records:
                    w.writerow(
                        [
                            r.created_at,
                            r.dest_addr,
                            r.amount,
                            r.crypto,
                            " ".join([tx.txid for tx in r.transactions]),
                        ]
                    )
                    yield data.getvalue()
                    data.seek(0)
                    data.truncate(0)

            response = Response(generate(), mimetype="text/csv")
            response.headers.set(
                "Content-Disposition", "attachment", filename="payouts.csv"
            )

        return response

    pagination = query.order_by(Payout.id.desc()).paginate(per_page=50)
    return render_template(
        "wallet/payouts_table.j2",
        payouts=pagination.items,
        pagination=pagination,
    )


@bp.route("/parts/tron-multiserver", methods=("GET", "POST"))
@login_required
def parts_tron_multiserver():
    if cryptos := filter(lambda x: isinstance(x, TronToken), Crypto.instances.values()):
        any_tron_crypto = next(cryptos)
    else:
        return "No Tron crypto found."

    if request.method == "POST":
        any_tron_crypto.multiserver_set_server(request.args["server_id"])

    servers_status = any_tron_crypto.servers_status()
    return render_template(
        "wallet/configure/tron/main__multiserver_table.j2",
        servers_status=servers_status,
    )


@bp.route("/configure/tron", methods=("GET", "POST"))
@login_required
def configure_tron():
    if cryptos := filter(lambda x: isinstance(x, TronToken), Crypto.instances.values()):
        any_tron_crypto: TronToken = next(cryptos)
    else:
        return "No Tron crypto found."

    account_info = any_tron_crypto.get_account_info()
    tron_config = any_tron_crypto.get_staking_config()

    if (
        not tron_config["fee_deposit_account"]["is_active"]
        or not tron_config["energy_delegator_account"]["is_active"]
    ):
        fee_deposit_qrcode = energy_delegator_qrcode = None
        try:
            fee_deposit_qrcode = segno.make(
                tron_config["fee_deposit_account"]["address"]
            )
            energy_delegator_qrcode = segno.make(
                tron_config["energy_delegator_account"]["address"]
            )
        except Exception:
            pass
        return render_template(
            "wallet/configure/tron/activation.j2",
            i=account_info,
            config=tron_config,
            fee_deposit_qrcode=fee_deposit_qrcode,
            energy_delegator_qrcode=energy_delegator_qrcode,
        )

    return render_template(
        "wallet/configure/tron/main.j2",
        i=account_info,
        crypto=any_tron_crypto,
        tron_config=tron_config,
    )


@bp.get("/parts/tron-staking-stake")
@login_required
def get_parts_tron_staking_stake():
    # if cryptos := filter(lambda x: isinstance(x, TronToken), Crypto.instances.values()):
    #     any_tron_crypto: TronToken = next(cryptos)
    # else:
    #     return "No Tron crypto found."

    # account_info = any_tron_crypto.get_account_info()
    return render_template(
        "wallet/configure/tron/main__dialog_staking__stake.j2",
    )


@bp.post("/parts/tron-staking-stake")
@login_required
def post_parts_tron_staking_stake():
    tron: TronToken = next(
        filter(lambda x: isinstance(x, TronToken), Crypto.instances.values())
    )
    stake_result = tron.stake_trx(
        request.values.get("amount_trx"), request.values.get("resource")
    )
    return render_template(
        "wallet/configure/tron/main__dialog_staking__result.j2",
        stake_result=stake_result,
    )


@bp.get("/metrics")
@metrics_basic_auth
def metrics():
    metrics = ""

    # Crypto metrics
    seen = set()
    for crypto in Crypto.instances.values():
        if crypto.__class__.__base__ not in seen:
            try:
                metrics += crypto.metrics()
                seen.add(crypto.__class__.__base__)
            except AttributeError:
                continue

    # Shkeeper metrics
    metrics += prometheus_client.generate_latest().decode()

    return metrics


@bp.get("/unlock")
@login_required
def show_unlock():
    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.pending
    ):
        return render_template(
            "wallet/unlock_setup.j2", wallet_password=wallet_encryption
        )
    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.disabled
    ):
        return redirect(url_for("wallet.wallets"))
    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.enabled
    ):
        if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.pending:
            # render key input form
            return render_template(
                "wallet/unlock_key_input.j2", wallet_password=wallet_encryption
            )
        if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.fail:
            # render key input form with invalid key error
            flash("Invalid wallet encryption password, try again.", category="warning")
            return render_template(
                "wallet/unlock_key_input.j2", wallet_password=wallet_encryption
            )
        if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.success:
            # render 'wallets unlocked & redirect to /wallets after 2s'
            return render_template(
                "wallet/unlock_unlocked.j2", wallet_password=wallet_encryption
            )

    app.logger.info(
        f"show_unlock wallet_encryption.persistent_status: {wallet_encryption.persistent_status()}, wallet_encryption.runtime_status: {wallet_encryption.runtime_status()}"
    )


@bp.post("/unlock")
@login_required
def process_unlock():
    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.pending
    ):
        if request.form.get("encryption"):
            if not (key := request.form.get("key")):
                flash("No password provided.", "warning")
                return redirect(url_for("wallet.show_unlock"))

            if request.form.get("key") != request.form.get("key2"):
                flash(
                    "Encryption password and its confirmatios does not match.",
                    "warning",
                )
                return redirect(url_for("wallet.show_unlock"))

            if "confirmation" not in request.form:
                flash(
                    "Yoy must confirm that you saved the encryption password.",
                    "warning",
                )
                return redirect(url_for("wallet.show_unlock"))

            wallet_encryption.set_key(key)
            hash = wallet_encryption.get_hash(key)
            wallet_encryption.save_hash(hash)
            wallet_encryption.set_persistent_status(
                WalletEncryptionPersistentStatus.enabled
            )
        else:
            wallet_encryption.set_persistent_status(
                WalletEncryptionPersistentStatus.disabled
            )
        return redirect(url_for("wallet.show_unlock"))

    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.enabled
    ):
        key = request.form.get("key")
        if key_matches := wallet_encryption.test_key(key):
            wallet_encryption.set_key(key)
            wallet_encryption.set_runtime_status(WalletEncryptionRuntimeStatus.success)
        else:
            wallet_encryption.set_runtime_status(WalletEncryptionRuntimeStatus.fail)
        return redirect(url_for("wallet.show_unlock"))


# ============================================================================
# Admin Merchant Management Routes
# ============================================================================

@bp.route("/admin/merchants")
@login_required
def admin_merchants():
    """List all merchants for admin management."""
    merchants = Merchant.query.order_by(Merchant.created_at.desc()).all()

    # Calculate totals
    total_commission = db.session.query(db.func.sum(CommissionRecord.commission_amount)).scalar() or 0
    total_merchants = Merchant.query.count()
    active_merchants = Merchant.query.filter_by(status=MerchantStatus.ACTIVE).count()

    return render_template(
        "admin/merchants.j2",
        merchants=merchants,
        total_commission=total_commission,
        total_merchants=total_merchants,
        active_merchants=active_merchants,
    )


@bp.route("/admin/merchants/<int:merchant_id>")
@login_required
def admin_merchant_detail(merchant_id):
    """View merchant details."""
    merchant = Merchant.query.get_or_404(merchant_id)
    platform_settings = PlatformSettings.get()
    balances = MerchantBalance.query.filter_by(merchant_id=merchant_id).all()
    recent_invoices = Invoice.query.filter_by(merchant_id=merchant_id).order_by(Invoice.created_at.desc()).limit(10).all()
    recent_payouts = MerchantPayout.query.filter_by(merchant_id=merchant_id).order_by(MerchantPayout.created_at.desc()).limit(10).all()

    # Calculate stats
    total_invoices = Invoice.query.filter_by(merchant_id=merchant_id).count()
    paid_invoices = Invoice.query.filter_by(merchant_id=merchant_id).filter(
        Invoice.status.in_([InvoiceStatus.PAID, InvoiceStatus.PAID_EXPIRED])
    ).count()
    total_volume = db.session.query(db.func.sum(Invoice.fiat)).filter(
        Invoice.merchant_id == merchant_id,
        Invoice.status.in_([InvoiceStatus.PAID, InvoiceStatus.PAID_EXPIRED])
    ).scalar() or 0
    commission_earned = db.session.query(db.func.sum(CommissionRecord.commission_amount)).filter_by(
        merchant_id=merchant_id
    ).scalar() or 0

    stats = {
        "total_invoices": total_invoices,
        "paid_invoices": paid_invoices,
        "total_volume": total_volume,
        "commission_earned": commission_earned,
    }

    return render_template(
        "admin/merchant_detail.j2",
        merchant=merchant,
        platform_settings=platform_settings,
        balances=balances,
        recent_invoices=recent_invoices,
        recent_payouts=recent_payouts,
        stats=stats,
    )


@bp.route("/admin/merchants/<int:merchant_id>/suspend", methods=["POST"])
@login_required
def admin_suspend_merchant(merchant_id):
    """Suspend a merchant."""
    merchant = Merchant.query.get_or_404(merchant_id)
    merchant.status = MerchantStatus.SUSPENDED
    db.session.commit()
    flash(f"Merchant '{merchant.name}' has been suspended.")
    return redirect(url_for("wallet.admin_merchants"))


@bp.route("/admin/merchants/<int:merchant_id>/activate", methods=["POST"])
@login_required
def admin_activate_merchant(merchant_id):
    """Activate/reactivate a merchant."""
    merchant = Merchant.query.get_or_404(merchant_id)
    merchant.status = MerchantStatus.ACTIVE
    db.session.commit()
    flash(f"Merchant '{merchant.name}' has been activated.")
    return redirect(url_for("wallet.admin_merchants"))


@bp.route("/admin/settings", methods=["GET", "POST"])
@login_required
def admin_platform_settings():
    """Manage platform settings (commission, etc.)."""
    settings = PlatformSettings.get()

    if request.method == "POST":
        try:
            settings.default_commission_percent = Decimal(request.form.get("commission_percent", "2.0"))
            settings.default_commission_fixed = Decimal(request.form.get("commission_fixed", "0"))
            settings.min_payout_amount = Decimal(request.form.get("min_payout", "50"))
            settings.auto_approve_merchants = request.form.get("auto_approve") == "on"
            db.session.commit()
            flash("Platform settings updated successfully.")
        except (InvalidOperation, ValueError) as e:
            flash(f"Invalid value: {e}")

        return redirect(url_for("wallet.admin_platform_settings"))

    return render_template("admin/platform_settings.j2", settings=settings)


@bp.route("/admin/commissions")
@login_required
def admin_commissions():
    """View commission reports."""
    from datetime import datetime, timedelta

    page = request.args.get("page", 1, type=int)
    per_page = 50

    query = CommissionRecord.query

    # Apply filters
    merchant_id = request.args.get("merchant_id", type=int)
    crypto = request.args.get("crypto")
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    if merchant_id:
        query = query.filter_by(merchant_id=merchant_id)
    if crypto:
        query = query.filter_by(crypto=crypto)
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d")
            query = query.filter(CommissionRecord.created_at >= from_dt)
        except ValueError:
            pass
    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%Y-%m-%d")
            query = query.filter(CommissionRecord.created_at <= to_dt)
        except ValueError:
            pass

    records = query.order_by(CommissionRecord.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Calculate stats
    total_commission = db.session.query(db.func.sum(CommissionRecord.commission_amount)).scalar() or 0
    total_records = CommissionRecord.query.count()

    # This month
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_commission = db.session.query(db.func.sum(CommissionRecord.commission_amount)).filter(
        CommissionRecord.created_at >= month_start
    ).scalar() or 0

    # Today
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_commission = db.session.query(db.func.sum(CommissionRecord.commission_amount)).filter(
        CommissionRecord.created_at >= today_start
    ).scalar() or 0

    stats = {
        "total_commission": total_commission,
        "month_commission": month_commission,
        "today_commission": today_commission,
        "total_records": total_records,
    }

    # Get all merchants for filter dropdown
    merchants = Merchant.query.order_by(Merchant.name).all()

    return render_template(
        "admin/commissions.j2",
        records=records,
        stats=stats,
        merchants=merchants,
    )


@bp.route("/admin/payouts")
@login_required
def admin_merchant_payouts():
    """View and manage merchant payout requests."""
    status_filter = request.args.get("status")
    merchant_id = request.args.get("merchant_id", type=int)
    crypto = request.args.get("crypto")
    page = request.args.get("page", 1, type=int)
    per_page = 50

    query = MerchantPayout.query

    if status_filter:
        try:
            status = MerchantPayoutStatus(status_filter)
            query = query.filter_by(status=status)
        except ValueError:
            pass
    if merchant_id:
        query = query.filter_by(merchant_id=merchant_id)
    if crypto:
        query = query.filter_by(crypto=crypto)

    payouts = query.order_by(MerchantPayout.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Calculate stats
    pending_payouts = MerchantPayout.query.filter_by(status=MerchantPayoutStatus.PENDING)
    processing_payouts = MerchantPayout.query.filter(
        MerchantPayout.status.in_([MerchantPayoutStatus.APPROVED, MerchantPayoutStatus.PROCESSING])
    )
    completed_payouts = MerchantPayout.query.filter_by(status=MerchantPayoutStatus.COMPLETED)
    failed_payouts = MerchantPayout.query.filter(
        MerchantPayout.status.in_([MerchantPayoutStatus.FAILED, MerchantPayoutStatus.REJECTED])
    )

    stats = {
        "pending_count": pending_payouts.count(),
        "pending_amount": db.session.query(db.func.sum(MerchantPayout.amount_fiat)).filter(
            MerchantPayout.status == MerchantPayoutStatus.PENDING
        ).scalar() or 0,
        "processing_count": processing_payouts.count(),
        "processing_amount": db.session.query(db.func.sum(MerchantPayout.amount_fiat)).filter(
            MerchantPayout.status.in_([MerchantPayoutStatus.APPROVED, MerchantPayoutStatus.PROCESSING])
        ).scalar() or 0,
        "completed_count": completed_payouts.count(),
        "completed_amount": db.session.query(db.func.sum(MerchantPayout.amount_fiat)).filter(
            MerchantPayout.status == MerchantPayoutStatus.COMPLETED
        ).scalar() or 0,
        "failed_count": failed_payouts.count(),
    }

    # Get all merchants for filter dropdown
    merchants = Merchant.query.order_by(Merchant.name).all()

    return render_template(
        "admin/merchant_payouts.j2",
        payouts=payouts,
        stats=stats,
        merchants=merchants,
        status_filter=status_filter,
    )


@bp.route("/admin/payouts/<int:payout_id>/approve", methods=["POST"])
@login_required
def admin_approve_payout(payout_id):
    """Approve a pending payout request."""
    payout = MerchantPayout.query.get_or_404(payout_id)

    if payout.status != MerchantPayoutStatus.PENDING:
        flash("This payout is not in pending status.")
        return redirect(url_for("wallet.admin_merchant_payouts"))

    payout.status = MerchantPayoutStatus.APPROVED
    db.session.commit()
    flash(f"Payout #{payout.id} has been approved.")
    return redirect(url_for("wallet.admin_merchant_payouts"))


@bp.route("/admin/payouts/<int:payout_id>/reject", methods=["POST"])
@login_required
def admin_reject_payout(payout_id):
    """Reject a payout request."""
    payout = MerchantPayout.query.get_or_404(payout_id)

    if payout.status not in (MerchantPayoutStatus.PENDING, MerchantPayoutStatus.APPROVED):
        flash("This payout cannot be rejected.")
        return redirect(url_for("wallet.admin_merchant_payouts"))

    # Return balance to merchant
    balance = MerchantBalance.query.filter_by(
        merchant_id=payout.merchant_id,
        crypto=payout.crypto
    ).first()
    if balance:
        balance.pending_balance = (balance.pending_balance or 0) - payout.amount_fiat
        balance.available_balance = (balance.available_balance or 0) + payout.amount_fiat

    payout.status = MerchantPayoutStatus.REJECTED
    payout.error_message = request.form.get("reason", "Rejected by admin")
    db.session.commit()
    flash(f"Payout #{payout.id} has been rejected.")
    return redirect(url_for("wallet.admin_merchant_payouts"))


@bp.route("/admin/payouts/<int:payout_id>/process", methods=["POST"])
@login_required
def admin_process_payout(payout_id):
    """Process an approved payout - sends crypto to merchant."""
    from shkeeper.merchant_payout_service import process_payout

    payout = MerchantPayout.query.get_or_404(payout_id)

    if payout.status != MerchantPayoutStatus.APPROVED:
        flash("This payout must be approved before processing.")
        return redirect(url_for("wallet.admin_merchant_payouts"))

    success, message = process_payout(payout_id)

    if success:
        flash(f"Payout #{payout.id} completed successfully. {message}")
    else:
        flash(f"Payout #{payout.id} failed: {message}")

    return redirect(url_for("wallet.admin_merchant_payouts"))


@bp.route("/admin/payouts/<int:payout_id>/retry", methods=["POST"])
@login_required
def admin_retry_payout(payout_id):
    """Retry a failed payout."""
    payout = MerchantPayout.query.get_or_404(payout_id)

    if payout.status != MerchantPayoutStatus.FAILED:
        flash("Only failed payouts can be retried.")
        return redirect(url_for("wallet.admin_merchant_payouts"))

    payout.status = MerchantPayoutStatus.APPROVED
    payout.error_message = None
    db.session.commit()
    flash(f"Payout #{payout.id} has been queued for retry.")
    return redirect(url_for("wallet.admin_merchant_payouts"))


@bp.route("/admin/merchants/<int:merchant_id>/commission", methods=["POST"])
@login_required
def admin_update_merchant_commission(merchant_id):
    """Update a merchant's commission settings."""
    merchant = Merchant.query.get_or_404(merchant_id)

    try:
        commission_percent = request.form.get("commission_percent", "").strip()
        commission_fixed = request.form.get("commission_fixed", "").strip()

        merchant.commission_percent = Decimal(commission_percent) if commission_percent else None
        merchant.commission_fixed = Decimal(commission_fixed) if commission_fixed else Decimal(0)
        db.session.commit()
        flash(f"Commission settings updated for '{merchant.name}'.")
    except (InvalidOperation, ValueError) as e:
        flash(f"Invalid value: {e}")

    return redirect(url_for("wallet.admin_merchant_detail", merchant_id=merchant_id))


@bp.route("/admin/commissions/export")
@login_required
def admin_export_commissions():
    """Export commission records to CSV."""
    from datetime import datetime

    query = CommissionRecord.query

    # Apply filters
    merchant_id = request.args.get("merchant_id", type=int)
    crypto = request.args.get("crypto")
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    if merchant_id:
        query = query.filter_by(merchant_id=merchant_id)
    if crypto:
        query = query.filter_by(crypto=crypto)
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d")
            query = query.filter(CommissionRecord.created_at >= from_dt)
        except ValueError:
            pass
    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%Y-%m-%d")
            query = query.filter(CommissionRecord.created_at <= to_dt)
        except ValueError:
            pass

    records = query.order_by(CommissionRecord.created_at.desc()).all()

    # Build CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Merchant", "Invoice ID", "TX Hash", "Currency", "Gross Amount", "Commission %", "Commission Fixed", "Commission Amount", "Date"])

    for record in records:
        merchant_name = record.merchant.name if record.merchant else "N/A"
        writer.writerow([
            record.id,
            merchant_name,
            record.invoice_id or "",
            record.tx_hash or "",
            record.crypto,
            f"{record.gross_amount:.2f}",
            f"{record.commission_percent:.2f}",
            f"{record.commission_fixed:.2f}" if record.commission_fixed else "0.00",
            f"{record.commission_amount:.2f}",
            record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else "",
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=commissions_{datetime.now().strftime('%Y%m%d')}.csv"}
    )
