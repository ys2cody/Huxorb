//+------------------------------------------------------------------+
//|                                            HuxORB_Bridge_EA.mq4 |
//|                         HuxORB PRO - Prop Firm Trading Bot      |
//|                         Execution Layer for FundedNext & Others |
//+------------------------------------------------------------------+
#property copyright "HuxORB Team"
#property link      "https://github.com/ys2cody/Huxorb"
#property version   "1.00"
#property strict

/*
   HuxORB PRO - MT4 Bridge EA
   ===========================

   This EA reads signals from the Python engine and executes them
   with proper risk management and prop firm safety rails.

   KEY FEATURES:
   - True risk-based position sizing (using SL distance)
   - Session validation (London/NY with server UTC offset)
   - Spread filtering
   - Max trades per day limit
   - Daily drawdown kill-switch (4.6% default)
   - Max drawdown kill-switch (9.5% default)
   - Consistency rule (40% profit cap per day)
   - Duplicate signal prevention
   - Comprehensive logging

   NO MARTINGALE. NO GRID. NO HEDGING.
   Conservative execution designed to pass prop firm challenges.
*/

//+------------------------------------------------------------------+
//| INPUT PARAMETERS                                                  |
//+------------------------------------------------------------------+

// Risk Management
input double   RiskPerTradePct = 0.5;        // Risk per trade (% of equity)
input int      MaxTradesPerDay = 2;          // Max trades per day (hard cap)

// Spread Filter
input int      MaxSpreadPoints = 20;         // Max spread in points (20 = 2.0 pips on 5-digit)

// Session Control
input int      ServerUtcOffsetHrs = 2;       // FundedNext server UTC offset (default: +2)
input bool     TradeLondon = true;           // Trade London session (07:00-10:00 UTC)
input bool     TradeNewYork = true;          // Trade New York session (12:00-16:00 UTC)

// Prop Firm Safety Rails
input double   DailyLossLimitPct = 4.6;      // Daily loss limit (% of starting daily equity)
input double   MaxLossLimitPct = 9.5;        // Max overall loss limit (% of starting balance)
input double   ProfitCapPctOfTarget = 40.0;  // Daily profit cap (% of phase target)
input double   PhaseTargetAmount = 1000.0;   // Phase profit target in account currency (e.g., $1000 for 10% of $10k)

// Signal File
input string   SignalFileName = "HUX_SIGNAL.csv";  // Signal file name in MQL4/Files/

// Execution
input int      Slippage = 3;                 // Max slippage in points
input int      MagicNumber = 888888;         // EA magic number
input string   TradeComment = "HuxORB_PRO";  // Trade comment

// Logging
input bool     EnableLogging = true;         // Enable detailed logging

//+------------------------------------------------------------------+
//| GLOBAL VARIABLES                                                  |
//+------------------------------------------------------------------+

datetime g_lastSignalTime = 0;           // Prevent duplicate signal execution
double   g_dailyStartEquity = 0;         // Equity at start of day
double   g_startingBalance = 0;          // Initial balance (set on first run)
int      g_tradesToday = 0;              // Trades executed today
datetime g_currentDay = 0;               // Current trading day
bool     g_tradingEnabled = true;        // Master trading switch
bool     g_dailyTradingEnabled = true;   // Daily trading switch (resets each day)
double   g_dailyProfit = 0;              // Profit/loss for current day

// Session times (UTC)
int LONDON_START = 7;
int LONDON_END = 10;
int NY_START = 12;
int NY_END = 16;

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit()
{
   // Initialize starting balance on first run
   if(g_startingBalance == 0)
   {
      g_startingBalance = AccountBalance();
      Log(StringFormat("EA Initialized. Starting Balance: %.2f", g_startingBalance));
   }

   // Initialize daily tracking
   ResetDailyCounters();

   // Log configuration
   Log("=== HuxORB PRO EA Configuration ===");
   Log(StringFormat("Risk per trade: %.2f%%", RiskPerTradePct));
   Log(StringFormat("Max trades/day: %d", MaxTradesPerDay));
   Log(StringFormat("Max spread: %d points", MaxSpreadPoints));
   Log(StringFormat("Server UTC offset: %+d hrs", ServerUtcOffsetHrs));
   Log(StringFormat("Daily loss limit: %.2f%%", DailyLossLimitPct));
   Log(StringFormat("Max loss limit: %.2f%%", MaxLossLimitPct));
   Log(StringFormat("Profit cap: %.2f%% of target ($%.2f)", ProfitCapPctOfTarget, PhaseTargetAmount));
   Log("===================================");

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Log(StringFormat("EA stopped. Reason: %s", GetDeinitReasonText(reason)));
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   // Check if new day
   CheckNewDay();

   // Check drawdown limits
   CheckDrawdownLimits();

   // Check consistency rule
   CheckConsistencyRule();

   // Exit if trading disabled
   if(!g_tradingEnabled || !g_dailyTradingEnabled)
   {
      return;
   }

   // Check max trades per day
   if(g_tradesToday >= MaxTradesPerDay)
   {
      return;
   }

   // Read and execute signal
   ReadAndExecuteSignal();
}

//+------------------------------------------------------------------+
//| Check for new trading day and reset counters                      |
//+------------------------------------------------------------------+
void CheckNewDay()
{
   datetime serverTime = TimeCurrent();
   datetime utcTime = serverTime - (ServerUtcOffsetHrs * 3600);
   datetime currentDay = iTime(Symbol(), PERIOD_D1, 0);

   if(currentDay != g_currentDay)
   {
      // New day detected
      Log(StringFormat("=== NEW TRADING DAY: %s ===", TimeToString(currentDay, TIME_DATE)));

      g_currentDay = currentDay;
      g_tradesToday = 0;
      g_dailyStartEquity = AccountEquity();
      g_dailyProfit = 0;
      g_dailyTradingEnabled = true;

      Log(StringFormat("Daily start equity: %.2f", g_dailyStartEquity));
   }
}

//+------------------------------------------------------------------+
//| Reset daily counters (called on init)                            |
//+------------------------------------------------------------------+
void ResetDailyCounters()
{
   datetime currentDay = iTime(Symbol(), PERIOD_D1, 0);
   g_currentDay = currentDay;
   g_tradesToday = 0;
   g_dailyStartEquity = AccountEquity();
   g_dailyProfit = 0;
   g_dailyTradingEnabled = true;
}

//+------------------------------------------------------------------+
//| Check drawdown limits (daily and max)                            |
//+------------------------------------------------------------------+
void CheckDrawdownLimits()
{
   double currentEquity = AccountEquity();

   // Check daily drawdown
   if(g_dailyStartEquity > 0)
   {
      double dailyDD = ((g_dailyStartEquity - currentEquity) / g_dailyStartEquity) * 100.0;

      if(dailyDD >= DailyLossLimitPct)
      {
         if(g_dailyTradingEnabled)
         {
            g_dailyTradingEnabled = false;
            Alert(StringFormat("⛔ DAILY DRAWDOWN LIMIT HIT: %.2f%% (Limit: %.2f%%)", dailyDD, DailyLossLimitPct));
            Log(StringFormat("CRITICAL: Daily drawdown limit breached: %.2f%% >= %.2f%%. Trading disabled for today.",
                             dailyDD, DailyLossLimitPct));
         }
      }
   }

   // Check max drawdown
   if(g_startingBalance > 0)
   {
      double maxDD = ((g_startingBalance - currentEquity) / g_startingBalance) * 100.0;

      if(maxDD >= MaxLossLimitPct)
      {
         if(g_tradingEnabled)
         {
            g_tradingEnabled = false;
            Alert(StringFormat("🛑 MAX DRAWDOWN LIMIT HIT: %.2f%% (Limit: %.2f%%)", maxDD, MaxLossLimitPct));
            Log(StringFormat("CRITICAL: Max drawdown limit breached: %.2f%% >= %.2f%%. Trading disabled permanently.",
                             maxDD, MaxLossLimitPct));
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Check consistency rule (profit cap)                              |
//+------------------------------------------------------------------+
void CheckConsistencyRule()
{
   if(PhaseTargetAmount <= 0) return;  // Disabled if target not set

   // Calculate today's profit
   g_dailyProfit = AccountEquity() - g_dailyStartEquity;

   // Calculate cap threshold
   double profitCap = (ProfitCapPctOfTarget / 100.0) * PhaseTargetAmount;

   if(g_dailyProfit >= profitCap)
   {
      if(g_dailyTradingEnabled)
      {
         g_dailyTradingEnabled = false;
         double profitPct = (g_dailyProfit / PhaseTargetAmount) * 100.0;
         Alert(StringFormat("✋ CONSISTENCY RULE: Daily profit %.2f (%.1f%% of target) exceeds %.1f%% cap",
                            g_dailyProfit, profitPct, ProfitCapPctOfTarget));
         Log(StringFormat("Consistency rule triggered: Daily profit %.2f >= %.2f cap. Trading stopped for today.",
                          g_dailyProfit, profitCap));
      }
   }
}

//+------------------------------------------------------------------+
//| Check if current time is within trading sessions                 |
//+------------------------------------------------------------------+
bool IsInSession()
{
   datetime serverTime = TimeCurrent();
   datetime utcTime = serverTime - (ServerUtcOffsetHrs * 3600);

   MqlDateTime dt;
   TimeToStruct(utcTime, dt);
   int hourUTC = dt.hour;

   bool inLondon = TradeLondon && (hourUTC >= LONDON_START && hourUTC < LONDON_END);
   bool inNY = TradeNewYork && (hourUTC >= NY_START && hourUTC < NY_END);

   return (inLondon || inNY);
}

//+------------------------------------------------------------------+
//| Check if spread is acceptable                                    |
//+------------------------------------------------------------------+
bool IsSpreadOK()
{
   int currentSpread = (int)MarketInfo(Symbol(), MODE_SPREAD);

   if(currentSpread > MaxSpreadPoints)
   {
      if(EnableLogging)
      {
         Log(StringFormat("Spread too high: %d points > %d limit", currentSpread, MaxSpreadPoints));
      }
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Read signal file and execute if valid                            |
//+------------------------------------------------------------------+
void ReadAndExecuteSignal()
{
   // Session check
   if(!IsInSession())
   {
      return;  // Outside trading hours
   }

   // Spread check
   if(!IsSpreadOK())
   {
      return;
   }

   // Read signal file
   string signalPath = SignalFileName;
   int fileHandle = FileOpen(signalPath, FILE_READ|FILE_CSV|FILE_ANSI, ',');

   if(fileHandle == INVALID_HANDLE)
   {
      // No signal file - this is OK, not an error
      return;
   }

   // Parse CSV header
   string header = FileReadString(fileHandle);

   // Read signal data
   if(!FileIsEnding(fileHandle))
   {
      string symbol = FileReadString(fileHandle);
      string side = FileReadString(fileHandle);
      double entry = StringToDouble(FileReadString(fileHandle));
      double sl = StringToDouble(FileReadString(fileHandle));
      double tp = StringToDouble(FileReadString(fileHandle));
      string comment = FileReadString(fileHandle);

      FileClose(fileHandle);

      // Validate signal
      if(symbol == Symbol() && entry > 0 && sl > 0 && tp > 0)
      {
         // Check if this is a new signal (not already executed)
         datetime signalTime = TimeCurrent();

         if(signalTime != g_lastSignalTime)
         {
            // Execute signal
            ExecuteSignal(side, entry, sl, tp, comment);
            g_lastSignalTime = signalTime;

            // Delete signal file after execution to prevent re-execution
            FileDelete(signalPath);
            Log("Signal file deleted after execution.");
         }
      }
      else
      {
         FileClose(fileHandle);
         Log("Invalid signal data in file.");
      }
   }
   else
   {
      FileClose(fileHandle);
   }
}

//+------------------------------------------------------------------+
//| Execute trade signal                                              |
//+------------------------------------------------------------------+
void ExecuteSignal(string side, double entry, double sl, double tp, string comment)
{
   Log(StringFormat("=== EXECUTING SIGNAL ==="));
   Log(StringFormat("Side: %s | Entry: %.5f | SL: %.5f | TP: %.5f", side, entry, sl, tp));

   // Normalize prices
   entry = NormalizeDouble(entry, Digits);
   sl = NormalizeDouble(sl, Digits);
   tp = NormalizeDouble(tp, Digits);

   // Determine order type
   int orderType;
   if(side == "BUY")
      orderType = OP_BUY;
   else if(side == "SELL")
      orderType = OP_SELL;
   else
   {
      Log("ERROR: Invalid order side: " + side);
      return;
   }

   // Calculate position size using risk-based sizing
   double lotSize = CalculateLotSize(entry, sl, RiskPerTradePct);

   if(lotSize <= 0)
   {
      Log("ERROR: Invalid lot size calculated: " + DoubleToString(lotSize, 2));
      return;
   }

   Log(StringFormat("Calculated lot size: %.2f (Risk: %.2f%% of %.2f)",
                    lotSize, RiskPerTradePct, AccountEquity()));

   // Execute order
   int ticket = OrderSend(Symbol(), orderType, lotSize, entry, Slippage, sl, tp,
                          TradeComment + " | " + comment, MagicNumber, 0, clrGreen);

   if(ticket > 0)
   {
      g_tradesToday++;
      Log(StringFormat("✓ Trade executed successfully. Ticket: %d | Lots: %.2f | Trades today: %d/%d",
                       ticket, lotSize, g_tradesToday, MaxTradesPerDay));
      Alert(StringFormat("HuxORB: Trade #%d opened (%s %.2f lots)", ticket, side, lotSize));
   }
   else
   {
      int error = GetLastError();
      Log(StringFormat("✗ Order failed. Error: %d (%s)", error, ErrorDescription(error)));
      Alert(StringFormat("HuxORB: Order failed! Error: %d", error));
   }
}

//+------------------------------------------------------------------+
//| Calculate lot size based on risk percentage                      |
//+------------------------------------------------------------------+
double CalculateLotSize(double entry, double sl, double riskPct)
{
   // Risk amount in account currency
   double equity = AccountEquity();
   double riskAmount = equity * (riskPct / 100.0);

   // SL distance in price
   double slDistance = MathAbs(entry - sl);

   if(slDistance <= 0)
   {
      Log("ERROR: SL distance is zero or negative");
      return 0;
   }

   // Get tick value (value of 1 pip movement for 1 lot)
   double tickSize = MarketInfo(Symbol(), MODE_TICKSIZE);
   double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);

   if(tickSize <= 0 || tickValue <= 0)
   {
      Log("ERROR: Invalid tick size or tick value");
      return 0;
   }

   // Calculate lot size: Risk Amount / (SL Distance in Ticks * Tick Value)
   double slDistanceInTicks = slDistance / tickSize;
   double lotSize = riskAmount / (slDistanceInTicks * tickValue);

   // Apply lot size constraints
   double minLot = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot = MarketInfo(Symbol(), MODE_MAXLOT);
   double lotStep = MarketInfo(Symbol(), MODE_LOTSTEP);

   // Round to lot step
   lotSize = MathFloor(lotSize / lotStep) * lotStep;

   // Clamp to min/max
   lotSize = MathMax(minLot, MathMin(maxLot, lotSize));

   if(EnableLogging)
   {
      Log(StringFormat("Risk Calculation: Equity=%.2f | Risk%%=%.2f | RiskAmt=%.2f",
                       equity, riskPct, riskAmount));
      Log(StringFormat("SL Distance: %.5f (%.1f ticks) | TickValue=%.5f",
                       slDistance, slDistanceInTicks, tickValue));
      Log(StringFormat("Lot Size: %.2f (Min=%.2f, Max=%.2f, Step=%.2f)",
                       lotSize, minLot, maxLot, lotStep));
   }

   return NormalizeDouble(lotSize, 2);
}

//+------------------------------------------------------------------+
//| Logging function                                                  |
//+------------------------------------------------------------------+
void Log(string message)
{
   if(EnableLogging)
   {
      string timestamp = TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS);
      Print("[", timestamp, "] ", message);
   }
}

//+------------------------------------------------------------------+
//| Get deinit reason as text                                        |
//+------------------------------------------------------------------+
string GetDeinitReasonText(int reason)
{
   switch(reason)
   {
      case REASON_PROGRAM:     return "EA stopped by user";
      case REASON_REMOVE:      return "EA removed from chart";
      case REASON_RECOMPILE:   return "EA recompiled";
      case REASON_CHARTCHANGE: return "Chart symbol/period changed";
      case REASON_CHARTCLOSE:  return "Chart closed";
      case REASON_PARAMETERS:  return "Input parameters changed";
      case REASON_ACCOUNT:     return "Account changed";
      default:                 return "Unknown reason";
   }
}

//+------------------------------------------------------------------+
//| Get error description                                             |
//+------------------------------------------------------------------+
string ErrorDescription(int code)
{
   switch(code)
   {
      case 0:    return "No error";
      case 1:    return "No error, but result is unknown";
      case 2:    return "Common error";
      case 3:    return "Invalid trade parameters";
      case 4:    return "Trade server is busy";
      case 5:    return "Old version of the client terminal";
      case 6:    return "No connection with trade server";
      case 7:    return "Not enough rights";
      case 8:    return "Too frequent requests";
      case 9:    return "Malfunctional trade operation";
      case 64:   return "Account disabled";
      case 65:   return "Invalid account";
      case 128:  return "Trade timeout";
      case 129:  return "Invalid price";
      case 130:  return "Invalid stops";
      case 131:  return "Invalid trade volume";
      case 132:  return "Market is closed";
      case 133:  return "Trade is disabled";
      case 134:  return "Not enough money";
      case 135:  return "Price changed";
      case 136:  return "Off quotes";
      case 137:  return "Broker is busy";
      case 138:  return "Requote";
      case 139:  return "Order is locked";
      case 140:  return "Long positions only allowed";
      case 141:  return "Too many requests";
      case 145:  return "Modification denied because order too close to market";
      case 146:  return "Trade context is busy";
      case 147:  return "Expirations are denied by broker";
      case 148:  return "Amount of open and pending orders has reached the limit";
      default:   return "Unknown error: " + IntegerToString(code);
   }
}

//+------------------------------------------------------------------+
