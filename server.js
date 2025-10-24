// server.js - CommonJS, Yahoo Finance search + quote
const express = require('express');
const dotenv = require('dotenv');
dotenv.config();

// Robust yahoo-finance2 import for CJS
const yfmod = require('yahoo-finance2');
const yahooFinance = yfmod.default || yfmod;

const app = express();
app.use(express.json());

// Simple in-memory caches
const searchCache = new Map(); // key: q
const quoteCache  = new Map(); // key: symbol
const now = () => Date.now();

const SEARCH_TTL = 60 * 60 * 1000; // 1 hour
const QUOTE_TTL  = 15 * 1000;      // 15 seconds (near real-time)

app.get('/api/ping', (req, res) => res.json({ ok: true, msg: 'pong' }));

// Search by name or ticker (Yahoo)
app.get('/api/stocks/search', async (req, res) => {
  try {
    const q = String(req.query.q || '').trim();
    if (!q) return res.json({ items: [] });

    const cached = searchCache.get(q);
    if (cached && (now() - cached.ts) < SEARCH_TTL) {
      return res.json({ items: cached.data });
    }

    const result = await yahooFinance.search(q, {
      quotesCount: 10,
      newsCount: 0,
      enableFuzzyQuery: true
    });

    const items = (result.quotes || [])
      .filter(x => x.symbol)
      .map(x => ({
        symbol: x.symbol,
        shortname: x.shortname || '',
        longname: x.longname || '',
        exchange: x.exchange || x.exchDisp || '',
        type: x.quoteType || x.typeDisp || ''
      }));

    searchCache.set(q, { ts: now(), data: items });
    res.json({ items });
  } catch (e) {
    res.status(500).json({ error: 'search_failed', message: e.message });
  }
});

// Quote by symbol (Yahoo)
app.get('/api/stocks/quote', async (req, res) => {
  try {
    const symbol = String(req.query.symbol || '').trim().toUpperCase();
    if (!symbol) return res.status(400).json({ error: 'missing_symbol' });

    const cached = quoteCache.get(symbol);
    if (cached && (now() - cached.ts) < QUOTE_TTL) {
      return res.json(cached.data);
    }

    const q = await yahooFinance.quote(symbol);
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
    res.status(500).json({ error: 'quote_failed', message: e.message });
  }
});

const PORT = 3000;
app.listen(PORT, () => console.log('API on http://127.0.0.1:' + PORT));
