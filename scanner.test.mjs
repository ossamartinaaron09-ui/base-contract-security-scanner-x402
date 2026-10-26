import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {VAULT, USDC, requestAudit, interpret} from './scanner.mjs';
const quote = () => ({vault_evm_base: VAULT, usdc_contract_base: USDC,
  target_contract: USDC, accepted_token: 'USDC (Base Mainnet)', price_usdc: 0.5});

test('real HTTP quote sends target and no payment header', async () => {
  let seen;
  const server = http.createServer((req, res) => {
    seen = req; res.writeHead(402, {'Content-Type': 'application/json'}); res.end(JSON.stringify(quote()));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const result = interpret(await requestAudit({baseUrl: `http://127.0.0.1:${server.address().port}`}));
    assert.equal(result.exitCode, 2); assert.equal(result.output.payment_sent, false);
    assert.equal(seen.headers['x-payment-tx'], undefined);
    assert.equal(new URL(seen.url, 'http://localhost').searchParams.get('address'), USDC);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});

test('rejects altered quote fields and amount', () => {
  for (const [key, value] of [['vault_evm_base', '0x' + '0'.repeat(40)],
      ['usdc_contract_base', 'other'], ['target_contract', 'other'],
      ['accepted_token', 'USDT'], ['price_usdc', 1], ['price_usdc', 'NaN']]) {
    assert.throws(() => interpret({status: 402, payload: {...quote(), [key]: value}}));
  }
});

test('report must match requested transaction and target', () => {
  const txHash = '0x' + 'a'.repeat(64);
  const good = {payment_status: 'VERIFIED_ON_CHAIN', tx_hash: txHash, audit_report: {address: USDC}};
  assert.equal(interpret({status: 200, payload: good}, {txHash}).exitCode, 0);
  assert.throws(() => interpret({status: 200, payload: {...good, audit_report: {error: 'RPC failed'}}}, {txHash}));
  assert.throws(() => interpret({status: 200, payload: good}, {txHash: '0x' + 'b'.repeat(64)}));
  assert.throws(() => interpret({status: 403, payload: {error: 'Payment rejected'}}, {txHash}));
});

test('rejects malformed inputs before networking', async () => {
  for (const options of [{address: '0xNO'}, {txHash: 'secret'}, {timeout: Infinity},
      {baseUrl: 'http://user:pass@example.org'}]) await assert.rejects(requestAudit(options));
});

test('non-JSON server error fails explicitly', async () => {
  const server = http.createServer((req, res) => { res.writeHead(502); res.end('<html>Unavailable</html>'); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try { await assert.rejects(requestAudit({baseUrl: `http://127.0.0.1:${server.address().port}`}), /non-JSON/); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});
