import contextlib
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import scanner as client


class ClientTests(unittest.TestCase):
    def quote(self):
        return {"vault_evm_base": client.VAULT, "usdc_contract_base": client.USDC,
                "target_contract": client.USDC, "price_usdc": 0.5,
                "accepted_token": "USDC (Base Mainnet)"}

    def test_quote_rejects_changed_destination_token_target_and_price(self):
        for field, value in [("vault_evm_base", "0x" + "0" * 40),
                             ("usdc_contract_base", "0x" + "1" * 40),
                             ("target_contract", "0x" + "2" * 40),
                             ("accepted_token", "USDC (Ethereum)"),
                             ("price_usdc", 2), ("price_usdc", "NaN")]:
            quote = self.quote(); quote[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                client.validate_quote(quote, client.USDC, "0.50")

    def test_http_402_is_read_as_quote_without_payment_header(self):
        seen = []
        body = json.dumps(self.quote()).encode()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get("X-PAYMENT-TX")))
                self.send_response(402); self.end_headers(); self.wfile.write(body)
            def log_message(self, *args): pass
        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    result = client.main(["--base-url", "http://127.0.0.1:%s" % server.server_port])
                self.assertEqual(result, 2)
                self.assertFalse(json.loads(out.getvalue())["payment_sent"])
                self.assertTrue(seen[0][0].startswith("/api/audit-contract?address="))
                self.assertIsNone(seen[0][1])
            finally:
                server.shutdown(); thread.join()

    def test_report_matching_and_server_errors(self):
        tx = "0x" + "a" * 64
        good = {"payment_status": "VERIFIED_ON_CHAIN", "tx_hash": tx,
                "audit_report": {"address": client.USDC, "is_contract": True}}
        cases = [(200, good, 0), (200, {**good, "tx_hash": "0x" + "b" * 64}, 1),
                 (200, {**good, "audit_report": {"error": "RPC unavailable"}}, 1),
                 (403, {"error": "Payment Verification Failed"}, 1)]
        for status, payload, expected in cases:
            with self.subTest(status=status, payload=payload), patch.object(client, "request_audit", return_value=(status, payload)):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(client.main(["--tx-hash", tx]), expected)

    def test_rejects_invalid_input_before_network(self):
        for url, address, tx in [("https://user:pass@example.org", client.USDC, None),
                                 ("http://localhost:8402", "0xno", None),
                                 ("http://localhost:8402", client.USDC, "key")]:
            with self.assertRaises(ValueError):
                client.request_audit(url, address, tx)


if __name__ == "__main__":
    unittest.main()
