import json
from decimal import Decimal

from shkeeper import requests
from shkeeper.modules.classes.rate_source import RateSource


class Coinbase(RateSource):
    name = "coinbase"

    def get_rate(self, fiat, crypto):
        # Normalize symbols to what Coinbase expects
        if fiat == "USD" and crypto in self.USDT_CRYPTOS:
            return Decimal(1.0)

        if crypto in self.USDC_CRYPTOS:
            crypto = "USDC"

        if crypto in self.BTC_CRYPTOS:
            crypto = "BTC"

        if crypto in self.FIRO_CRYPTOS:
            crypto = "FIRO"

        url = f"https://api.coinbase.com/v2/exchange-rates?currency={crypto}"
        answer = requests.get(url)
        if answer.status_code != requests.codes.ok:
            raise Exception(f"Can't get rate for {crypto} / {fiat}: HTTP {answer.status_code}")

        data = json.loads(answer.text)
        rates = data.get("data", {}).get("rates", {})

        # Prefer the requested fiat; fall back to USD if the requested key is missing
        if fiat in rates:
            return Decimal(rates[fiat])
        if fiat == "USD" and "USDT" in rates:
            # USDT closely tracks USD; use it as a backup
            return Decimal(rates["USDT"])

        raise Exception(f"Can't get rate for {crypto} / {fiat}: pair not found in Coinbase response")
