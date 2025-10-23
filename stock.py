from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from yahooquery import Ticker

BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'

# In-memory store
user_selected_stocks = {}

# Search function using Yahoo
def search_companies(query):
    query = query.strip()
    ticker_obj = Ticker(query)
    search_result = ticker_obj.symbols  # This gives a list of symbols Yahoo thinks matches

    matches = []
    for symbol in search_result:
        try:
            info = Ticker(symbol).quote_type
            if isinstance(info, dict) and symbol in info:
                name = info[symbol].get("longName") or info[symbol].get("shortName")
                if name and query.lower() in name.lower():
                    matches.append({"name": name, "ticker": symbol})
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

    return matches

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Send me a company name to begin tracking.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    user_id = update.message.from_user.id

    if context.user_data.get("awaiting_choice"):
        selected_ticker = user_input.upper()
        possible = context.user_data.get("options", [])
        for company in possible:
            if selected_ticker == company["ticker"]:
                user_selected_stocks[user_id] = company
                await update.message.reply_text(f"Stock '{company['name']}' (ticker {company['ticker']}) selected.")
                context.user_data["awaiting_choice"] = False
                return
        await update.message.reply_text("Invalid selection. Please reply with a valid ticker.")
        return

    matches = search_companies(user_input)

    if not matches:
        await update.message.reply_text("No matching companies found.")
    elif len(matches) == 1:
        selected = matches[0]
        user_selected_stocks[user_id] = selected
        await update.message.reply_text(f"Stock '{selected['name']}' (ticker {selected['ticker']}) selected.")
    else:
        options = [comp["ticker"] for comp in matches[:5]]  # limit to top 5 results
        context.user_data["awaiting_choice"] = True
        context.user_data["options"] = matches[:5]
        keyboard = ReplyKeyboardMarkup([[ticker] for ticker in options], one_time_keyboard=True)
        await update.message.reply_text("Multiple matches found. Please choose the ticker:", reply_markup=keyboard)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Stock bot with Yahoo Finance is running...")
    app.run_polling()
