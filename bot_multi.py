# bot_multi.py (Fund & Coupon% as user inputs)
import os, asyncio, datetime as dt, sqlite3, yfinance as yf, ccxt
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

DB = "investments.db"

# Conversation steps
(SYMBOL, MARKET, KO, KI, PERIOD, FUND, PAYOUT, COUPON_RATE, DECAY) = range(9)

# ===== DB helpers =====
def db_init():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS investments(
        chat_id TEXT,
        symbol TEXT,
        market TEXT,
        entrance_date TEXT,
        entrance_price REAL,
        ko REAL,
        ki REAL,
        decay REAL,
        period REAL,
        payout TEXT,
        months_passed INTEGER,
        status TEXT,
        group_chat TEXT,
        fund REAL,
        coupon_rate REAL
    )""")
    con.commit(); con.close()

def db_exec(q, p=(), fetch=False):
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute(q, p); res = cur.fetchall() if fetch else None
    con.commit(); con.close(); return res

# ===== Market price =====
async def get_price(symbol, mkt):
    if mkt == "stock":
        data = yf.download(symbol, period="1d", progress=False)
        return float(data["Close"].iloc[-1])
    else:
        ex = ccxt.binance()
        ticker = ex.fetch_ticker(symbol)  # e.g. BTC/USDT symbol format on ccxt is "BTC/USDT"
        return float(ticker["last"])

# ===== Commands =====
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /add to add an investment, /status to view all.")

async def add(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Enter symbol (e.g. AAPL or BTC/USDT):")
    return SYMBOL

async def symbol_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["symbol"] = update.message.text.strip().upper()
    await update.message.reply_text("Market type? (stock / crypto)")
    return MARKET

async def market_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["market"] = update.message.text.strip().lower()
    await update.message.reply_text("Knock-Out % (e.g. 5 for +5%)")
    return KO

async def ko_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["KO"] = float(update.message.text.strip())
    await update.message.reply_text("Knock-In % (negative number, e.g. -10)")
    return KI

async def ki_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["KI"] = float(update.message.text.strip())
    await update.message.reply_text("Investment period in months (e.g. 6)")
    return PERIOD

async def period_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["period"] = float(update.message.text.strip())
    await update.message.reply_text("Fund invested in RM (e.g. 50000)")
    return FUND

async def fund_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["fund"] = float(update.message.text.strip())
    await update.message.reply_text("Payout type? (bullet / coupon)")
    return PAYOUT

async def payout_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    payout = update.message.text.strip().lower()
    ctx.user_data["payout"] = payout
    if payout == "coupon":
        await update.message.reply_text("Coupon % per month (e.g. 1 for 1%)")
        return COUPON_RATE
    else:
        ctx.user_data["coupon_rate"] = 0.0
        await update.message.reply_text("KO decay % per month (0 for none)")
        return DECAY

async def coupon_rate_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["coupon_rate"] = float(update.message.text.strip())
    await update.message.reply_text("KO decay % per month (0 for none)")
    return DECAY

async def decay_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rec = ctx.user_data
    rec["decay"] = float(update.message.text.strip())
    # Entrance snapshot
    price = await get_price(rec["symbol"], rec["market"])
    now = dt.date.today()
    db_exec("""INSERT INTO investments
        (chat_id, symbol, market, entrance_date, entrance_price,
         ko, ki, decay, period, payout, months_passed, status, group_chat, fund, coupon_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, ?)""",
        (str(update.effective_chat.id), rec["symbol"], rec["market"], str(now), price,
         rec["KO"], rec["KI"], rec["decay"], rec["period"], rec["payout"],
         os.getenv("TG_GROUP_CHAT_ID"), rec["fund"], rec["coupon_rate"]))
    await update.message.reply_text(
        "✅ Saved\n"
        f"Symbol: {rec['symbol']} ({rec['market']})\n"
        f"Entry: {price:.4f} on {now}\n"
        f"KO {rec['KO']}% | KI {rec['KI']}% | Decay {rec['decay']}%/mo\n"
        f"Period {rec['period']}m | Payout {rec['payout']} | Fund RM {rec['fund']:.2f}"
        + (f" | Coupon {rec['coupon_rate']}%/mo" if rec['payout']=='coupon' else "")
    )
    return ConversationHandler.END

async def status(update: Update, _: ContextTypes.DEFAULT_TYPE):
    rows = db_exec("""SELECT symbol,market,entrance_price,ko,ki,decay,period,
                             payout,months_passed,status,fund,coupon_rate
                      FROM investments WHERE chat_id=?""",
                   (str(update.effective_chat.id),), True)
    if not rows:
        await update.message.reply_text("No records. Use /add."); return
    out=[]
    for sym,mkt,ep,ko,ki,dec,per,pay,mp,st,fund,coupon in rows:
        cur = await get_price(sym, mkt)
        KO_adj = ko - dec*mp
        KO_price = ep*(1+KO_adj/100); KI_price = ep*(1+ki/100)
        change = (cur-ep)/ep*100
        line = (
            f"{sym} ({mkt})\n"
            f"Now {cur:.4f} ({change:+.2f}%) | KO {KO_price:.4f} | KI {KI_price:.4f}\n"
            f"{mp}/{per} months | {pay} | {st}\n"
            f"Fund RM {fund:.2f}" + (f" | Coupon {coupon}%/mo" if pay=='coupon' else "")
        )
        out.append(line)
    await update.message.reply_text("\n\n".join(out))

# ===== Schedulers =====
async def check_prices(app):
    rows = db_exec("""SELECT rowid, chat_id, symbol, market, entrance_price,
                             ko, ki, decay, months_passed, status, group_chat
                      FROM investments""", fetch=True)
    for rowid,chat,sym,mkt,ep,ko,ki,dec,mp,st,gchat in rows:
        if st!="active": continue
        cur = await get_price(sym,mkt)
        KO_adj = ko - dec*mp
        KO_price = ep*(1+KO_adj/100); KI_price = ep*(1+ki/100)
        msg=None
        if cur>=KO_price: st="knockout"; msg=f"🚀 {sym} KO hit! {cur:.4f} ≥ {KO_price:.4f}"
        elif cur<=KI_price: st="knockin"; msg=f"⚠️ {sym} KI hit! {cur:.4f} ≤ {KI_price:.4f}"
        if msg:
            db_exec("UPDATE investments SET status=? WHERE rowid=?", (st,rowid))
            for cid in filter(None,[chat,gchat]):
                app.create_task(app.bot.send_message(chat_id=cid, text=msg))

async def monthly_update(app):
    today = dt.date.today()
    rows = db_exec("""SELECT rowid, chat_id, symbol, entrance_date,
                             months_passed, period, payout, status,
                             group_chat, fund, coupon_rate
                      FROM investments""", fetch=True)
    for rowid,chat,sym,start,mp,per,payout,st,gchat,fund,coupon in rows:
        if st!="active": continue
        start_d = dt.date.fromisoformat(start)
        if today.day == start_d.day:
            mp += 1
            st = "matured" if mp>=per else st
            db_exec("UPDATE investments SET months_passed=?, status=? WHERE rowid=?", (mp,st,rowid))
            if payout=="coupon":
                coupon_amt = float(fund) * float(coupon) / 100.0
                msg=f"💰 {sym}: Monthly coupon RM {coupon_amt:.2f} credited ({mp}/{per})"
            else:
                msg=f"🎯 {sym}: Bullet payout checkpoint ({mp}/{per})"
            for cid in filter(None,[chat,gchat]):
                app.create_task(app.bot.send_message(chat_id=cid, text=msg))

async def cancel(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Setup cancelled."); return ConversationHandler.END

# ===== Main =====
async def main():
    db_init()
    token = os.getenv("TG_TOKEN")
    app = ApplicationBuilder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("add", add)],
        states={
            SYMBOL:[MessageHandler(filters.TEXT, symbol_input)],
            MARKET:[MessageHandler(filters.TEXT, market_input)],
            KO:[MessageHandler(filters.TEXT, ko_input)],
            KI:[MessageHandler(filters.TEXT, ki_input)],
            PERIOD:[MessageHandler(filters.TEXT, period_input)],
            FUND:[MessageHandler(filters.TEXT, fund_input)],
            PAYOUT:[MessageHandler(filters.TEXT, payout_input)],
            COUPON_RATE:[MessageHandler(filters.TEXT, coupon_rate_input)],
            DECAY:[MessageHandler(filters.TEXT, decay_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))

    scheduler = AsyncIOScheduler()
    # run daily checks in SG morning
    scheduler.add_job(check_prices, "cron", hour=9, args=[app])
    scheduler.add_job(monthly_update, "cron", hour=9, minute=5, args=[app])
    scheduler.start()

    print("Bot running…")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
