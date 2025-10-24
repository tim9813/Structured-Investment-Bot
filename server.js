// server.js (CommonJS, vi-friendly)
const express = require('express');
const { Pool } = require('pg');
require('dotenv').config();
const yf = require('yahoo-finance2').default;
const pino = require('pino');

// at the top of server.js, replace your yahoo import with:
const yf2 = require('yahoo-finance2');
const yf = yf2.default || yf2;   // works with both CJS/ESM builds

// basic logger
const logger = pino({ transport: { target: 'pino-pretty' }, level: 'info' });

const app = express();
app.use(express.json());

// optional DB (kept for future)
const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgres://appuser:StrongPass!@localhost:5432/appdb'
});

// In-memory caches to reduce Yahoo calls
const searchCache = new Map(); // key: q, value: {ts, data}
const quoteCache = new Map();  // key: symbol, value: {ts, data}
const now = () => Date.now();

// TTLs (ms)
const SEARCH_TTL = 60 * 60 * 1000;   // 1h
const QUOTE_TTL  = 15 * 1000;        // 15s (near real-time)

app.get('/api/ping', (req, res) => res.json({ ok: true, msg: 'pong' }));

app.get('/api/time', async (req, res) => {
  try {
    const r = await pool.query('select now()');
    res.json({ time: r.rows[0].now });
  } catch (e) {
    res.json({ time: new Date().toISOString(), note: 'db optional: ' + e.message });
  }
});

// --- Yahoo Finance: search by name/ticker ---
app.get('/api/stocks/search', async (req, res) => {
  try {
    const q = String(req.query.q || '').trim();
    if (!q) return res.json({ items: [] });

    const cached = searchCache.get(q);
    if (cached && (now() - cached.ts) < SEARCH_TTL) {
      return res.json({ items: cached.data });
    }

    const result = await yf.search(q, { quotesCount: 10, newsCount: 0, enableFuzzyQuery: true });
    const items = (result.quotes || [])
      .filter(x => x.symbol && (x.quoteType === 'EQUITY' || x.quoteType === 'ETF' || x.typeDisp))
      .map(x => ({
        symbol: x.symbol,
        shortname: x.shortname || '',
        longname: x.longname || '',
        exchange: x.exchange || x.exchDisp || '',
        type: x.quoteType || x.typeDisp || '',
      }));

    searchCache.set(q, { ts: now(), data: items });
    res.json({ items });
  } catch (e) {
    logger.error(e);
    res.status(500).json({ error: 'search_failed', message: e.message });
  }
});

// --- Yahoo Finance: get a quote for a symbol ---
app.get('/api/stocks/quote', async (req, res) => {
  try {
    const symbol = String(req.query.symbol || '').trim().toUpperCase();
    if (!symbol) return res.status(400).json({ error: 'missing_symbol' });

    const cached = quoteCache.get(symbol);
    if (cached && (now() - cached.ts) < QUOTE_TTL) {
      return res.json(cached.data);
    }

    const q = await yf.quote(symbol);
    const payload = {
      symbol: q.symbol,
      shortName: q.shortName,
      longName: q.longName,
      currency: q.currency,
      marketState: q.marketState,
      price: q.regularMarketPrice,
      change: q.regularMarketChange,
      changePercent: q.regularMarketChangePercent,
      previousClose: q.regularMarketPreviousClose,
      open: q.regularMarketOpen,
      high: q.regularMarketDayHigh,
      low: q.regularMarketDayLow,
      time: q.regularMarketTime ? new Date(q.regularMarketTime * 1000).toISOString() : null
    };

    quoteCache.set(symbol, { ts: now(), data: payload });
    res.json(payload);
  } catch (e) {
    logger.error(e);
    res.status(500).json({ error: 'quote_failed', message: e.message });
  }
});

const PORT = 3000;
app.listen(PORT, () => logger.info('API on http://127.0.0.1:' + PORT));

