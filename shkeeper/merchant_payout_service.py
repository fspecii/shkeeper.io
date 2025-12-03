"""
Merchant Payout Service

Handles processing of merchant payout requests - converting fiat amounts to crypto
and sending to merchant's configured payout address.
"""
from decimal import Decimal
from flask import current_app as app

from shkeeper import db
from shkeeper.models import (
    MerchantPayout,
    MerchantPayoutStatus,
    MerchantBalance,
    Merchant,
    ExchangeRate,
    Transaction,
)
from shkeeper.modules.classes.crypto import Crypto


def get_crypto_amount_for_fiat(crypto_name: str, fiat_amount: Decimal) -> Decimal:
    """
    Convert a fiat amount (USD) to crypto amount using current exchange rate.

    Args:
        crypto_name: The cryptocurrency symbol (e.g., "BTC", "ETH")
        fiat_amount: The amount in fiat (USD)

    Returns:
        The equivalent amount in cryptocurrency
    """
    rate = ExchangeRate.get(crypto_name)
    if not rate or rate.rate <= 0:
        raise ValueError(f"No valid exchange rate found for {crypto_name}")

    crypto_amount = fiat_amount / rate.rate
    return crypto_amount


def process_payout(payout_id: int) -> tuple[bool, str]:
    """
    Process a merchant payout request.

    This function:
    1. Validates the payout is in APPROVED status
    2. Gets the merchant's payout address for the crypto
    3. Converts the fiat amount to crypto
    4. Sends the crypto to the merchant's address
    5. Updates the payout status and merchant balance

    Args:
        payout_id: The ID of the MerchantPayout to process

    Returns:
        Tuple of (success: bool, message: str)
    """
    payout = MerchantPayout.query.get(payout_id)
    if not payout:
        return False, f"Payout {payout_id} not found"

    if payout.status != MerchantPayoutStatus.APPROVED:
        return False, f"Payout {payout_id} is not in APPROVED status"

    merchant = Merchant.query.get(payout.merchant_id)
    if not merchant:
        return False, "Merchant not found"

    # Get merchant's payout address for this crypto
    dest_address = merchant.get_payout_address(payout.crypto)
    if not dest_address:
        payout.status = MerchantPayoutStatus.FAILED
        payout.error_message = f"No payout address configured for {payout.crypto}"
        db.session.commit()
        return False, payout.error_message

    # Get the crypto instance
    crypto = Crypto.instances.get(payout.crypto)
    if not crypto:
        payout.status = MerchantPayoutStatus.FAILED
        payout.error_message = f"Cryptocurrency {payout.crypto} not available"
        db.session.commit()
        return False, payout.error_message

    # Update status to processing
    payout.status = MerchantPayoutStatus.PROCESSING
    payout.dest_address = dest_address
    db.session.commit()

    try:
        # Convert fiat to crypto amount
        crypto_amount = get_crypto_amount_for_fiat(payout.crypto, payout.amount_fiat)

        app.logger.info(
            f"[MerchantPayout #{payout.id}] Processing payout: "
            f"${payout.amount_fiat} -> {crypto_amount} {payout.crypto} "
            f"to {dest_address}"
        )

        # Send the crypto
        # Note: Different crypto classes might have different send methods
        # Most bitcoin-like cryptos use sendtoaddress
        if hasattr(crypto, 'sendtoaddress'):
            response = crypto.sendtoaddress(
                destination=dest_address,
                amount=crypto_amount,
                subtract_fee_from_amount=True  # Fee comes from the payout amount
            )

            if response.get("error"):
                raise Exception(f"RPC error: {response['error']}")

            tx_hash = response.get("result")
            if not tx_hash:
                raise Exception("No transaction hash returned")

            # Success - update payout
            payout.status = MerchantPayoutStatus.COMPLETED
            payout.tx_hash = tx_hash
            payout.amount_crypto = crypto_amount
            payout.error_message = None

            # Deduct from pending balance (was moved there when payout was requested)
            balance = MerchantBalance.query.filter_by(
                merchant_id=merchant.id,
                crypto=payout.crypto
            ).first()
            if balance:
                balance.pending_balance = (balance.pending_balance or Decimal(0)) - payout.amount_fiat

            db.session.commit()

            app.logger.info(
                f"[MerchantPayout #{payout.id}] Successfully sent. TX: {tx_hash}"
            )

            # Track as outgoing transaction
            Transaction.add_outgoing(payout.crypto, tx_hash)

            return True, f"Payout completed. TX: {tx_hash}"

        else:
            # Crypto doesn't support sendtoaddress - mark as failed
            raise Exception(f"Cryptocurrency {payout.crypto} doesn't support automated payouts")

    except Exception as e:
        app.logger.error(
            f"[MerchantPayout #{payout.id}] Failed to process: {str(e)}"
        )
        payout.status = MerchantPayoutStatus.FAILED
        payout.error_message = str(e)
        db.session.commit()
        return False, str(e)


def process_approved_payouts():
    """
    Process all approved payouts. This can be called by a scheduler/cron job.

    Returns:
        List of (payout_id, success, message) tuples
    """
    results = []
    approved_payouts = MerchantPayout.query.filter_by(
        status=MerchantPayoutStatus.APPROVED
    ).all()

    for payout in approved_payouts:
        success, message = process_payout(payout.id)
        results.append((payout.id, success, message))

    return results
