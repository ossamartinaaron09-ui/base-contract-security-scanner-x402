#!/usr/bin/env node
/** Dependency-free Node 18+ client for the gateway's transaction-hash protocol. */
import {pathToFileURL} from 'node:url';

export const VAULT = '0xbefe9ce194a3d685486e5fda11c5221146de4d6c';
export const USDC = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913';
const MAX_RESPONSE = 1048576;

export async function requestAudit({baseUrl = 'http://185.166.214.127:8402',
  address = USDC, txHash, timeout = 15000} = {}) {
  const url = new URL(baseUrl);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      url.search || url.hash || !['', '/'].includes(url.pathname)) {
    throw new Error('Base URL must be an HTTP(S) origin without credentials or path');
  }
  if (!/^0x[0-9a-fA-F]{40}$/.test(address)) throw new Error('Invalid EVM address');
  if (txHash !== undefined && !/^0x[0-9a-fA-F]{64}$/.test(txHash)) throw new Error('Invalid transaction hash');
  if (!Number.isFinite(timeout) || timeout <= 0) throw new Error('Timeout must be positive and finite');
  url.pathname = '/api/audit-contract';
  url.searchParams.set('address', address);
  const headers = {Accept: 'application/json', 'User-Agent': 'BaseAuditClient/1.0'};
  if (txHash) headers['X-PAYMENT-TX'] = txHash;
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), timeout);
  try {
    const response = await fetch(url, {headers, signal: abort.signal, redirect: 'error'});
    const chunks = []; let bytes = 0;
    for await (const chunk of response.body) {
      bytes += chunk.byteLength;
      if (bytes > MAX_RESPONSE) { abort.abort(); throw new Error('Response exceeds 1 MiB'); }
      chunks.push(chunk);
    }
    let payload;
    try { payload = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
    catch { throw new Error(`Gateway returned non-JSON data (HTTP ${response.status})`); }
    if (!payload || Array.isArray(payload) || typeof payload !== 'object') throw new Error('Response must be a JSON object');
    return {status: response.status, payload};
  } finally { clearTimeout(timer); }
}

export function interpret({status, payload}, {address = USDC, txHash, maximum = 0.5} = {}) {
  if (status === 402) {
    const price = Number(payload.price_usdc);
    if (String(payload.vault_evm_base).toLowerCase() !== VAULT ||
        String(payload.usdc_contract_base).toLowerCase() !== USDC ||
        String(payload.target_contract).toLowerCase() !== address.toLowerCase() ||
        payload.accepted_token !== 'USDC (Base Mainnet)') throw new Error('Unexpected recipient, token, network or target');
    if (!Number.isFinite(price) || !Number.isFinite(maximum) || price <= 0 || price > maximum)
      throw new Error('Quote exceeds ceiling or has an invalid price');
    return {exitCode: 2, output: {result: 'PAYMENT_REQUIRED', http_status: 402,
      price_usdc: price, recipient: VAULT, token_contract: USDC, network: 'Base (8453)',
      target_contract: address, payment_sent: false,
      note: 'Quote only. No signing, transfer, or income verification.'}};
  }
  if (status !== 200) throw new Error(`Gateway HTTP ${status}: ${payload.error || 'request failed'}`);
  const report = payload.audit_report;
  if (!txHash || payload.payment_status !== 'VERIFIED_ON_CHAIN' ||
      String(payload.tx_hash).toLowerCase() !== txHash.toLowerCase() ||
      !report || typeof report !== 'object' || Array.isArray(report) || report.error ||
      String(report.address).toLowerCase() !== address.toLowerCase()) throw new Error('No matching completed report');
  return {exitCode: 0, output: {http_status: 200, response: payload,
    report_source: 'gateway; not independently verified',
    warning: 'Bytecode heuristics do not establish security or detect honeypots reliably.'}};
}

export async function main(args = process.argv.slice(2)) {
  const options = {};
  const names = {'--base-url': 'baseUrl', '--address': 'address', '--tx-hash': 'txHash',
    '--timeout': 'timeout', '--max-price-usdc': 'maximum'};
  try {
    if (args.includes('--help')) {
      console.log('node scanner.mjs [--base-url ORIGIN] [--address 0xADDRESS] [--tx-hash 0xHASH] [--timeout SECONDS] [--max-price-usdc 0.50]');
      return 0;
    }
    for (let i = 0; i < args.length; i += 2) {
      if (!names[args[i]] || args[i + 1] === undefined) throw new Error(`Invalid option: ${args[i]}`);
      options[names[args[i]]] = args[i + 1];
    }
    if (options.timeout !== undefined) options.timeout = Number(options.timeout) * 1000;
    if (options.maximum !== undefined) options.maximum = Number(options.maximum);
    const result = interpret(await requestAudit(options), options);
    console.log(JSON.stringify(result.output, null, 2));
    return result.exitCode;
  } catch (error) {
    console.error(JSON.stringify({result: 'ERROR', detail: error.message}));
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) process.exitCode = await main();
