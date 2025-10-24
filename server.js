// server.js - Enhanced version with improvements
const express = require('express');
const dotenv = require('dotenv');
dotenv.config();

// Robust yahoo-finance2 import for CJS
const yfmod = require('yahoo-finance2');
const yahooFinance = yfmod.default || yfmod;

const app = express();
app.use(express.json());

// CORS middleware (if needed for frontend)
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  next();
});

// Simple in-memory caches with size limits
class LRUCache {
  constructor(maxSize = 100) {
    this.cache = new Map();
    this.maxSize = maxSize;
  }

  get(key) {
    if (!this.cache.has(key)) return null;
    const item = this.cache.get(key);
    // Move to end (most recently used)
    this.cache.delete(key);
    this.cache.set(key, item);
    return item;
  }

  set(key, value) {
    if (this.cache.has(key)) {
      this.cache.delete(key);
    } else if (this.cache.size >= this.maxSize) {
      // Remove oldest (first) item
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
    this.cache.set(key, value);
  }

  clear() {
    this.cache.clear();
  }
}

const searchCache = new LRUCache(50);
const quoteCache = new LRUCache(100);

const now = () => Date.now();
const SEARCH_TTL = 60 * 60 * 1000; // 1 hour
const QUOTE_TTL = 15 * 1000;       // 15 seconds

// Rate limiting (simple in-memory)
const rateLimitMap = new Map();
const RATE_LIMIT_WINDOW = 60 * 1000; // 1 minute
const RATE_LIMIT_MAX = 60; // 60 requests per minute

function checkRateLimit(ip) {
  const key = ip;
  const current = rateLimitMap.get(key) || { count: 0, resetTime: now() + RATE_LIMIT_WINDOW };
  
  if (now() > current.resetTime) {
    current.count = 0;
    current.resetTime = now() + RATE_LIMIT_WINDOW;
  }
  
  current.count++;
  rateLimitMap.set(key, current);
  
  return {
    allowed: current.count <= RATE_LIMIT_MAX,
    remaining: Math.max(0, RATE_LIMIT_MAX - current.count),
    resetTime: current.resetTime
  };
}

// Rate limit middleware
app.use((req, res, next) => {
  const ip = req.ip || req.connection.remoteAddress;
  const limit = checkRateLimit(ip);
  
  res.setHeader('X-RateLimit-Limit', RATE_LIMIT_MAX);
  res.setHeader('X-RateLimit-Remaining', limit.remaining);
  res.setHeader('X-RateLimit-Reset', new Date(limit.resetTime).toISOString());
  
  if (!limit.allowed) {
    return res.status(429).json({ 
      error: 'rate_limit_exceeded',
      message: 'Too many requests, please try again later'
    });
  }
  
  next();
});

// Health check
app.get('/api/ping', (req, res) => {
  res.json({ 
    ok: true, 
    msg: 'pong',
    timestamp: new Date().toISOString(),
    cacheStats: {
      searchCache: searchCache.cache.size,
      quoteCache: quoteCache.cache.size
    }
  });
});

// Search by name or ticker (Yahoo)
app.get('/api/stocks/search', async (req, res) => {
  try {
    const q = String(req.query.q || '').trim();
    
    if (!q) {
      return res.json({ items: [], cached: false });
    }
    
    if (q.length < 1) {
      return res.status(400).json({ 
        error: 'invalid_query',
        message: 'Query must be at least 1 character'
      });
    }

    // Check cache
    const cached = searchCache.get(q);
    if (cached && (now() - cached.ts) < SEARCH_TTL) {
      return res.json({ 
        items: cached.data, 
        cached: true,
        cacheAge: Math.floor((now() - cached.ts) / 1000)
      });
    }

    // Fetch from Yahoo Finance
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
    
    res.json({ 
      items, 
      cached: false,
      count: items.length
    });
  } catch (e) {
    console.error('Search error:', e);
    res.status(500).json({ 
      error: 'search_failed', 
      message: e.message,
      query: req.query.q
    });
  }
});

// Quote by symbol (Yahoo)
app.get('/api/stocks/quote', async (req, res) => {
  try {
    const symbol = String(req.query.symbol || '').trim().toUpperCase();
    
    if (!symbol) {
      return res.status(400).json({ 
        error: 'missing_symbol',
        message: 'Symbol parameter is required'
      });
    }

    // Check cache
    const cached = quoteCache.get(symbol);
    if (cached && (now() - cached.ts) < QUOTE_TTL) {
      return res.json({ 
        ...cached.data, 
        cached: true,
        cacheAge: Math.floor((now() - cached.ts) / 1000)
      });
    }

    // Fetch from Yahoo Finance
    const q = await yahooFinance.quote(symbol);
    
    if (!q || !q.symbol) {
      return res.status(404).json({
        error: 'symbol_not_found',
        message: `No data found for symbol: ${symbol}`
      });
    }

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
      volume: q.regularMarketVolume,
      fiftyTwoWeekHigh: q.fiftyTwoWeekHigh,
      fiftyTwoWeekLow: q.fiftyTwoWeekLow,
      marketCap: q.marketCap,
      time: q.regularMarketTime ? new Date(q.regularMarketTime * 1000).toISOString() : null,
      cached: false
    };

    quoteCache.set(symbol, { ts: now(), data: payload });
    
    res.json(payload);
  } catch (e) {
    console.error('Quote error:', e);
    
    if (e.message && e.message.includes('Not Found')) {
      return res.status(404).json({ 
        error: 'symbol_not_found',
        message: `Symbol not found: ${req.query.symbol}`
      });
    }
    
    res.status(500).json({ 
      error: 'quote_failed', 
      message: e.message,
      symbol: req.query.symbol
    });
  }
});

// Clear cache endpoint (useful for testing)
app.post('/api/cache/clear', (req, res) => {
  searchCache.clear();
  quoteCache.clear();
  res.json({ 
    ok: true, 
    message: 'All caches cleared' 
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({ 
    error: 'not_found',
    message: 'Endpoint not found',
    path: req.path
  });
});

// Error handler
app.use((err, req, res, next) => {
  console.error('Unhandled error:', err);
  res.status(500).json({ 
    error: 'internal_error',
    message: 'An unexpected error occurred'
  });
});

const PORT = process.env.PORT || 3000;
const server = app.listen(PORT, () => {
  console.log(`Stock API Server running on http://127.0.0.1:${PORT}`);
  console.log(`Health check: http://127.0.0.1:${PORT}/api/ping`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, closing server...');
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});

module.exports = app; // For testing
