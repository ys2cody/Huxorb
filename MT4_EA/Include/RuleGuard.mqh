//+------------------------------------------------------------------+
//|                                                    RuleGuard.mqh |
//|                         HuxORB PRO - Rule Validation Layer       |
//+------------------------------------------------------------------+
#property copyright "HuxORB Team"
#property link      "https://github.com/ys2cody/Huxorb"
#property strict

#include "Utils.mqh"
#include "NewsFilter.mqh"
#include "SessionFilter.mqh"
#include "RiskManager.mqh"
#include "ConfigProfiles.mqh"

//+------------------------------------------------------------------+
//| Rule Guard Reason Codes                                          |
//+------------------------------------------------------------------+
#define RG_OK                    "OK"
#define RG_NEWS_BLACKOUT         "NEWS_BLACKOUT"
#define RG_OUTSIDE_SESSION       "OUTSIDE_SESSION"
#define RG_DAILY_LOSS_LIMIT      "DAILY_LOSS_LIMIT"
#define RG_MAX_DD                "MAX_DD"
#define RG_SPREAD_TOO_HIGH       "SPREAD_TOO_HIGH"
#define RG_LOT_CAP               "LOT_CAP"
#define RG_MAX_OPEN_TRADES       "MAX_OPEN_TRADES"
#define RG_MAX_TRADES_TODAY      "MAX_TRADES_TODAY"
#define RG_TRADING_DISABLED      "TRADING_DISABLED"
#define RG_INVALID_PARAMS        "INVALID_PARAMS"
#define RG_ENTRY_DELAY_JITTER    "ENTRY_DELAY_JITTER"
#define RG_DRY_RUN_MODE          "DRY_RUN_MODE"

//+------------------------------------------------------------------+
//| Rule Guard Status Structure                                      |
//+------------------------------------------------------------------+
struct RuleGuardStatus
{
   bool     tradingEnabled;
   bool     inSession;
   bool     inNewsBlackout;
   double   dailyPnL;
   double   dailyDDPct;
   double   maxDDPct;
   int      tradesT oday;
   int      openTrades;
   datetime nextNewsEvent;
   string   currentSession;
   int      spreadPoints;
   bool     dryRunMode;
};

//+------------------------------------------------------------------+
//| Rule Guard Class                                                  |
//+------------------------------------------------------------------+
class CRuleGuard
{
private:
   CNewsFilter*      m_newsFilter;
   CSessionFilter*   m_sessionFilter;
   CRiskManager*     m_riskManager;
   CConfigProfiles*  m_config;

   bool              m_dryRunMode;
   bool              m_logging;
   int               m_magicNumber;

   datetime          m_pendingSignalTime;
   bool              m_hasPendingSignal;

public:
   CRuleGuard();
   ~CRuleGuard();

   // Initialization
   void Init(CNewsFilter* newsFilter, CSessionFilter* sessionFilter,
             CRiskManager* riskManager, CConfigProfiles* config,
             bool dryRun, int magic, bool logging);

   // Main validation methods
   bool CanOpenTrade(string symbol, int direction, double lotSize,
                     double entryPrice, double sl, double tp, string &reasonOut);

   bool CanModifyStops(int orderTicket, double newSL, double newTP, string &reasonOut);

   bool CanCloseTrade(int orderTicket, string &reasonOut);

   // Signal timing (for jitter support)
   void RegisterPendingSignal(datetime signalTime);
   bool IsSignalDelayExpired();
   void ClearPendingSignal();

   // Status and diagnostics
   void GetStatus(RuleGuardStatus &status);
   void PrintStatus();
   void PrintBlockReason(string reasonCode, string details = "");

   // Dry run mode
   bool IsDryRunMode() { return m_dryRunMode; }
   void SetDryRunMode(bool enabled) { m_dryRunMode = enabled; }

private:
   bool ValidateSpread(string symbol, int maxSpread, string &reasonOut);
   bool ValidateSession(string symbol, string &reasonOut);
   bool ValidateNewsBlackout(string symbol, string &reasonOut);
   bool ValidateRisk(double lotSize, string &reasonOut);
   bool ValidateParams(double entryPrice, double sl, double tp, string &reasonOut);
};

//+------------------------------------------------------------------+
//| Constructor                                                       |
//+------------------------------------------------------------------+
CRuleGuard::CRuleGuard()
{
   m_newsFilter = NULL;
   m_sessionFilter = NULL;
   m_riskManager = NULL;
   m_config = NULL;
   m_dryRunMode = false;
   m_logging = true;
   m_magicNumber = 888888;
   m_pendingSignalTime = 0;
   m_hasPendingSignal = false;
}

//+------------------------------------------------------------------+
//| Destructor                                                        |
//+------------------------------------------------------------------+
CRuleGuard::~CRuleGuard()
{
   // Note: Components are managed externally, don't delete
}

//+------------------------------------------------------------------+
//| Initialize                                                        |
//+------------------------------------------------------------------+
void CRuleGuard::Init(CNewsFilter* newsFilter, CSessionFilter* sessionFilter,
                      CRiskManager* riskManager, CConfigProfiles* config,
                      bool dryRun, int magic, bool logging)
{
   m_newsFilter = newsFilter;
   m_sessionFilter = sessionFilter;
   m_riskManager = riskManager;
   m_config = config;
   m_dryRunMode = dryRun;
   m_magicNumber = magic;
   m_logging = logging;

   LogMessage("RULEGUARD", StringFormat("Initialized (DryRun: %s, Magic: %d)",
                                        dryRun ? "YES" : "NO", magic), m_logging);

   if(m_dryRunMode)
   {
      Alert("⚠️ RULE GUARD IN DRY-RUN MODE - NO REAL TRADES WILL BE PLACED");
      LogMessage("RULEGUARD", "*** DRY-RUN MODE ACTIVE ***", true);
   }
}

//+------------------------------------------------------------------+
//| Main validation: Can we open a trade?                            |
//+------------------------------------------------------------------+
bool CRuleGuard::CanOpenTrade(string symbol, int direction, double lotSize,
                              double entryPrice, double sl, double tp, string &reasonOut)
{
   /*
      CRITICAL: All order placement MUST go through this function.

      Validation order (fail-fast):
      1. Dry-run mode check
      2. Parameter validation
      3. Spread check
      4. Session check
      5. News blackout check
      6. Risk limits check
      7. Entry delay jitter check

      Each check logs the reason if it fails.
   */

   // 1. Dry-run mode
   if(m_dryRunMode)
   {
      reasonOut = RG_DRY_RUN_MODE;
      LogMessage("RULEGUARD", FormatBlockReason(RG_DRY_RUN_MODE,
                                                StringFormat("%s %.2f lots @ %.5f",
                                                            direction == OP_BUY ? "BUY" : "SELL",
                                                            lotSize, entryPrice)), m_logging);
      return false;
   }

   // 2. Parameter validation
   if(!ValidateParams(entryPrice, sl, tp, reasonOut))
   {
      PrintBlockReason(reasonOut, StringFormat("Entry:%.5f SL:%.5f TP:%.5f", entryPrice, sl, tp));
      return false;
   }

   // 3. Spread check
   if(!ValidateSpread(symbol, m_config.GetMaxSpreadPoints(), reasonOut))
   {
      PrintBlockReason(reasonOut);
      return false;
   }

   // 4. Session check
   if(!ValidateSession(symbol, reasonOut))
   {
      PrintBlockReason(reasonOut);
      return false;
   }

   // 5. News blackout check
   if(!ValidateNewsBlackout(symbol, reasonOut))
   {
      PrintBlockReason(reasonOut);
      return false;
   }

   // 6. Risk limits check
   if(!ValidateRisk(lotSize, reasonOut))
   {
      PrintBlockReason(reasonOut);
      return false;
   }

   // 7. Entry delay jitter check
   if(m_hasPendingSignal && !IsSignalDelayExpired())
   {
      reasonOut = RG_ENTRY_DELAY_JITTER;
      int remainingSec = (int)(m_pendingSignalTime + m_config.CalculateEntryDelayJitter() - TimeCurrent());
      PrintBlockReason(reasonOut, StringFormat("Wait %d sec", remainingSec));
      return false;
   }

   // All checks passed!
   reasonOut = RG_OK;
   return true;
}

//+------------------------------------------------------------------+
//| Validate if can modify stops                                     |
//+------------------------------------------------------------------+
bool CRuleGuard::CanModifyStops(int orderTicket, double newSL, double newTP, string &reasonOut)
{
   if(m_dryRunMode)
   {
      reasonOut = RG_DRY_RUN_MODE;
      LogMessage("RULEGUARD", FormatBlockReason(RG_DRY_RUN_MODE,
                                                StringFormat("ModifyStops #%d", orderTicket)), m_logging);
      return false;
   }

   // Generally allow stop modifications
   // Could add checks here if needed (e.g., don't modify during news)

   if(m_riskManager != NULL)
   {
      if(!m_riskManager.CanModifyStops(orderTicket, newSL, newTP, reasonOut))
      {
         PrintBlockReason(reasonOut, StringFormat("Ticket:%d", orderTicket));
         return false;
      }
   }

   reasonOut = RG_OK;
   return true;
}

//+------------------------------------------------------------------+
//| Validate if can close trade                                      |
//+------------------------------------------------------------------+
bool CRuleGuard::CanCloseTrade(int orderTicket, string &reasonOut)
{
   if(m_dryRunMode)
   {
      reasonOut = RG_DRY_RUN_MODE;
      LogMessage("RULEGUARD", FormatBlockReason(RG_DRY_RUN_MODE,
                                                StringFormat("CloseTrade #%d", orderTicket)), m_logging);
      return false;
   }

   // Always allow closing trades (emergency exit)
   reasonOut = RG_OK;
   return true;
}

//+------------------------------------------------------------------+
//| Register pending signal (for jitter timing)                      |
//+------------------------------------------------------------------+
void CRuleGuard::RegisterPendingSignal(datetime signalTime)
{
   m_pendingSignalTime = signalTime;
   m_hasPendingSignal = true;

   int delaySec = m_config.CalculateEntryDelayJitter();
   if(delaySec > 0)
   {
      LogMessage("RULEGUARD", StringFormat("Signal registered, delay: %d sec", delaySec), m_logging);
   }
}

//+------------------------------------------------------------------+
//| Check if signal delay has expired                                |
//+------------------------------------------------------------------+
bool CRuleGuard::IsSignalDelayExpired()
{
   if(!m_hasPendingSignal)
      return true;

   int delaySec = m_config.CalculateEntryDelayJitter();
   return (TimeCurrent() >= m_pendingSignalTime + delaySec);
}

//+------------------------------------------------------------------+
//| Clear pending signal                                             |
//+------------------------------------------------------------------+
void CRuleGuard::ClearPendingSignal()
{
   m_hasPendingSignal = false;
   m_pendingSignalTime = 0;
   m_config.ResetJitter();
}

//+------------------------------------------------------------------+
//| Get current status                                                |
//+------------------------------------------------------------------+
void CRuleGuard::GetStatus(RuleGuardStatus &status)
{
   status.tradingEnabled = (m_riskManager != NULL) ? m_riskManager.IsTradingEnabled() : true;
   status.dryRunMode = m_dryRunMode;

   // Session status
   string sessionReason;
   status.inSession = (m_sessionFilter != NULL) ? m_sessionFilter.IsInSession(sessionReason) : true;
   status.currentSession = sessionReason;

   // News status
   string newsReason;
   status.inNewsBlackout = (m_newsFilter != NULL) ? m_newsFilter.IsNewsBlackout(Symbol(), newsReason) : false;

   datetime nextEvent;
   string nextTitle;
   if(m_newsFilter != NULL && m_newsFilter.GetNextEvent(Symbol(), nextEvent, nextTitle))
      status.nextNewsEvent = nextEvent;
   else
      status.nextNewsEvent = 0;

   // Risk status
   if(m_riskManager != NULL)
   {
      status.dailyPnL = m_riskManager.GetDailyPnL();
      status.dailyDDPct = m_riskManager.GetDailyDD();
      status.maxDDPct = m_riskManager.GetCurrentDD();
      status.tradesToday = m_riskManager.GetTradesToday();
   }
   else
   {
      status.dailyPnL = 0;
      status.dailyDDPct = 0;
      status.maxDDPct = 0;
      status.tradesToday = 0;
   }

   // Spread
   status.spreadPoints = (int)MarketInfo(Symbol(), MODE_SPREAD);

   // Open trades
   int openCount = 0;
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == m_magicNumber && OrderSymbol() == Symbol())
            openCount++;
      }
   }
   status.openTrades = openCount;
}

//+------------------------------------------------------------------+
//| Print current status                                              |
//+------------------------------------------------------------------+
void CRuleGuard::PrintStatus()
{
   RuleGuardStatus status;
   GetStatus(status);

   Print("=== RULE GUARD STATUS ===");
   Print("Mode: ", status.dryRunMode ? "DRY-RUN" : "LIVE");
   Print("Trading enabled: ", status.tradingEnabled ? "YES" : "NO");
   Print("In session: ", status.inSession ? "YES (" + status.currentSession + ")" : "NO");
   Print("News blackout: ", status.inNewsBlackout ? "YES" : "NO");
   Print("Current spread: ", status.spreadPoints, " points");
   Print("Trades today: ", status.tradesToday);
   Print("Open trades: ", status.openTrades);
   Print("Daily P&L: $", DoubleToString(status.dailyPnL, 2));
   Print("Daily DD: ", DoubleToString(status.dailyDDPct, 2), "%");
   Print("Max DD: ", DoubleToString(status.maxDDPct, 2), "%");

   if(status.nextNewsEvent > 0)
   {
      int minsUntil = (int)((status.nextNewsEvent - TimeCurrent()) / 60);
      Print("Next news event: ", TimeToString(status.nextNewsEvent), " (in ", minsUntil, " min)");
   }

   Print("=========================");
}

//+------------------------------------------------------------------+
//| Print block reason                                                |
//+------------------------------------------------------------------+
void CRuleGuard::PrintBlockReason(string reasonCode, string details = "")
{
   LogMessage("RULEGUARD", FormatBlockReason(reasonCode, details), m_logging);
}

//+------------------------------------------------------------------+
//| Validate spread                                                   |
//+------------------------------------------------------------------+
bool CRuleGuard::ValidateSpread(string symbol, int maxSpread, string &reasonOut)
{
   int currentSpread = (int)MarketInfo(symbol, MODE_SPREAD);

   if(currentSpread > maxSpread)
   {
      reasonOut = StringFormat("%s:%d>%d", RG_SPREAD_TOO_HIGH, currentSpread, maxSpread);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Validate session                                                  |
//+------------------------------------------------------------------+
bool CRuleGuard::ValidateSession(string symbol, string &reasonOut)
{
   if(m_sessionFilter == NULL)
      return true;

   string sessionName;
   if(!m_sessionFilter.IsInSession(sessionName))
   {
      reasonOut = StringFormat("%s:%s", RG_OUTSIDE_SESSION, sessionName);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Validate news blackout                                           |
//+------------------------------------------------------------------+
bool CRuleGuard::ValidateNewsBlackout(string symbol, string &reasonOut)
{
   if(m_newsFilter == NULL)
      return true;

   string newsReason;
   if(m_newsFilter.IsNewsBlackout(symbol, newsReason))
   {
      reasonOut = StringFormat("%s:%s", RG_NEWS_BLACKOUT, newsReason);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Validate risk limits                                             |
//+------------------------------------------------------------------+
bool CRuleGuard::ValidateRisk(double lotSize, string &reasonOut)
{
   if(m_riskManager == NULL)
      return true;

   if(!m_riskManager.CanOpenTrade(lotSize, reasonOut))
   {
      // Reason already set by risk manager
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Validate trade parameters                                        |
//+------------------------------------------------------------------+
bool CRuleGuard::ValidateParams(double entryPrice, double sl, double tp, string &reasonOut)
{
   if(entryPrice <= 0 || sl <= 0 || tp <= 0)
   {
      reasonOut = RG_INVALID_PARAMS;
      return false;
   }

   // Check SL and TP are on correct sides
   double slDistance = MathAbs(entryPrice - sl);
   double tpDistance = MathAbs(entryPrice - tp);

   if(slDistance < 10 * Point || tpDistance < 10 * Point)
   {
      reasonOut = StringFormat("%s:SL/TP_TOO_CLOSE", RG_INVALID_PARAMS);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
