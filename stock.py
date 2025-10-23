import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from yahooquery import Ticker, search

BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'

user_selected_stocks = {}
user_groups = {}  # {user_id: [{'name': 'Group 1', 'stocks': [ticker1, ticker2], 'prices': {}, 'active': True}]}

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

async def get_stock_prices(tickers):
    """Fetch current prices for multiple tickers"""
    try:
        loop = asyncio.get_event_loop()
        ticker_obj = Ticker(tickers)
        result = await loop.run_in_executor(None, lambda: ticker_obj.price)
        
        prices = {}
        for ticker in tickers:
            if ticker in result and isinstance(result[ticker], dict):
                price_data = result[ticker]
                current_price = price_data.get('regularMarketPrice')
                if current_price:
                    prices[ticker] = {
                        'price': current_price,
                        'currency': price_data.get('currency', 'USD'),
                        'change': price_data.get('regularMarketChange', 0),
                        'change_percent': price_data.get('regularMarketChangePercent', 0)
                    }
        
        return prices
    except Exception as e:
        print(f"[ERROR] Failed to fetch prices: {e}")
        return {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to Stock Tracker Bot! 📈\n\n"
        "Commands:\n"
        "/add - Add a new stock to track\n"
        "/list - View your tracked stocks\n"
        "/delete - Remove a stock from tracking\n"
        "/group - Create a stock group (2-5 stocks)\n"
        "/groups - View your groups\n"
        "/disband - Disband a group (keeps for future)\n"
        "/activate - Reactivate a disbanded group\n"
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

async def create_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the process of creating a stock group"""
    user_id = update.message.from_user.id
    
    # Check if user has added stocks
    if user_id not in user_selected_stocks or not user_selected_stocks[user_id]:
        await update.message.reply_text(
            "❌ You need to add stocks first!\n\n"
            "Use /add to add stocks to your tracking list."
        )
        return
    
    stocks = user_selected_stocks[user_id]
    
    if len(stocks) < 2:
        await update.message.reply_text(
            "❌ You need at least 2 stocks to create a group.\n\n"
            f"You currently have {len(stocks)} stock. Use /add to add more stocks."
        )
        return
    
    # Initialize group creation state
    context.user_data["creating_group"] = True
    context.user_data["group_stocks"] = []
    context.user_data["group_step"] = "name"
    
    await update.message.reply_text(
        "📊 Let's create a stock group!\n\n"
        "First, give your group a name (e.g., 'Tech Giants', 'My Portfolio'):"
    )

async def disband_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Disband a group (set as inactive)"""
    user_id = update.message.from_user.id
    
    if user_id not in user_groups or not user_groups[user_id]:
        await update.message.reply_text("You don't have any groups. Use /group to create one!")
        return
    
    # Filter only active groups
    active_groups = [g for g in user_groups[user_id] if g.get('active', True)]
    
    if not active_groups:
        await update.message.reply_text("You don't have any active groups. Use /activate to reactivate disbanded groups.")
        return
    
    if len(active_groups) == 1:
        group = active_groups[0]
        context.user_data["disbanding_group"] = True
        context.user_data["group_to_disband"] = group
        
        keyboard = [["Yes, disband it"], ["No, keep it active"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Are you sure you want to disband:\n'{group['name']}'?\n\n"
            f"Stocks: {', '.join(group['stocks'])}\n\n"
            f"(The group will be saved and can be reactivated later)",
            reply_markup=reply_markup
        )
    else:
        context.user_data["disbanding_group"] = True
        
        keyboard = [[f"{g['name']} ({', '.join(g['stocks'][:2])}...)"] for g in active_groups]
        keyboard.append(["Cancel"])
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "Select the group you want to disband:",
            reply_markup=reply_markup
        )

async def activate_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reactivate a disbanded group"""
    user_id = update.message.from_user.id
    
    if user_id not in user_groups or not user_groups[user_id]:
        await update.message.reply_text("You don't have any groups. Use /group to create one!")
        return
    
    # Filter only inactive groups
    inactive_groups = [g for g in user_groups[user_id] if not g.get('active', True)]
    
    if not inactive_groups:
        await update.message.reply_text("You don't have any disbanded groups. All your groups are active!")
        return
    
    if len(inactive_groups) == 1:
        group = inactive_groups[0]
        context.user_data["activating_group"] = True
        context.user_data["group_to_activate"] = group
        
        keyboard = [["Yes, activate it"], ["No, keep it disbanded"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Reactivate this group?\n'{group['name']}'\n\n"
            f"Stocks: {', '.join(group['stocks'])}",
            reply_markup=reply_markup
        )
    else:
        context.user_data["activating_group"] = True
        
        keyboard = [[f"{g['name']} ({', '.join(g['stocks'][:2])}...)"] for g in inactive_groups]
        keyboard.append(["Cancel"])
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "Select the group you want to reactivate:",
            reply_markup=reply_markup
        )

async def view_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display all groups for the user"""
    user_id = update.message.from_user.id
    
    if user_id not in user_groups or not user_groups[user_id]:
        await update.message.reply_text(
            "You don't have any groups yet.\n\n"
            "Use /group to create your first stock group!"
        )
        return
    
    groups = user_groups[user_id]
    active_groups = [g for g in groups if g.get('active', True)]
    inactive_groups = [g for g in groups if not g.get('active', True)]
    
    response = ""
    
    if active_groups:
        response += "📊 Active Groups:\n\n"
        for i, group in enumerate(active_groups, 1):
            response += f"{i}. {group['name']} ✅\n"
            response += f"   Stocks: {', '.join(group['stocks'])}\n"
            
            # Show prices if available
            if group.get('prices'):
                response += "   Prices:\n"
                for ticker, price_data in group['prices'].items():
                    change_symbol = "📈" if price_data['change'] >= 0 else "📉"
                    response += f"   • {ticker}: {price_data['currency']} {price_data['price']:.2f} {change_symbol} ({price_data['change_percent']:.2f}%)\n"
            
            response += "\n"
    
    if inactive_groups:
        response += "💤 Disbanded Groups:\n\n"
        for i, group in enumerate(inactive_groups, 1):
            response += f"{i}. {group['name']} (Inactive)\n"
            response += f"   Stocks: {', '.join(group['stocks'])}\n\n"
    
    if not response:
        response = "You don't have any groups yet."
    
    await update.message.reply_text(response)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["adding_stock"] = False
    context.user_data["awaiting_choice"] = False
    context.user_data["deleting_stock"] = False
    context.user_data["creating_group"] = False
    context.user_data["disbanding_group"] = False
    context.user_data["activating_group"] = False
    context.user_data["group_step"] = None
    context.user_data.pop("options", None)
    context.user_data.pop("stock_to_delete", None)
    context.user_data.pop("group_stocks", None)
    context.user_data.pop("group_name", None)
    context.user_data.pop("group_to_disband", None)
    context.user_data.pop("group_to_activate", None)
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
    
    if user_id not in user_groups:
        user_groups[user_id] = []
    
    # Handle group activation
    if context.user_data.get("activating_group"):
        if user_input == "Cancel":
            await cancel(update, context)
            return
        
        if user_input in ["Yes, activate it", "No, keep it disbanded"]:
            if user_input == "Yes, activate it":
                group = context.user_data.get("group_to_activate")
                group['active'] = True
                
                # Refresh prices
                tickers = group['stocks']
                prices = await get_stock_prices(tickers)
                group['prices'] = prices
                
                await update.message.reply_text(
                    f"✅ Group '{group['name']}' has been reactivated!\n"
                    f"Prices updated.",
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                await update.message.reply_text(
                    "Group remains disbanded.",
                    reply_markup=ReplyKeyboardRemove()
                )
            
            context.user_data["activating_group"] = False
            context.user_data.pop("group_to_activate", None)
            return
        
        # Multiple groups - find and activate selected one
        group_name = user_input.split(" (")[0].strip()
        inactive_groups = [g for g in user_groups[user_id] if not g.get('active', True)]
        
        for group in inactive_groups:
            if group['name'] == group_name:
                group['active'] = True
                
                # Refresh prices
                tickers = group['stocks']
                prices = await get_stock_prices(tickers)
                group['prices'] = prices
                
                await update.message.reply_text(
                    f"✅ Group '{group['name']}' has been reactivated!\n"
                    f"Prices updated.",
                    reply_markup=ReplyKeyboardRemove()
                )
                context.user_data["activating_group"] = False
                return
        
        await update.message.reply_text("Invalid selection. Please try again or use /cancel")
        return
    
    # Handle group disbanding
    if context.user_data.get("disbanding_group"):
        if user_input == "Cancel":
            await cancel(update, context)
            return
        
        if user_input in ["Yes, disband it", "No, keep it active"]:
            if user_input == "Yes, disband it":
                group = context.user_data.get("group_to_disband")
                group['active'] = False
                await update.message.reply_text(
                    f"✅ Group '{group['name']}' has been disbanded.\n"
                    f"You can reactivate it anytime with /activate",
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                await update.message.reply_text(
                    "Group remains active.",
                    reply_markup=ReplyKeyboardRemove()
                )
            
            context.user_data["disbanding_group"] = False
            context.user_data.pop("group_to_disband", None)
            return
        
        # Multiple groups - find and disband selected one
        group_name = user_input.split(" (")[0].strip()
        active_groups = [g for g in user_groups[user_id] if g.get('active', True)]
        
        for group in active_groups:
            if group['name'] == group_name:
                group['active'] = False
                await update.message.reply_text(
                    f"✅ Group '{group['name']}' has been disbanded.\n"
                    f"You can reactivate it anytime with /activate",
                    reply_markup=ReplyKeyboardRemove()
                )
                context.user_data["disbanding_group"] = False
                return
        
        await update.message.reply_text("Invalid selection. Please try again or use /cancel")
        return
    
    # Handle group creation flow
    if context.user_data.get("creating_group"):
        step = context.user_data.get("group_step")
        
        # Step 1: Get group name
        if step == "name":
            context.user_data["group_name"] = user_input
            context.user_data["group_step"] = "select_stocks"
            
            stocks = user_selected_stocks[user_id]
            keyboard = [[f"{stock['ticker']} - {stock['name'][:30]}"] for stock in stocks]
            keyboard.append(["Done selecting"])
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
            
            await update.message.reply_text(
                f"✅ Group name: '{user_input}'\n\n"
                f"Now select stocks for this group (2-5 stocks).\n"
                f"Tap each stock you want to add, then tap 'Done selecting'.",
                reply_markup=reply_markup
            )
            return
        
        # Step 2: Select stocks
        elif step == "select_stocks":
            if user_input == "Done selecting":
                selected_stocks = context.user_data.get("group_stocks", [])
                
                if len(selected_stocks) < 2:
                    await update.message.reply_text(
                        f"❌ You need at least 2 stocks in a group. You've selected {len(selected_stocks)}.\n"
                        "Please select more stocks."
                    )
                    return
                
                if len(selected_stocks) > 5:
                    await update.message.reply_text(
                        f"❌ Maximum 5 stocks per group. You've selected {len(selected_stocks)}.\n"
                        "Please create the group with 5 stocks or select fewer."
                    )
                    return
                
                # Fetch prices for the group
                tickers = [s['ticker'] for s in selected_stocks]
                prices = await get_stock_prices(tickers)
                
                # Create the group
                group = {
                    'name': context.user_data["group_name"],
                    'stocks': tickers,
                    'stock_details': selected_stocks,
                    'prices': prices,
                    'active': True
                }
                
                user_groups[user_id].append(group)
                
                response = f"✅ Group '{group['name']}' created successfully!\n\n"
                response += f"Stocks: {', '.join(tickers)}\n\n"
                response += "Prices fetched and tracking started. Use /groups to view details."
                
                await update.message.reply_text(response, reply_markup=ReplyKeyboardRemove())
                
                # Reset state
                context.user_data["creating_group"] = False
                context.user_data["group_step"] = None
                context.user_data.pop("group_stocks", None)
                context.user_data.pop("group_name", None)
                return
            
            # Add stock to group
            selected_ticker = user_input.split(" - ")[0].strip().upper()
            stocks = user_selected_stocks[user_id]
            group_stocks = context.user_data.get("group_stocks", [])
            
            for stock in stocks:
                if stock['ticker'] == selected_ticker:
                    # Check if already added
                    if any(s['ticker'] == selected_ticker for s in group_stocks):
                        await update.message.reply_text(
                            f"⚠️ {selected_ticker} is already in this group!"
                        )
                        return
                    
                    # Check max limit
                    if len(group_stocks) >= 5:
                        await update.message.reply_text(
                            f"⚠️ Maximum 5 stocks per group reached!"
                        )
                        return
                    
                    group_stocks.append(stock)
                    context.user_data["group_stocks"] = group_stocks
                    
                    await update.message.reply_text(
                        f"✅ Added {stock['name']} ({selected_ticker})\n"
                        f"Total: {len(group_stocks)}/5 stocks selected.\n\n"
                        f"Continue selecting or tap 'Done selecting'."
                    )
                    return
            
            await update.message.reply_text("Invalid selection. Please select from the list.")
            return
    
    # Handle deletion confirmation or selection
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
    
    # Check if user is in "adding stock" mode
    if not context.user_data.get("adding_stock"):
        await update.message.reply_text(
            "Please use /add to start adding a stock, or /help for available commands."
        )
        return
    
    # Handle ticker selection from keyboard
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
    
    # Search for companies
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
    app.add_handler(CommandHandler("group", create_group))
    app.add_handler(CommandHandler("groups", view_groups))
    app.add_handler(CommandHandler("disband", disband_group))
    app.add_handler(CommandHandler("activate", activate_group))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("list", list_stocks))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Stock bot with Yahoo Finance is running...")
    app.run_polling()
