from decimal import Decimal
import traceback
from os import environ
from concurrent.futures import ThreadPoolExecutor
from operator import  itemgetter


from werkzeug.datastructures import Headers
from flask import Blueprint, jsonify, g
from flask import request
from flask import Response
from flask import stream_with_context
from shkeeper.modules.cryptos.btc import Btc
from flask import current_app as app
from flask.json import JSONDecoder
from flask_sqlalchemy import sqlalchemy
from shkeeper import requests

from shkeeper import db
from shkeeper.auth import basic_auth_optional, login_required, api_key_required
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.modules.classes.tron_token import TronToken
from shkeeper.modules.classes.ethereum import Ethereum
from shkeeper.modules.cryptos.bitcoin_lightning import BitcoinLightning
from shkeeper.modules.cryptos.monero import Monero
from shkeeper.modules.rates import RateSource
from shkeeper.models import *
from shkeeper.callback import send_notification, send_unconfirmed_notification
from shkeeper.utils import format_decimal
from shkeeper.wallet_encryption import (
    wallet_encryption,
    WalletEncryptionPersistentStatus,
    WalletEncryptionRuntimeStatus,
)
from shkeeper.exceptions import NotRelatedToAnyInvoice


bp = Blueprint("api_v1", __name__, url_prefix="/api/v1/")

# class DecimalJSONDecoder(JSONDecoder):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, parse_float=Decimal, **kwargs)

# bp.json_decoder = DecimalJSONDecoder


@bp.route("/crypto")
def list_crypto():
    filtered_list = []
    crypto_list = []
    disable_on_lags = app.config.get("DISABLE_CRYPTO_WHEN_LAGS")
    cryptos =  Crypto.instances.values()
    filtered_cryptos = []

    for crypto in cryptos:
        if crypto.wallet.enabled:
            filtered_cryptos.append(crypto)

    def get_crypto_status(crypto):
        return crypto, crypto.getstatus()

    with ThreadPoolExecutor() as executor:
        results = list(executor.map(get_crypto_status, filtered_cryptos))

    for crypto, status in results:
        if status == "Offline":
            continue
        if disable_on_lags and status != "Synced":
            continue
        filtered_list.append(crypto.crypto)
        crypto_list.append({
            "name": crypto.crypto,
            "display_name": crypto.display_name
        })

    return {
        "status": "success",
        "crypto": sorted(filtered_list),
        "crypto_list": sorted(crypto_list, key=itemgetter("name")),
    }


@bp.get("/<crypto_name>/generate-address")
@login_required
def generate_address(crypto_name):
    crypto = Crypto.instances[crypto_name]
    addr = crypto.mkaddr()
    return {"status": "success", "addr": addr}


@bp.post("/<crypto_name>/payment_request")
@api_key_required
def payment_request(crypto_name):
    try:
        try:
            crypto = Crypto.instances[crypto_name]
        except KeyError:
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable",
            }
        if not crypto.wallet.enabled:
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable",
            }
        if app.config.get("DISABLE_CRYPTO_WHEN_LAGS") and crypto.getstatus() != "Synced":
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable because of lagging",
            }

        req = request.get_json(force=True)
        # Multi-tenant: pass merchant_id if authenticated as merchant
        merchant_id = g.merchant.id if hasattr(g, 'merchant') and g.merchant else None
        invoice = Invoice.add(crypto=crypto, request=req, merchant_id=merchant_id)
        response = {
            "status": "success",
            **invoice.for_response(),
        }
        app.logger.info({"request": req, "response": response, "merchant_id": merchant_id})

    except Exception as e:
        app.logger.exception(f"Failed to create invoice for {req}")
        response = {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }

    return response

@bp.post("/<crypto_name>/quote")
@api_key_required
def get_crypto_quote(crypto_name):
    try:
        try:
            crypto = Crypto.instances[crypto_name]
        except KeyError:
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable",
            }
        if not crypto.wallet.enabled:
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable",
            }
        if app.config.get("DISABLE_CRYPTO_WHEN_LAGS") and crypto.getstatus() != "Synced":
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable because of lagging",
            }

        req = request.get_json(force=True)
        fiat = req.get("fiat")
        amount_str = req.get("amount")

        if not fiat or not amount_str:
            return {
                "status": "error",
                "message": "'fiat' and 'amount' are required fields.",
            }

        amount_fiat = Decimal(amount_str)
        rate = ExchangeRate.get(fiat, crypto.crypto)
        amount_crypto, exchange_rate = rate.convert(amount_fiat)

        return {
            "status": "success",
            "fiat": fiat,
            "amount_fiat": str(amount_fiat),
            "crypto": crypto.crypto,
            "amount_crypto": str(amount_crypto),
            "exchange_rate": str(exchange_rate),
        }

    except Exception as e:
        app.logger.exception("Failed to get crypto quote")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }

@bp.get("/<crypto_name>/payment-gateway")
@login_required
def payment_gateway_get_status(crypto_name):
    crypto = Crypto.instances[crypto_name]
    return {
        "status": "success",
        "enabled": crypto.wallet.enabled,
        "token": crypto.wallet.apikey,
    }


@bp.post("/<crypto_name>/payment-gateway")
@login_required
def payment_gateway_set_status(crypto_name):
    req = request.get_json(force=True)
    crypto = Crypto.instances[crypto_name]
    crypto.wallet.enabled = req["enabled"]
    db.session.commit()
    return {"status": "success"}


@bp.post("/<crypto_name>/payment-gateway/token")
@login_required
def payment_gateway_set_token(crypto_name):
    req = request.get_json(force=True)
    for crypto in Crypto.instances.values():
        crypto.wallet.apikey = req["token"]
    db.session.commit()
    return {"status": "success"}


@bp.post("/<crypto_name>/transaction")
@login_required
def add_transaction(crypto_name):
    try:
        tx = request.get_json(force=True)
        # app.logger.warning(type(r['amount']))
        # app.logger.warning(Decimal(r['amount']))

        crypto = Crypto.instances[crypto_name]
        t = Transaction.add(crypto, tx)

        response = {
            "status": "success",
            "id": t.id,
        }

    except Exception as e:
        raise e
        response = {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }

    return response


@bp.post("/<crypto_name>/payout_destinations")
@login_required
def payout_destinations(crypto_name):
    req = request.get_json(force=True)

    if req["action"] == "add":
        if not PayoutDestination.query.filter_by(
            crypto=crypto_name, addr=req["daddress"]
        ).all():
            pd = PayoutDestination(crypto=crypto_name, addr=req["daddress"])
            if req.get("comment"):
                pd.comment = req["comment"]
            db.session.add(pd)
            db.session.commit()
        return {"status": "success"}
    elif req["action"] == "delete":
        PayoutDestination.query.filter_by(addr=req["daddress"]).delete()
        db.session.commit()
        return {"status": "success"}
    elif req["action"] == "list":
        pd = PayoutDestination.query.filter_by(crypto=crypto_name).all()
        return {
            "status": "success",
            "payout_destinations": [{"addr": p.addr, "comment": p.comment} for p in pd],
        }
    else:
        return {"status": "error", "message": "Unknown action"}


@bp.post("/<crypto_name>/autopayout")
@login_required
def autopayout(crypto_name):
    req = request.get_json(force=True)

    if req["policy"] not in [i.value for i in PayoutPolicy]:
        return {"status": "error", "message": f"Unknown payout policy: {req['policy']}"}

    w = Wallet.query.filter_by(crypto=crypto_name).first()
    if autopayout_destination := req.get("add"):
        w.pdest = autopayout_destination
    if autopayout_fee := req.get("fee"):
        w.pfee = autopayout_fee
    w.ppolicy = PayoutPolicy(req["policy"])
    w.pcond = req["policyValue"]
    w.payout = req.get("policyStatus", True)
    w.llimit = req["partiallPaid"]
    w.ulimit = req["addedFee"]
    w.confirmations = req["confirationNum"]
    w.recalc = req["recalc"]

    db.session.commit()
    return {"status": "success"}


@bp.get("/<crypto_name>/status")
@login_required
def status(crypto_name):
    crypto = Crypto.instances[crypto_name]
    return {
        "name": crypto.crypto,
        "amount": format_decimal(crypto.balance()) if crypto.balance() else 0,
        "server": crypto.getstatus(),
    }


@bp.get("/<crypto_name>/balance")
@api_key_required
def balance(crypto_name):
    if crypto_name not in Crypto.instances.keys():
        return {"status": "error", 
                "message": f"Crypto {crypto_name} is not enabled"}
    crypto = Crypto.instances[crypto_name]
    fiat = "USD"
    rate = ExchangeRate.get(fiat, crypto_name)
    current_rate = rate.get_rate()
    crypto_amount = format_decimal(crypto.balance()) if crypto.balance() else 0

    return {
        "name": crypto.crypto,
        "display_name": crypto.display_name,
        "amount_crypto": crypto_amount,
        "rate": current_rate,
        "fiat": "USD",
        "amount_fiat": format_decimal(Decimal(crypto_amount) * Decimal(current_rate)),
        "server_status": crypto.getstatus(),
    }


@bp.post("/<crypto_name>/payout")
@basic_auth_optional
@login_required
def payout(crypto_name):
    try:
        req = request.get_json(force=True)
        crypto = Crypto.instances[crypto_name]
        amount = Decimal(req["amount"])
        res = crypto.mkpayout(
            req["destination"],
            amount,
            req["fee"],
        )
    except Exception as e:
        app.logger.exception("Payout error")
        return {"status": "error", "message": f"Error: {e}"}

    if "result" in res and res["result"]:
        idtxs = res["result"] if isinstance(res["result"], list) else [res["result"]]
        Payout.add(
            {"dest": req["destination"], "amount": amount, "txids": idtxs}, crypto_name
        )

    return res


@bp.post("/payoutnotify/<crypto_name>")
def payoutnotify(crypto_name):
    try:
        if "X-Shkeeper-Backend-Key" not in request.headers:
            app.logger.warning("No backend key provided")
            return {"status": "error", "message": "No backend key provided"}, 403

        crypto = Crypto.instances[crypto_name]
        bkey = environ.get(f"SHKEEPER_BTC_BACKEND_KEY", "shkeeper")
        if request.headers["X-Shkeeper-Backend-Key"] != bkey:
            app.logger.warning("Wrong backend key")
            return {"status": "error", "message": "Wrong backend key"}, 403

        data = request.get_json(force=True)
        app.logger.info(f"Payout notification: {data}")

        for p in data:
            # Handle legacy auto-payout system
            Payout.add(p, crypto_name)

            # Handle merchant payouts - update any PROCESSING payouts with matching destination
            if p.get("status") == "success" and p.get("dest") and p.get("txids"):
                processing_payouts = MerchantPayout.query.filter_by(
                    crypto=crypto_name,
                    dest_address=p["dest"],
                    status=MerchantPayoutStatus.PROCESSING
                ).all()

                for merchant_payout in processing_payouts:
                    tx_hash = p["txids"][0] if p["txids"] else None
                    if tx_hash:
                        merchant_payout.status = MerchantPayoutStatus.COMPLETED
                        merchant_payout.tx_hash = tx_hash
                        merchant_payout.error_message = None

                        # Update merchant balance
                        balance = MerchantBalance.query.filter_by(
                            merchant_id=merchant_payout.merchant_id,
                            crypto=crypto_name,
                            fiat=merchant_payout.fiat or "USD",
                        ).first()
                        if balance:
                            balance.pending_balance = (balance.pending_balance or Decimal(0)) - merchant_payout.amount_fiat
                            balance.total_paid_out = (balance.total_paid_out or Decimal(0)) + merchant_payout.amount_fiat

                        app.logger.info(
                            f"[MerchantPayout #{merchant_payout.id}] Completed via payoutnotify. TX: {tx_hash}"
                        )

                db.session.commit()

        return {"status": "success"}
    except Exception as e:
        app.logger.exception("Payout notify error")
        return {"status": "error", "message": f"Error: {e}"}


@bp.post("/walletnotify/<crypto_name>/<txid>")
def walletnotify(crypto_name, txid):
    try:
        if "X-Shkeeper-Backend-Key" not in request.headers:
            app.logger.warning("No backend key provided")
            return {"status": "error", "message": "No backend key provided"}, 403

        try:
            crypto = Crypto.instances[crypto_name]
        except KeyError:
            return {
                "status": "success",
                "message": f"Ignoring notification for {crypto_name}: crypto is not available for processing",
            }

        bkey = environ.get(f"SHKEEPER_BTC_BACKEND_KEY", "shkeeper")
        if request.headers["X-Shkeeper-Backend-Key"] != bkey:
            app.logger.warning("Wrong backend key")
            return {"status": "error", "message": "Wrong backend key"}, 403

        for addr, amount, confirmations, category in crypto.getaddrbytx(txid):
            try:
                if category not in ("send", "receive"):
                    app.logger.warning(
                        f"[{crypto.crypto}/{txid}] ignoring unknown category: {category}"
                    )
                    continue

                if category == "send":
                    Transaction.add_outgoing(crypto, txid)
                    continue

                if confirmations == 0:
                    app.logger.info(
                        f"[{crypto.crypto}/{txid}] TX has no confirmations yet (entered mempool)"
                    )

                    if app.config.get("UNCONFIRMED_TX_NOTIFICATION"):
                        utx = UnconfirmedTransaction.add(
                            crypto_name, txid, addr, amount
                        )
                        send_unconfirmed_notification(utx)

                    continue

                tx = Transaction.add(
                    crypto,
                    {
                        "txid": txid,
                        "addr": addr,
                        "amount": amount,
                        "confirmations": confirmations,
                    },
                )
                tx.invoice.update_with_tx(tx)
                UnconfirmedTransaction.delete(crypto_name, txid)
                app.logger.info(f"[{crypto.crypto}/{txid}] TX has been added to db")
                if not tx.need_more_confirmations:
                    send_notification(tx)
            except sqlalchemy.exc.IntegrityError as e:
                app.logger.warning(f"[{crypto.crypto}/{txid}] TX already exist in db")
                db.session.rollback()
        return {"status": "success"}
    except NotRelatedToAnyInvoice:
        app.logger.warning(f"Transaction {txid} is not related to any invoice")
        return {
            "status": "success",
            "message": "Transaction is not related to any invoice",
        }
    except Exception as e:
        app.logger.exception(
            f"Exception while processing transaction notification: {crypto_name}/{txid}"
        )
        return {
            "status": "error",
            "message": f"Exception while processing transaction notification: {traceback.format_exc()}.",
        }, 409


@bp.get("/<crypto_name>/decrypt")
def decrypt_key(crypto_name):
    try:
        if "X-Shkeeper-Backend-Key" not in request.headers:
            app.logger.warning("No backend key provided")
            return {"status": "error", "message": "No backend key provided"}, 403

        try:
            crypto = Crypto.instances[crypto_name]
        except KeyError:
            return {
                "status": "success",
                "message": f"Ignoring notification for {crypto_name}: crypto is not available for processing",
            }

        bkey = environ.get(f"SHKEEPER_BTC_BACKEND_KEY", "shkeeper")
        if request.headers["X-Shkeeper-Backend-Key"] != bkey:
            app.logger.warning("Wrong backend key")
            return {"status": "error", "message": "Wrong backend key"}, 403
    except Exception as e:
        return {
            "status": "error",
            "message": f"Exception while processing transaction notification: {traceback.format_exc()}.",
        }, 409

    return {
        "persistent_status": wallet_encryption.persistent_status().name,
        "runtime_status": wallet_encryption.runtime_status().name,
        "key": wallet_encryption.key(),
    }


@bp.get("/<crypto_name>/server")
@login_required
def get_server_details(crypto_name):
    crypto = Crypto.instances[crypto_name]
    usr, pwd = crypto.get_rpc_credentials()
    host = crypto.gethost()
    return {"status": "success", "key": f"{usr}:{pwd}", "host": host}


@bp.post("/<crypto_name>/server/key")
@login_required
def set_server_key(crypto_name):
    # TODO: implement
    return {"status": "error", "message": "not implemented yet"}


@bp.post("/<crypto_name>/server/host")
@login_required
def set_server_host(crypto_name):
    # TODO: implement
    return {"status": "error", "message": "not implemented yet"}


@bp.get("/<crypto_name>/backup")
@login_required
def backup(crypto_name):
    crypto = Crypto.instances[crypto_name]
    if isinstance(crypto, (TronToken, Ethereum, Monero, Btc, BitcoinLightning)):
        filename, content = crypto.dump_wallet()
        headers = Headers()
        headers.add("Content-Type", "application/json")
        headers.add("Content-Disposition", f'attachment; filename="{filename}"')
        return Response(content, headers=headers)

    url = crypto.dump_wallet()
    bkey = environ.get(f"SHKEEPER_BTC_BACKEND_KEY")
    req = requests.get(url, stream=True, headers={"X-SHKEEPER-BACKEND-KEY": bkey})
    headers = Headers()
    headers.add("Content-Type", req.headers["content-type"])
    # headers.add('Content-Disposition', req.headers['Content-Disposition'])
    fname = url.split("/")[-1]
    headers.add("Content-Disposition", f'attachment; filename="{fname}"')
    return Response(
        stream_with_context(req.iter_content(chunk_size=2048)), headers=headers
    )


@bp.post("/<crypto_name>/exchange-rate")
@login_required
def set_exchange_rate(crypto_name):
    req = request.get_json(force=True)
    rate_source = ExchangeRate.query.filter_by(
        crypto=crypto_name, fiat=req["fiat"]
    ).first()
    if not rate_source:
        return {
            "status": "error",
            "message": f"No rate configured for {crypto_name}/{req['fiat']}",
        }
    rate_source.source = req["source"]
    if rate_source.source == "manual":
        rate_source.rate = req["rate"]
    rate_source.fee = req["fee"]
    db.session.commit()
    return {"status": "success"}


@bp.get("/<crypto_name>/estimate-tx-fee/<amount>")
@login_required
def estimate_tx_fee(crypto_name, amount):
    crypto = Crypto.instances[crypto_name]
    return crypto.estimate_tx_fee(amount, address=request.args.get("address"))


@bp.get("/<crypto_name>/task/<id>")
@basic_auth_optional
@login_required
def get_task(crypto_name, id):
    crypto = Crypto.instances[crypto_name]
    return crypto.get_task(id)


@bp.post("/<crypto_name>/multipayout")
@basic_auth_optional
@login_required
def multipayout(crypto_name):
    try:
        payout_list = request.get_json(force=True)
        crypto = Crypto.instances[crypto_name]
    except Exception as e:
        app.logger.exception("Multipayout error")
        return {"status": "error", "message": f"Error: {e}"}
    return crypto.multipayout(payout_list)


@bp.get("/<crypto_name>/addresses")
@api_key_required
def list_addresses(crypto_name):
    try:
        addresses = Crypto.instances[crypto_name].get_all_addresses()
        return {"status": "success", "addresses": addresses}
    except Exception as e:
        app.logger.exception(f"Failed to list addresses for {crypto_name}")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@bp.get("/transactions", defaults={"crypto": None, "addr": None})
@bp.get("/transactions/<crypto>/<addr>")
@api_key_required
def list_transactions(crypto, addr):
    try:
        # Multi-tenant: filter by merchant if authenticated as merchant
        merchant_id = g.merchant.id if hasattr(g, 'merchant') and g.merchant else None

        if crypto is None or addr is None:
            # List all transactions
            confirmed_query = Transaction.query.join(Invoice)
            unconfirmed_query = UnconfirmedTransaction.query.join(Invoice)

            if merchant_id:
                confirmed_query = confirmed_query.filter(Invoice.merchant_id == merchant_id)
                unconfirmed_query = unconfirmed_query.filter(Invoice.merchant_id == merchant_id)

            transactions = (
                *confirmed_query.all(),
                *unconfirmed_query.all(),
            )
        else:
            # Filter by crypto and address
            confirmed = (
                Transaction.query.join(Invoice)
                .join(InvoiceAddress, isouter=True)
                .filter(Transaction.crypto == crypto)
                .filter((Invoice.addr == addr) | (InvoiceAddress.addr == addr))
            )
            unconfirmed = UnconfirmedTransaction.query.join(Invoice).filter(
                UnconfirmedTransaction.crypto == crypto,
                UnconfirmedTransaction.addr == addr
            )

            if merchant_id:
                confirmed = confirmed.filter(Invoice.merchant_id == merchant_id)
                unconfirmed = unconfirmed.filter(Invoice.merchant_id == merchant_id)

            transactions = (
                *confirmed.all(),
                *unconfirmed.all(),
            )
        return jsonify(
            status="success", transactions=[tx.to_json() for tx in transactions]
        )
    except Exception as e:
        app.logger.exception(f"Failed to list transactions")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@bp.get("/invoices", defaults={"external_id": None})
@bp.get("/invoices/<external_id>")
@api_key_required
def list_invoices(external_id):
    try:
        # Start with base query
        query = Invoice.query.filter(Invoice.status != InvoiceStatus.OUTGOING)

        # Multi-tenant: filter by merchant if authenticated as merchant
        if hasattr(g, 'merchant') and g.merchant:
            query = query.filter(Invoice.merchant_id == g.merchant.id)

        if external_id is not None:
            query = query.filter_by(external_id=external_id)

        invoices = query.all()
        return jsonify(status="success", invoices=[i.to_json() for i in invoices])
    except Exception as e:
        app.logger.exception(f"Failed to list invoices")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@bp.get("/invoice/<int:invoice_id>/status")
@api_key_required
def get_invoice_status(invoice_id):
    """
    Get the status of an invoice by its ID.

    Used by the payment widget to poll for payment status updates.

    Returns the invoice status directly in 'status' field for widget compatibility.
    The widget checks data.status for values like 'PAID', 'UNPAID', 'PARTIAL'.
    """
    try:
        # Build query
        query = Invoice.query.filter_by(id=invoice_id)

        # Multi-tenant: filter by merchant if authenticated as merchant
        if hasattr(g, 'merchant') and g.merchant:
            query = query.filter(Invoice.merchant_id == g.merchant.id)

        invoice = query.first()

        if not invoice:
            return {"status": "error", "message": "Invoice not found"}, 404

        # Return invoice status directly in 'status' field for widget compatibility
        # Widget checks: var status = (data.status || '').toUpperCase();
        return {
            "status": invoice.status.name if invoice.status else "UNPAID",
            "id": invoice.id,
            "amount_crypto": str(invoice.amount_crypto) if invoice.amount_crypto else None,
            "amount_fiat": str(invoice.amount_fiat) if invoice.amount_fiat else None,
            "balance_crypto": str(invoice.balance_crypto) if invoice.balance_crypto else "0",
            "balance_fiat": str(invoice.balance_fiat) if invoice.balance_fiat else "0",
            "crypto": invoice.crypto,
            "fiat": invoice.fiat,
            "addr": invoice.addr,
            "exchange_rate": str(invoice.exchange_rate) if invoice.exchange_rate else None,
        }
    except Exception as e:
        app.logger.exception(f"Failed to get invoice status for {invoice_id}")
        return {
            "status": "error",
            "message": str(e),
        }, 500


@bp.get("/<crypto_name>/payouts")
@api_key_required
def list_payouts(crypto_name):
    try:
        amount = request.args.get("amount")

        if not amount:
            raise Exception("No amount provided.")

        if Payout.query.filter_by(amount=amount).all():
            return {"status": "success"}
        else:
            return {
                "status": "error",
                "message": f"No payouts for {amount} {crypto_name} found.",
            }
    except Exception as e:
        app.logger.exception(f"Failed to check payouts for {amount} {crypto_name}")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@bp.get("/tx-info/<txid>/<external_id>")
@api_key_required
def get_txid_info(txid, external_id):
    try:
        # Multi-tenant: filter by merchant if authenticated as merchant
        merchant_id = g.merchant.id if hasattr(g, 'merchant') and g.merchant else None

        info = {}
        query = (
            Transaction.query.join(Invoice)
            .filter(Transaction.txid == txid, Invoice.external_id == external_id)
        )

        if merchant_id:
            query = query.filter(Invoice.merchant_id == merchant_id)

        if tx := query.first():
            info = {
                "crypto": tx.crypto,
                "amount": format_decimal(tx.amount_fiat),
                "addr": tx.addr,
            }
        return {"status": "success", "info": info}
    except Exception as e:
        app.logger.exception(f"Oops!")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@bp.post("/decryption-key")
@api_key_required
def decryption_key():
    if not (key := request.form.get("key")):
        return {"status": "error", "message": "Decryption key is requred"}
    if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.success:
        return {"status": "success", "message": "Decryption key was already entered"}
    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.enabled
    ):
        if wallet_encryption.test_key(key):
            wallet_encryption.set_key(key)
            wallet_encryption.set_runtime_status(WalletEncryptionRuntimeStatus.success)
            return {"status": "success"}
        else:
            return {"status": "error", "message": "Invalid decryption key"}
    else:
        return {"status": "error", "message": "Wallet is not encrypted"}


@bp.post("/test-callback-receiver")
@api_key_required
def test_callback_receiver():
    callback = request.get_json(force=True)
    app.logger.info("=============== Test callback received ===================")
    app.logger.info(callback)
    return {"status": "success", "message": "callback logged"}, 202


# ============================================================================
# Admin-only Merchant Payout Processing API
# ============================================================================

@bp.post("/admin/process-payouts")
@login_required
def process_pending_payouts():
    """
    Process all approved merchant payouts.

    This endpoint is intended to be called by a cron job or scheduler
    to automatically process approved payout requests.

    Requires admin authentication (login_required).
    """
    from shkeeper.merchant_payout_service import process_approved_payouts

    results = process_approved_payouts()

    successful = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]

    return {
        "status": "success",
        "processed": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "results": [
            {
                "payout_id": r[0],
                "success": r[1],
                "message": r[2]
            }
            for r in results
        ]
    }


@bp.get("/merchant/balance")
@api_key_required
def get_merchant_balance():
    """
    Get the authenticated merchant's current balances.

    Returns balance for each cryptocurrency the merchant has received payments in.
    """
    if not hasattr(g, 'merchant') or not g.merchant:
        return {"status": "error", "message": "Merchant authentication required"}, 401

    balances = MerchantBalance.query.filter_by(merchant_id=g.merchant.id).all()

    return {
        "status": "success",
        "balances": [
            {
                "crypto": b.crypto,
                "total_received": str(b.total_received or 0),
                "total_commission": str(b.total_commission or 0),
                "available_balance": str(b.available_balance or 0),
                "pending_balance": str(b.pending_balance or 0),
            }
            for b in balances
        ]
    }


@bp.post("/merchant/payout")
@api_key_required
def request_merchant_payout():
    """
    Request a payout for the authenticated merchant.

    JSON body:
    {
        "crypto": "BTC",          # Required: cryptocurrency to withdraw
        "amount": 100.00,         # Optional: amount in USD (0 or omit for full balance)
        "security_phrase": "..."  # Required: phrase set at registration
    }
    """
    if not hasattr(g, 'merchant') or not g.merchant:
        return {"status": "error", "message": "Merchant authentication required"}, 401

    merchant = g.merchant

    if merchant.status != MerchantStatus.ACTIVE:
        return {"status": "error", "message": "Merchant account is not active"}, 403

    req = request.get_json(force=True)
    security_phrase = req.get("security_phrase", "")
    if not security_phrase:
        return {
            "status": "error",
            "message": "Security phrase is required to request a payout."
        }, 400
    if merchant.security_phrase_hash:
        if not merchant.verify_security_phrase(str(security_phrase)):
            return {
                "status": "error",
                "message": "Invalid security phrase."
            }, 403
    else:
        merchant.security_phrase_hash = Merchant.hash_secret(str(security_phrase))
        db.session.commit()

    crypto = req.get("crypto")
    if not crypto:
        return {"status": "error", "message": "crypto is required"}, 400

    # Check payout address is configured
    payout_address = merchant.get_payout_address(crypto)
    if not payout_address:
        return {
            "status": "error",
            "message": f"No payout address configured for {crypto}. Please configure it in your merchant settings."
        }, 400

    # Get merchant's balance for this crypto (any fiat)
    fiat_requested = req.get("fiat")
    balances = [
        b for b in MerchantBalance.query.filter_by(merchant_id=merchant.id, crypto=crypto).all()
        if (b.available_balance or Decimal(0)) > 0
    ]

    balance = None
    if fiat_requested:
        balance = next(
            (b for b in balances if (b.fiat or "").upper() == str(fiat_requested).upper()),
            None,
        )
    if not balance and balances:
        balance = max(balances, key=lambda b: b.available_balance or Decimal(0))

    if not balance:
        return {"status": "error", "message": f"No available balance for {crypto}"}, 400

    # Determine amount
    requested_amount = Decimal(str(req.get("amount", 0)))
    if requested_amount <= 0:
        # Withdraw full balance
        amount = balance.available_balance
    else:
        if requested_amount > balance.available_balance:
            return {
                "status": "error",
                "message": f"Requested amount (${requested_amount}) exceeds available balance (${balance.available_balance})"
            }, 400
        amount = requested_amount

    # Check minimum payout
    platform_settings = PlatformSettings.get()
    min_payout = merchant.min_payout_amount or platform_settings.min_payout_amount or Decimal(50)
    if amount < min_payout:
        return {
            "status": "error",
            "message": f"Minimum payout amount is ${min_payout}"
        }, 400

    # Create payout request
    payout = MerchantPayout(
        merchant_id=merchant.id,
        crypto=crypto,
        fiat=balance.fiat or "USD",
        amount_fiat=amount,
        dest_address=payout_address,
        status=MerchantPayoutStatus.PENDING
    )
    db.session.add(payout)

    # Move amount from available to pending
    balance.available_balance = (balance.available_balance or Decimal(0)) - amount
    balance.pending_balance = (balance.pending_balance or Decimal(0)) + amount

    db.session.commit()

    return {
        "status": "success",
        "message": "Payout request submitted",
        "payout": {
            "id": payout.id,
            "crypto": payout.crypto,
            "amount_fiat": str(payout.amount_fiat),
            "dest_address": payout.dest_address,
            "status": payout.status.value
        }
    }


@bp.get("/merchant/payouts")
@api_key_required
def list_merchant_payouts():
    """
    List the authenticated merchant's payout requests.
    """
    if not hasattr(g, 'merchant') or not g.merchant:
        return {"status": "error", "message": "Merchant authentication required"}, 401

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    payouts = MerchantPayout.query.filter_by(
        merchant_id=g.merchant.id
    ).order_by(
        MerchantPayout.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return {
        "status": "success",
        "payouts": [
            {
                "id": p.id,
                "crypto": p.crypto,
                "fiat": p.fiat or "USD",
                "amount_fiat": str(p.amount_fiat),
                "amount_crypto": str(p.amount_crypto) if p.amount_crypto else None,
                "dest_address": p.dest_address,
                "status": p.status.value,
                "tx_hash": p.tx_hash,
                "error_message": p.error_message,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payouts.items
        ],
        "pagination": {
            "page": payouts.page,
            "per_page": payouts.per_page,
            "total": payouts.total,
            "pages": payouts.pages,
        }
    }
