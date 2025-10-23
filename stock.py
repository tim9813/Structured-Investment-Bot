import asyncio
from telegram import Update, ReplyKeyboardMarkup
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
        # Use the search function, not Ticker.search
        result = await loop.run_in_executor(None, search, q)
        
        # result is a dict with 'quotes' key
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
        print(f"[ERROR] Search failed for '{q}': {type(e).__name__} - {e}")  # Better logging
        return [], error_msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Send me a company name or ticker to begin tracking.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    user_id = update.message.from_user.id
    
    # Handle ticker selection from keyboard
    if context.user_data.get("awaiting_choice"):
        # Extract ticker from "AAPL - Apple Inc." format
        selected_ticker = user_input.split(" - ")[0].strip().upper()
        possible = context.user_data.get("options", [])
        
        for company in possible:
            if selected_ticker == company["ticker"]:
                user_selected_stocks[user_id] = company
                await update.message.reply_text(
                    f"✅ Stock '{company['name']}' ({company['ticker']}) selected."
                )
                context.user_data["awaiting_choice"] = False
                context.user_data.pop("options", None)  # Clean up
                return
        
        await update.message.reply_text("Invalid selection. Please reply with a valid ticker from the options.")
        return
    
    # Search for companies - MUST AWAIT!
    matches, error = await search_companies(user_input)
    
    # Handle errors
    if error:
        await update.message.reply_text(error)
        return
    
    # Handle no results
    if not matches:
        await update.message.reply_text("No matching companies found.")
        return
    
    # Single match - auto select
    if len(matches) == 1:
        selected = matches[0]
        user_selected_stocks[user_id] = selected
        await update.message.reply_text(
            f"✅ Stock '{selected['name']}' ({selected['ticker']}) selected."
        )
    
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
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Stock bot with Yahoo Finance is running...")
    app.run_polling()
