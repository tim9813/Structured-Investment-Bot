import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from yahooquery import Ticker, search

BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'

# In-memory store
user_selected_stocks = {}

async def search_companies(query, max_results=10):
    """Search for companies using Yahoo Finance API.
    
    Args:
        query: Company name or ticker symbol to search for
        max_results: Maximum number of results to return (default: 10)
        
    Returns:
        tuple: (matches_list, error_message)
    """
    q = query.strip()
    
    if not q:
        return [], "Please provide a search query"
    
    if len(q) < 2:
        return [], "Query too short. Please enter at least 2 characters"
    
    try:
        # Run blocking API call in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, search, q)
        
        quotes = result.get("quotes", [])
        
        if not quotes:
            return [], f"No companies found for '{query}'"
        
        matches = []
        for item in quotes[:max_results]:  # Limit results
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
        "/help - Show this message"
    )

async def add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the process of adding a stock"""
    user_id = update.message.from_user.id
    context.user_data["adding_stock"] = True
    await update.message.reply_text(
        "🔍 Please send me a company name or ticker symbol to search.\n"
        "Example: 'Apple' or 'AAPL'\n\n"
        "Send /cancel to stop."
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation"""
    context.user_data["adding_stock"] = False
    context.user_data["awaiting_choice"] = False
    context.user_data.pop("options", None)
    await update.message.reply_text(
        "❌ Operation cancelled.",
        reply_markup=ReplyKeyboardRemove()
    )

async def list_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List user's tracked stocks"""
    user_id = update.message.from_user.id
    
    if user_id not in user_selected_stocks or not user_selected_stocks[user_id]:
        await update.message.reply_text("You haven't added any stocks yet. Use /add to start tracking!")
        return
    
    # If single stock
    if isinstance(user_selected_stocks[user_id], dict):
        stock = user_selected_stocks[user_id]
        response = f"📊 Your tracked stock:\n\n• {stock['name']} ({stock['ticker']})"
    else:
        # If multiple stocks (for future enhancement)
        response = "📊 Your tracked stocks:\n\n"
        for stock in user_selected_stocks[user_id]:
            response += f"• {stock['name']} ({stock['ticker']})\n"
    
    await update.message.reply_text(response)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    user_id = update.message.from_user.id
    
    # Check if user is in "adding stock" mode
    if not context.user_data.get("adding_stock"):
        await update.message.reply_text(
            "Please use /add to start adding a stock, or /help for available commands."
        )
        return
    
    # Handle ticker selection from keyboard
    if context.user_data.get("awaiting_choice"):
        # Extract ticker from "AAPL - Apple Inc." format
        selected_ticker = user_input.split(" - ")[0].strip().upper()
        possible = context.user_data.get("options", [])
        
        for company in possible:
            if selected_ticker == company["ticker"]:
                user_selected_stocks[user_id] = company
                await update.message.reply_text(
                    f"✅ Stock '{company['name']}' ({company['ticker']}) selected and added to your tracking list!",
                    reply_markup=ReplyKeyboardRemove()
                )
                # Reset states
                context.user_data["awaiting_choice"] = False
                context.user_data["adding_stock"] = False
                context.user_data.pop("options", None)
                return
        
        await update.message.reply_text("Invalid selection. Please reply with a valid ticker from the options.")
        return
    
    # Search for companies
    matches, error = await search_companies(user_input)
    
    # Handle errors
    if error:
        await update.message.reply_text(error)
        return
    
    # Handle no results
    if not matches:
        await update.message.reply_text(
            "No matching companies found. Try another search or use /cancel to stop."
        )
        return
    
    # Single match - auto select
    if len(matches) == 1:
        selected = matches[0]
        user_selected_stocks[user_id] = selected
        await update.message.reply_text(
            f"✅ Stock '{selected['name']}' ({selected['ticker']}) selected and added to your tracking list!"
        )
        # Reset state
        context.user_data["adding_stock"] = False
    
    # Multiple matches - show keyboard
    else:
        options = matches[:5]  # limit to top 5 results
        context.user_data["awaiting_choice"] = True
        context.user_data["options"] = options
        
        # Create keyboard with ticker and name
        keyboard = [[f"{comp['ticker']} - {comp['name'][:40]}"] for comp in options]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "Multiple matches found. Please select one:",
            reply_markup=reply_markup
        )

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("add", add_stock))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("list", list_stocks))
    
    # Message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Stock bot with Yahoo Finance is running...")
    app.run_polling()
