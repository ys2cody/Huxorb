//+------------------------------------------------------------------+
//|                                      HuxORB_Bridge_EA_v2.mq4     |
//|                         HuxORB PRO - Enhanced with RuleGuard     |
//+------------------------------------------------------------------+
#property copyright "HuxORB Team"
#property link      "https://github.com/ys2cody/Huxorb"
#property version   "2.00"
#property strict

/*
   HuxORB PRO v2.0 - ENHANCED WITH RULE GUARD
   ===========================================

   MAJOR ENHANCEMENTS:
   - Modular RuleGuard validation layer
   - News blackout filter (manual + CSV modes)
   - Enhanced session control
   - Advanced risk management
   - Multi-account support with safe desynchronization
   - Dry-run mode for testing
   - Comprehensive diagnostics

   PROP FIRM COMPLIANCE:
   - All trades validated through RuleGuard
   - News blackout enforcement
   - Session validation
   - DD limits with optional auto-close
   - Consistency rule enforcement
   - Per-account jitter (NO trade mirroring)

   NO OPTIMIZATION. NO CURVE-FITTING. RULE-BASED ONLY.
*/

#include <Include/RuleGuard.mqh>

//+------------------------------------------------------------------+
//| INPUT PARAMETERS - Account & Profile                             |
//+------------------------------------------------------------------+
input string   _P1_ = "=== ACCOUNT & PROFILE ===";
input string   ProfileName = "DEFAULT";          // Profile: DEFAULT, CONSERVATIVE, AGGRESSIVE
input int      InstanceID = 1;                   // Instance ID (for multiple accounts)
input string   AccountGroup = "EURUSD_MAIN";     // Account group identifier

//+------------------------------------------------------------------+
//| INPUT PARAMETERS - Risk Management                               |
//+------------------------------------------------------------------+
input string   _P2_ = "=== RISK MANAGEMENT ===";
input double   RiskPerTradePct = 0.5;            // Risk per trade (%)
input double   MaxLotSize = 10.0;                // Maximum lot size
input int      MaxOpenTrades = 2;                // Max simultaneous trades
input int      MaxTradesPerDay = 2;              // Max trades per day
input double   DailyLossLimitPct = 4.6;          // Daily loss limit (%)
input double   MaxLossLimitPct = 9.5;            // Max overall loss limit (%)
input double   ProfitCapPctOfTarget = 40.0;      // Daily profit cap (% of target)
input double   PhaseTargetAmount = 1000.0;       // Phase profit target
input bool     CloseTradesOnDDLimit = false;     // Auto-close trades if DD limit hit

//+------------------------------------------------------------------+
//| INPUT PARAMETERS - Sessions                                      |
//+------------------------------------------------------------------+
input string   _P3_ = "=== TRADING SESSIONS ===";
input bool     TradeLondon = true;               // Trade London session (07:00-10:00 UTC)
input bool     TradeNewYork = true;              // Trade New York session (12:00-16:00 UTC)
input bool     TradeAsia = false;                // Trade Asia session (00:00-04:00 UTC)
input int      ServerUtcOffsetHrs = 2;           // Server UTC offset (FundedNext = +2)

//+------------------------------------------------------------------+
//| INPUT PARAMETERS - News Filter                                   |
//+------------------------------------------------------------------+
input string   _P4_ = "=== NEWS FILTER ===";
input bool     NewsFilterEnabled = true;         // Enable news filter
input bool     UseCSVCalendar = false;           // true=CSV calendar, false=manual blackout
input string   NewsCalendarFile = "news_calendar.csv";  // CSV calendar filename
input string   BlackoutWindowsFile = "blackout_windows.csv";  // Manual blackout filename
input int      NewsMinutesBefore = 30;           // Minutes before news
input int      NewsMinutesAfter = 10;            // Minutes after news
input bool     NewsFilterBySymbol = true;        // Only block if news affects symbol
input bool     NewsHighImpactOnly = false;       // Only block HIGH impact news

//+------------------------------------------------------------------+
//| INPUT PARAMETERS - Spread & Execution                            |
//+------------------------------------------------------------------+
input string   _P5_ = "=== EXECUTION ===";
input int      MaxSpreadPoints = 20;             // Max spread in points
input int      Slippage = 3;                     // Max slippage in points
input int      EntryDelayJitterSec = 30;         // Entry delay jitter (0-N seconds)
input int      EntryDelayBaseSec = 0;            // Entry delay base (seconds)

//+------------------------------------------------------------------+
//| INPUT PARAMETERS - Signal File & Magic                           |
//+------------------------------------------------------------------+
input string   _P6_ = "=== SIGNAL & MAGIC ===";
input string   SignalFileName = "HUX_SIGNAL.csv"; // Signal file name
input int      MagicNumber = 888888;             // EA magic number
input string   TradeComment = "HuxORB_PRO_v2";   // Trade comment

//+------------------------------------------------------------------+
//| INPUT PARAMETERS - Diagnostics                                   |
//+------------------------------------------------------------------+
input string   _P7_ = "=== DIAGNOSTICS ===";
input bool     DryRunMode = false;               // Dry-run mode (no real trades)
input bool     EnableLogging = true;             // Enable detailed logging
input bool     PrintStatusOnTick = false;        // Print status every tick (verbose!)

//+------------------------------------------------------------------+
//| GLOBAL OBJECTS                                                    |
//+------------------------------------------------------------------+
CNewsFilter*     g_newsFilter = NULL;
CSessionFilter*  g_sessionFilter = NULL;
CRiskManager*    g_riskManager = NULL;
CConfigProfiles* g_config = NULL;
CRuleGuard*      g_ruleGuard = NULL;

//+------------------------------------------------------------------+
//| GLOBAL STATE                                                      |
//+------------------------------------------------------------------+
datetime g_lastSignalTime = 0;
bool     g_initialized = false;

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("===============================================");
   Print("HuxORB PRO v2.0 - Enhanced with RuleGuard");
   Print("===============================================");

   // Create components
   g_newsFilter = new CNewsFilter();
   g_sessionFilter = new CSessionFilter();
   g_riskManager = new CRiskManager();
   g_config = new CConfigProfiles();
   g_ruleGuard = new CRuleGuard();

   // Initialize configuration profile
   g_config.Init(ProfileName, InstanceID, AccountGroup, EnableLogging);

   // Override profile settings with input parameters (if provided)
   // This allows manual override while still using profiles
   if(RiskPerTradePct > 0)
      g_config.LoadDefaultProfile();  // Would need setter methods for full override

   // Initialize news filter
   g_newsFilter.Init(NewsFilterEnabled, UseCSVCalendar,
                     NewsCalendarFile, BlackoutWindowsFile,
                     NewsMinutesBefore, NewsMinutesAfter,
                     NewsFilterBySymbol, NewsHighImpactOnly,
                     ServerUtcOffsetHrs, EnableLogging);

   // Initialize session filter
   g_sessionFilter.Init(ServerUtcOffsetHrs, EnableLogging);
   if(TradeLondon)
      g_sessionFilter.LoadLondonSession(true);
   if(TradeNewYork)
      g_sessionFilter.LoadNewYorkSession(true);
   if(TradeAsia)
      g_sessionFilter.LoadAsiaSession(true);

   // Initialize risk manager
   g_riskManager.Init(RiskPerTradePct, MaxLotSize, MaxOpenTrades, MaxTradesPerDay,
                      DailyLossLimitPct, MaxLossLimitPct, ProfitCapPctOfTarget,
                      PhaseTargetAmount, MagicNumber, CloseTradesOnDDLimit, EnableLogging);

   // Initialize RuleGuard (central validator)
   g_ruleGuard.Init(g_newsFilter, g_sessionFilter, g_riskManager, g_config,
                    DryRunMode, MagicNumber, EnableLogging);

   // Print configuration
   Print("\n=== CONFIGURATION ===");
   g_config.PrintProfile();
   Print("");
   g_sessionFilter.PrintStatus();
   Print("");
   g_newsFilter.PrintStatus();
   Print("");
   g_riskManager.PrintStatus();
   Print("");
   g_ruleGuard.PrintStatus();
   Print("=====================\n");

   if(DryRunMode)
   {
      Alert("⚠️ DRY-RUN MODE ENABLED - No real trades will be placed!");
      Comment("DRY-RUN MODE - Testing only");
   }

   g_initialized = true;

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("HuxORB PRO v2.0 stopped. Reason: ", reason);

   // Clean up
   if(g_newsFilter != NULL) delete g_newsFilter;
   if(g_sessionFilter != NULL) delete g_sessionFilter;
   if(g_riskManager != NULL) delete g_riskManager;
   if(g_config != NULL) delete g_config;
   if(g_ruleGuard != NULL) delete g_ruleGuard;

   Comment("");
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   if(!g_initialized)
      return;

   // Update risk manager (check for new day, DD limits, etc.)
   g_riskManager.CheckNewDay();
   g_riskManager.CheckDrawdownLimits();
   g_riskManager.CheckConsistencyRule();

   // Optional: Print status every tick (very verbose!)
   if(PrintStatusOnTick)
   {
      g_ruleGuard.PrintStatus();
   }

   // Check if can trade (early exit if disabled)
   if(!g_riskManager.IsTradingEnabled())
   {
      return;
   }

   // Read and process signal file
   ReadAndExecuteSignal();
}

//+------------------------------------------------------------------+
//| Read signal file and execute if valid                            |
//+------------------------------------------------------------------+
void ReadAndExecuteSignal()
{
   // Open signal file
   string signalPath = SignalFileName;
   int fileHandle = FileOpen(signalPath, FILE_READ|FILE_CSV|FILE_ANSI, ',');

   if(fileHandle == INVALID_HANDLE)
   {
      // No signal file - this is normal, not an error
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
         // Check if this is a new signal (not already processed)
         datetime signalTime = TimeCurrent();

         if(signalTime != g_lastSignalTime)
         {
            // Register signal with RuleGuard (for jitter timing)
            g_ruleGuard.RegisterPendingSignal(signalTime);

            // Execute signal
            ExecuteSignal(side, entry, sl, tp, comment);

            g_lastSignalTime = signalTime;

            // Delete signal file after processing
            FileDelete(signalPath);
            LogMessage("MAIN", "Signal file deleted after processing", EnableLogging);
         }
      }
      else
      {
         LogMessage("MAIN", "Invalid signal data in file", EnableLogging);
         FileClose(fileHandle);
      }
   }
   else
   {
      FileClose(fileHandle);
   }
}

//+------------------------------------------------------------------+
//| Execute trade signal (with RuleGuard validation)                 |
//+------------------------------------------------------------------+
void ExecuteSignal(string side, double entry, double sl, double tp, string comment)
{
   LogMessage("MAIN", "=== PROCESSING SIGNAL ===", EnableLogging);
   LogMessage("MAIN", StringFormat("Side: %s | Entry: %.5f | SL: %.5f | TP: %.5f", side, entry, sl, tp), EnableLogging);

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
      LogMessage("MAIN", "ERROR: Invalid order side: " + side, EnableLogging);
      return;
   }

   // Calculate position size
   double lotSize = g_riskManager.CalculateLotSize(Symbol(), entry, sl, RiskPerTradePct);

   if(lotSize <= 0)
   {
      LogMessage("MAIN", "ERROR: Invalid lot size calculated", EnableLogging);
      return;
   }

   LogMessage("MAIN", StringFormat("Calculated lot size: %.2f", lotSize), EnableLogging);

   // *** CRITICAL: RuleGuard validation ***
   string blockReason;
   if(!g_ruleGuard.CanOpenTrade(Symbol(), orderType, lotSize, entry, sl, tp, blockReason))
   {
      // Trade blocked by RuleGuard
      LogMessage("MAIN", StringFormat("✗ Trade BLOCKED: %s", blockReason), EnableLogging);

      if(DryRunMode)
      {
         LogMessage("MAIN", StringFormat("[DRY-RUN] Would have been blocked: %s", blockReason), EnableLogging);
      }

      return;  // Don't execute trade
   }

   // All validations passed!
   LogMessage("MAIN", "✓ All RuleGuard checks passed", EnableLogging);

   // Check if still need to wait for jitter delay
   if(!g_ruleGuard.IsSignalDelayExpired())
   {
      LogMessage("MAIN", "Waiting for entry delay jitter...", EnableLogging);
      return;  // Will retry on next tick
   }

   // Execute order
   if(DryRunMode)
   {
      LogMessage("MAIN", StringFormat("[DRY-RUN] Would place order: %s %.2f lots @ %.5f (SL:%.5f TP:%.5f)",
                                      side, lotSize, entry, sl, tp), true);
      Alert(StringFormat("[DRY-RUN] Trade simulated: %s %.2f lots", side, lotSize));

      // Clear pending signal
      g_ruleGuard.ClearPendingSignal();
      return;
   }

   // REAL ORDER PLACEMENT
   int ticket = OrderSend(Symbol(), orderType, lotSize, entry, Slippage, sl, tp,
                          TradeComment + " | " + comment, MagicNumber, 0, clrGreen);

   if(ticket > 0)
   {
      g_riskManager.IncrementTradeCount();
      g_ruleGuard.ClearPendingSignal();

      LogMessage("MAIN", StringFormat("✓ Trade executed successfully. Ticket: %d | Lots: %.2f | Trades today: %d/%d",
                                      ticket, lotSize, g_riskManager.GetTradesToday(), MaxTradesPerDay), EnableLogging);

      Alert(StringFormat("HuxORB PRO: Trade #%d opened (%s %.2f lots)", ticket, side, lotSize));
   }
   else
   {
      int error = GetLastError();
      LogMessage("MAIN", StringFormat("✗ Order failed. Error: %d (%s)", error, ErrorDescription(error)), true);
      Alert(StringFormat("HuxORB PRO: Order FAILED! Error: %d", error));
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
