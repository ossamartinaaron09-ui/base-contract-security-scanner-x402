#!/usr/bin/env python3
"""Single-file client for the gateway's GET /api/audit-contract interface.

Uses only Python 3.9+ standard library. No signing or automatic payments.
Exit codes: 0 report returned, 2 payment quote, 1 error.
"""
import argparse
import http.client
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

VAULT = "0xbefe9ce194a3d685486e5fda11c5221146de4d6c"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
MAX_RESPONSE = 1_048_576


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_audit(base_url, address, tx_hash=None, timeout=15):
    parsed = urlsplit(base_url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        raise ValueError("base URL must be an HTTP(S) origin without credentials or path")
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise ValueError("address must contain exactly 40 hexadecimal digits after 0x")
    if tx_hash is not None and not re.fullmatch(r"0x[0-9a-fA-F]{64}", tx_hash):
        raise ValueError("transaction hash must contain 64 hexadecimal digits after 0x")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    headers = {"Accept": "application/json", "User-Agent": "AuditGatewayDemo/1.0"}
    if tx_hash:
        headers["X-PAYMENT-TX"] = tx_hash
    url = base_url.rstrip("/") + "/api/audit-contract?" + urlencode({"address": address})
    opener = build_opener(NoRedirects())
    try:
        response = opener.open(Request(url, headers=headers), timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(MAX_RESPONSE + 1)
        status = response.code
    if len(raw) > MAX_RESPONSE:
        raise ValueError("response exceeds 1 MiB")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("gateway returned non-JSON data (HTTP %s)" % status)
    if not isinstance(payload, dict):
        raise ValueError("gateway response must be a JSON object")
    return status, payload


def validate_quote(payload, address, maximum):
    if str(payload.get("vault_evm_base", "")).lower() != VAULT:
        raise ValueError("payment destination differs from the configured operator vault")
    if str(payload.get("usdc_contract_base", "")).lower() != USDC:
        raise ValueError("quote does not identify the expected Base USDC contract")
    if str(payload.get("target_contract", "")).lower() != address.lower():
        raise ValueError("quote is for a different target contract")
    if payload.get("accepted_token") != "USDC (Base Mainnet)":
        raise ValueError("quote specifies an unexpected token/network")
    try:
        price = Decimal(str(payload["price_usdc"]))
        maximum = Decimal(str(maximum))
    except (KeyError, InvalidOperation):
        raise ValueError("invalid quote price")
    if not price.is_finite() or not maximum.is_finite() or not 0 < price <= maximum:
        raise ValueError("price is invalid or exceeds the configured ceiling")
    return str(price)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://185.166.214.127:8402")
    parser.add_argument("--address", default=USDC)
    parser.add_argument("--tx-hash", help="hash of a payment you already made; never a private key")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--max-price-usdc", default="0.50")
    args = parser.parse_args(argv)
    try:
        status, payload = request_audit(args.base_url, args.address, args.tx_hash, args.timeout)
        if status == 402:
            price = validate_quote(payload, args.address, args.max_price_usdc)
            print(json.dumps({"http_status": 402, "result": "PAYMENT_REQUIRED",
                "price_usdc": price, "network": "Base (8453)", "recipient": VAULT,
                "token_contract": USDC, "target_contract": args.address,
                "payment_sent": False,
                "note": "Quote only. This client does not sign, send funds, or verify income."}, indent=2))
            return 2
        if status != 200:
            raise ValueError("gateway returned HTTP %s: %s" % (status, payload.get("error", "request failed")))
        report = payload.get("audit_report")
        if (not args.tx_hash or payload.get("payment_status") != "VERIFIED_ON_CHAIN"
                or str(payload.get("tx_hash", "")).lower() != args.tx_hash.lower()
                or not isinstance(report, dict) or report.get("error")
                or str(report.get("address", "")).lower() != args.address.lower()):
            raise ValueError("gateway did not return a matching completed report")
        print(json.dumps({"http_status": status, "report_source": "gateway; not independently verified",
            "warning": "Bytecode heuristics are not a security certification.",
            "response": payload}, indent=2))
        return 0
    except (ValueError, URLError, OSError, http.client.HTTPException) as error:
        print(json.dumps({"result": "ERROR", "detail": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
