import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from yahooquery import Ticker, search

BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'

# In-memory store - changed to support multiple stocks per user
user_selected_stocks = {}  # {user_id: [list of stocks]}

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
        "/delete - Remove a stock from tracking\n"
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

async def delete_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the process of deleting a stock"""
    user_id = update.message.from_user.id
    
    # Check if user has any stocks
    if user_id not in user_selected_stocks or not user_selected_stocks[user_id]:
        await update.message.reply_text("You don't have any stocks to delete. Use /add to start tracking!")
        return
    
    stocks = user_selected_stocks[user_id]
    
    # If only one stock, confirm deletion
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
        # Multiple stocks - show keyboard to select which one to delete
        context.user_data["deleting_stock"] = True
        
        keyboard = [[f"{stock['ticker']} - {stock['name'][:40]}"] for stock in stocks]
        keyboard.append(["Cancel"])
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "Select the stock you want to delete:",
            reply_markup=reply_markup
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation"""
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
    """List user's tracked stocks"""
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
    
    # Initialize user's stock list if doesn't exist
    if user_id not in user_selected_stocks:
        user_selected_stocks[user_id] = []
    
    # Handle deletion confirmation or selection
    if context.user_data.get("deleting_stock"):
        if user_input == "Cancel":
            await cancel(update, context)
            return
        
        # Single stock deletion confirmation
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
        
        # Multiple stocks - find and delete selected one
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
                # Check if stock already exists
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
        
        # Check if stock already exists
        if any(s['ticker'] == selected['ticker'] for s in user_selected_stocks[user_id]):
            await update.message.reply_text(
                f"⚠️ {selected['name']} ({selected['ticker']}) is already in your tracking list!"
            )
        else:
            user_selected_stocks[user_id].append(selected)
            await update.message.reply_text(
                f"✅ Stock '{selected['name']}' ({selected['ticker']}) added to your tracking list!"
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
    app.add_handler(CommandHandler("delete", delete_stock))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("list", list_stocks))
    
    # Message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Stock bot with Yahoo Finance is running...")
    app.run_polling()
```

## Key Changes:

1. **Changed data structure** - `user_selected_stocks[user_id]` now stores a **list** of stocks instead of a single stock

2. **`/delete` command** - New function that:
   - Shows confirmation for single stock
   - Shows selection keyboard for multiple stocks
   - Handles "Cancel" option

3. **Duplicate prevention** - Checks if stock already exists before adding

4. **Better state management** - Added `deleting_stock` state and `stock_to_delete` context

5. **Updated `/list`** - Now handles multiple stocks with numbering

6. **Delete flow**:
   - If 1 stock: "Are you sure?" confirmation
   - If multiple: Shows keyboard to select which one to delete

## User Flow Examples:

**Single stock:**
```
User: /delete
Bot: Are you sure you want to delete: Apple Inc. (AAPL)?
     [Yes, delete it] [No, keep it]
```

**Multiple stocks:**
```
User: /delete
Bot: Select the stock you want to delete:
     [AAPL - Apple Inc.]
     [NVDA - NVIDIA Corporation]
     [TSLA - Tesla, Inc.]
     [Cancel]
