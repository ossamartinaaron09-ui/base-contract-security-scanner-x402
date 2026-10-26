# Base contract security scanner — Python & Node.js HTTP 402 clients

Inspect the interface of a Base mainnet smart-contract bytecode screening service
from Python or Node.js. The gateway quotes **0.50 USDC on Base per report**.
The clients need no API key or registration and use no external dependencies.

**This is an experimental bytecode screening interface. It is not a comprehensive
security audit, a honeypot detector, or a guarantee that a token is safe to buy.**
Its transaction-hash payment interface is custom; standard x402 v2 compatibility
has not been established.

## Quick start

```sh
git clone https://github.com/ossamartinaaron09-ui/base-contract-security-scanner-x402.git
cd base-contract-security-scanner-x402
python3 scanner.py
# or Node.js 18+
node scanner.mjs
```

Both clients target `http://185.166.214.127:8402/api/audit-contract` by default,
using the Base USDC address as the sample contract. An unpaid request should
return HTTP 402 and a quote; exit status **2** means payment is required,
**1** means an error, and **0** means a matching report was returned.

**Reachability:** the 402 interface has been verified from within the server.
External access to port 8402 timed out during verification. Until that network
path is available, use a gateway you can access or an authorized SSH tunnel:

```sh
ssh -N -L 18402:127.0.0.1:8402 USER@YOUR_GATEWAY_HOST
python3 scanner.py --base-url http://127.0.0.1:18402
node scanner.mjs --base-url http://127.0.0.1:18402
```

## Inspect another Base contract

```sh
python3 scanner.py --address 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
node scanner.mjs --address 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
```

The clients check the quote's target, price ceiling, network, USDC contract and
operator destination. They **do not send money, approve tokens or sign messages**.
The default ceiling is 0.50 USDC. No private key is ever needed by either client.

## Existing payment receipt

For an independently arranged payment, the gateway accepts its transaction hash:

```sh
python3 scanner.py --address 0xYOUR_CONTRACT --tx-hash 0xYOUR_EXISTING_TRANSACTION_HASH
node scanner.mjs --address 0xYOUR_CONTRACT --tx-hash 0xYOUR_EXISTING_TRANSACTION_HASH
```

Replace both placeholders with complete hexadecimal values. The custom request
header is `X-PAYMENT-TX`. The returned verification status is the gateway's claim,
not an independent on-chain check by these clients. No paid end-to-end transaction
was performed in this repository's validation.

## What the gateway checks

The inspected implementation fetches deployed bytecode and looks for patterns
associated with DELEGATECALL, SELFDESTRUCT, CREATE2, token selectors and ownership
methods. Its substring matching can mistake embedded data for executable opcodes.
Selector presence does not prove behavior. Proxy implementation analysis,
sell-transaction simulation, liquidity analysis and honeypot detection are **not
implemented**. The payment handler also needs customer/request binding and replay
protection before production commercial reliance. These clients demonstrate the
API contract; they do not resolve those server limitations.

## Tests

```sh
python3 -m unittest -v
node --test scanner.test.mjs
```

Tests use local HTTP servers and fixtures, covering payment quotes, mismatched
destinations and reports, malformed inputs, and server errors. They transfer no funds.

## Payment destination

- Network: Base mainnet, chain ID 8453
- Asset: native USDC, `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`
- Operator: `0xbefe9ce194a3d685486e5fda11c5221146de4d6c`

This repository contains clients and documentation. It does not host the gateway,
fund a bounty, establish service availability, or demonstrate earned revenue.
