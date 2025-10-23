import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from yahooquery import Ticker, search

BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'

user_selected_stocks = {}

async def search_companies(query, max_results=10):
    q = query.strip()
    
    if not q:
        return [], "Please provide a search query"
    
    if len(q) < 2:
        return [], "Query too short. Please enter at least 2 characters"
    
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, search, q)
        
        quotes = result.get("quotes", [])
        
        if not quotes:
            return [], f"No companies found for '{query}'"
        
        matches = []
        for item in quotes[:max_results]:
            symbol = item.get("symbol")
            name = item.get("shortname") or item.get("longname")
            exchange = item.get("exchDisp", "")
            
            if symbol and name:
                matches.append({
                    "name": name, 
                    "ticker": symbol,
                    "exchange": exchange
                })
        
        return matches, None
        
    except Exception as e:
        error_msg = f"Sorry, search failed. Please try again later."
        print(f"[ERROR] Search failed for '{q}': {type(e).__name__} - {e}")
        return [], error_msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to Stock Tracker Bot! 📈\n\n"
        "Commands:\n"
        "/add - Add a new stock to track\n"
        "/list - View your tracked stocks\n"
        "/delete - Remove a stock from tracking\n"
        "/help - Show this message"
    )

async def add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    context.user_data["adding_stock"] = True
    await update.message.reply_text(
        "🔍 Please send me a company name or ticker symbol to search.\n"
        "Example: 'Apple' or 'AAPL'\n\n"
        "Send /cancel to stop."
    )

async def delete_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in user_selected_stocks or not user_selected_stocks[user_id]:
        await update.message.reply_text("You don't have any stocks to delete. Use /add to start tracking!")
        return
    
    stocks = user_selected_stocks[user_id]
    
    if len(stocks) == 1:
        stock = stocks[0]
        context.user_data["deleting_stock"] = True
        context.user_data["stock_to_delete"] = stock
        
        keyboard = [["Yes, delete it"], ["No, keep it"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Are you sure you want to delete:\n{stock['name']} ({stock['ticker']})?",
            reply_markup=reply_markup
        )
    else:
        context.user_data["deleting_stock"] = True
        
        keyboard = [[f"{stock['ticker']} - {stock['name'][:40]}"] for stock in stocks]
        keyboard.append(["Cancel"])
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "Select the stock you want to delete:",
            reply_markup=reply_markup
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["adding_stock"] = False
    context.user_data["awaiting_choice"] = False
    context.user_data["deleting_stock"] = False
    context.user_data.pop("options", None)
    context.user_data.pop("stock_to_delete", None)
    await update.message.reply_text(
        "❌ Operation cancelled.",
        reply_markup=ReplyKeyboardRemove()
    )

async def list_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in user_selected_stocks or not user_selected_stocks[user_id]:
        await update.message.reply_text("You haven't added any stocks yet. Use /add to start tracking!")
        return
    
    stocks = user_selected_stocks[user_id]
    
    if len(stocks) == 1:
        stock = stocks[0]
        response = f"📊 Your tracked stock:\n\n• {stock['name']} ({stock['ticker']})"
    else:
        response = "📊 Your tracked stocks:\n\n"
        for i, stock in enumerate(stocks, 1):
            response += f"{i}. {stock['name']} ({stock['ticker']})\n"
    
    await update.message.reply_text(response)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    user_id = update.message.from_user.id
    
    if user_id not in user_selected_stocks:
        user_selected_stocks[user_id] = []
    
    if context.user_data.get("deleting_stock"):
        if user_input == "Cancel":
            await cancel(update, context)
            return
        
        if user_input in ["Yes, delete it", "No, keep it"]:
            if user_input == "Yes, delete it":
                stock = context.user_data.get("stock_to_delete")
                user_selected_stocks[user_id].remove(stock)
                await update.message.reply_text(
                    f"✅ {stock['name']} ({stock['ticker']}) has been removed from your tracking list.",
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                await update.message.reply_text(
                    "Stock kept in your tracking list.",
                    reply_markup=ReplyKeyboardRemove()
                )
            
            context.user_data["deleting_stock"] = False
            context.user_data.pop("stock_to_delete", None)
            return
        
        selected_ticker = user_input.split(" - ")[0].strip().upper()
        stocks = user_selected_stocks[user_id]
        
        for stock in stocks:
            if stock['ticker'] == selected_ticker:
                user_selected_stocks[user_id].remove(stock)
                await update.message.reply_text(
                    f"✅ {stock['name']} ({stock['ticker']}) has been removed from your tracking list.",
                    reply_markup=ReplyKeyboardRemove()
                )
                context.user_data["deleting_stock"] = False
                return
        
        await update.message.reply_text("Invalid selection. Please try again or use /cancel")
        return
    
    if not context.user_data.get("adding_stock"):
        await update.message.reply_text(
            "Please use /add to start adding a stock, or /help for available commands."
        )
        return
    
    if context.user_data.get("awaiting_choice"):
        selected_ticker = user_input.split(" - ")[0].strip().upper()
        possible = context.user_data.get("options", [])
        
        for company in possible:
            if selected_ticker == company["ticker"]:
                if any(s['ticker'] == company['ticker'] for s in user_selected_stocks[user_id]):
                    await update.message.reply_text(
                        f"⚠️ {company['name']} ({company['ticker']}) is already in your tracking list!",
                        reply_markup=ReplyKeyboardRemove()
                    )
                else:
                    user_selected_stocks[user_id].append(company)
                    await update.message.reply_text(
                        f"✅ Stock '{company['name']}' ({company['ticker']}) added to your tracking list!",
                        reply_markup=ReplyKeyboardRemove()
                    )
                
                context.user_data["awaiting_choice"] = False
                context.user_data["adding_stock"] = False
                context.user_data.pop("options", None)
                return
        
        await update.message.reply_text("Invalid selection. Please reply with a valid ticker from the options.")
        return
    
    matches, error = await search_companies(user_input)
    
    if error:
        await update.message.reply_text(error)
        return
    
    if not matches:
        await update.message.reply_text(
            "No matching companies found. Try another search or use /cancel to stop."
        )
        return
    
    if len(matches) == 1:
        selected = matches[0]
        
        if any(s['ticker'] == selected['ticker'] for s in user_selected_stocks[user_id]):
            await update.message.reply_text(
                f"⚠️ {selected['name']} ({selected['ticker']}) is already in your tracking list!"
            )
        else:
            user_selected_stocks[user_id].append(selected)
            await update.message.reply_text(
                f"✅ Stock '{selected['name']}' ({selected['ticker']}) added to your tracking list!"
            )
        
        context.user_data["adding_stock"] = False
    else:
        options = matches[:5]
        context.user_data["awaiting_choice"] = True
        context.user_data["options"] = options
        
        keyboard = [[f"{comp['ticker']} - {comp['name'][:40]}"] for comp in options]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "Multiple matches found. Please select one:",
            reply_markup=reply_markup
        )

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("add", add_stock))
    app.add_handler(CommandHandler("delete", delete_stock))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("list", list_stocks))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Stock bot with Yahoo Finance is running...")
    app.run_polling()
