//+------------------------------------------------------------------+
//|                                                 RiskManager.mqh  |
//|                         HuxORB PRO - Risk Management             |
//+------------------------------------------------------------------+
#property copyright "HuxORB Team"
#property link      "https://github.com/ys2cody/Huxorb"
#property strict

#include "Utils.mqh"

//+------------------------------------------------------------------+
//| Risk Manager Class                                                |
//+------------------------------------------------------------------+
class CRiskManager
{
private:
   // Risk limits
   double   m_riskPerTradePct;
   double   m_maxLotSize;
   int      m_maxOpenTrades;
   int      m_maxTradesPerDay;

   // Drawdown limits
   double   m_dailyLossLimitPct;
   double   m_maxLossLimitPct;
   double   m_dailyProfitCapPct;
   double   m_phaseTargetAmount;

   // State tracking
   double   m_startingBalance;
   double   m_dailyStartEquity;
   datetime m_currentDay;
   int      m_tradesToday;
   bool     m_tradingEnabled;
   bool     m_dailyTradingEnabled;

   // Configuration
   bool     m_closeOnDDLimit;    // Close trades if DD limit hit
   int      m_magicNumber;
   bool     m_logging;

public:
   CRiskManager();
   ~CRiskManager() {};

   void Init(double riskPct, double maxLot, int maxOpen, int maxPerDay,
             double dailyLossPct, double maxLossPct, double profitCapPct,
             double phaseTarget, int magic, bool closeOnDD, bool logging);

   // Validation
   bool CanOpenTrade(double lotSize, string &reasonOut);
   bool CanModifyStops(int ticket, double newSL, double newTP, string &reasonOut);
   bool CanCloseTrade(int ticket, string &reasonOut);

   // Risk calculation
   double CalculateLotSize(string symbol, double entry, double sl, double riskPct);

   // Daily management
   void CheckNewDay();
   void CheckDrawdownLimits();
   void CheckConsistencyRule();

   // State management
   void IncrementTradeCount() { m_tradesToday++; }
   bool IsTradingEnabled() { return m_tradingEnabled && m_dailyTradingEnabled; }
   void DisableTrading(string reason);

   // Getters
   int  GetTradesToday() { return m_tradesToday; }
   double GetDailyPnL() { return AccountEquity() - m_dailyStartEquity; }
   double GetCurrentDD() { return ((m_startingBalance - AccountEquity()) / m_startingBalance) * 100.0; }
   double GetDailyDD() { return ((m_dailyStartEquity - AccountEquity()) / m_dailyStartEquity) * 100.0; }

   // Diagnostics
   void PrintStatus();

private:
   int CountOpenTrades(int magic);
   void CloseAllTrades(int magic, string reason);
};

//+------------------------------------------------------------------+
//| Constructor                                                       |
//+------------------------------------------------------------------+
CRiskManager::CRiskManager()
{
   m_riskPerTradePct = 0.5;
   m_maxLotSize = 10.0;
   m_maxOpenTrades = 2;
   m_maxTradesPerDay = 2;
   m_dailyLossLimitPct = 4.6;
   m_maxLossLimitPct = 9.5;
   m_dailyProfitCapPct = 40.0;
   m_phaseTargetAmount = 1000.0;
   m_startingBalance = 0;
   m_dailyStartEquity = 0;
   m_currentDay = 0;
   m_tradesToday = 0;
   m_tradingEnabled = true;
   m_dailyTradingEnabled = true;
   m_closeOnDDLimit = false;
   m_magicNumber = 888888;
   m_logging = true;
}

//+------------------------------------------------------------------+
//| Initialize                                                        |
//+------------------------------------------------------------------+
void CRiskManager::Init(double riskPct, double maxLot, int maxOpen, int maxPerDay,
                        double dailyLossPct, double maxLossPct, double profitCapPct,
                        double phaseTarget, int magic, bool closeOnDD, bool logging)
{
   m_riskPerTradePct = riskPct;
   m_maxLotSize = maxLot;
   m_maxOpenTrades = maxOpen;
   m_maxTradesPerDay = maxPerDay;
   m_dailyLossLimitPct = dailyLossPct;
   m_maxLossLimitPct = maxLossPct;
   m_dailyProfitCapPct = profitCapPct;
   m_phaseTargetAmount = phaseTarget;
   m_magicNumber = magic;
   m_closeOnDDLimit = closeOnDD;
   m_logging = logging;

   // Initialize balance tracking
   if(m_startingBalance == 0)
   {
      m_startingBalance = AccountBalance();
      LogMessage("RISK", StringFormat("Starting balance: %.2f", m_startingBalance), m_logging);
   }

   // Initialize daily tracking
   CheckNewDay();
}

//+------------------------------------------------------------------+
//| Check if can open trade                                          |
//+------------------------------------------------------------------+
bool CRiskManager::CanOpenTrade(double lotSize, string &reasonOut)
{
   // Check trading enabled
   if(!m_tradingEnabled)
   {
      reasonOut = "RG_MAX_DD_LIMIT";
      return false;
   }

   if(!m_dailyTradingEnabled)
   {
      reasonOut = "RG_DAILY_LIMIT";
      return false;
   }

   // Check max trades per day
   if(m_tradesToday >= m_maxTradesPerDay)
   {
      reasonOut = StringFormat("RG_MAX_TRADES_TODAY:%d/%d", m_tradesToday, m_maxTradesPerDay);
      return false;
   }

   // Check max open trades
   int openTrades = CountOpenTrades(m_magicNumber);
   if(openTrades >= m_maxOpenTrades)
   {
      reasonOut = StringFormat("RG_MAX_OPEN_TRADES:%d/%d", openTrades, m_maxOpenTrades);
      return false;
   }

   // Check lot size
   if(lotSize > m_maxLotSize)
   {
      reasonOut = StringFormat("RG_LOT_CAP:%.2f>%.2f", lotSize, m_maxLotSize);
      return false;
   }

   if(lotSize <= 0)
   {
      reasonOut = "RG_INVALID_LOT:<=0";
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Check if can modify stops                                        |
//+------------------------------------------------------------------+
bool CRiskManager::CanModifyStops(int ticket, double newSL, double newTP, string &reasonOut)
{
   // Generally allow modifications unless trading is completely disabled
   if(!m_tradingEnabled)
   {
      reasonOut = "RG_TRADING_DISABLED";
      return false;
   }

   // Could add more checks here if needed
   return true;
}

//+------------------------------------------------------------------+
//| Check if can close trade                                         |
//+------------------------------------------------------------------+
bool CRiskManager::CanCloseTrade(int ticket, string &reasonOut)
{
   // Always allow closing trades
   return true;
}

//+------------------------------------------------------------------+
//| Calculate lot size based on risk                                 |
//+------------------------------------------------------------------+
double CRiskManager::CalculateLotSize(string symbol, double entry, double sl, double riskPct)
{
   // Risk amount in account currency
   double equity = AccountEquity();
   double riskAmount = equity * (riskPct / 100.0);

   // SL distance in price
   double slDistance = MathAbs(entry - sl);

   if(slDistance <= 0)
   {
      LogMessage("RISK", "ERROR: SL distance is zero or negative", m_logging);
      return 0;
   }

   // Get tick value (value of 1 pip movement for 1 lot)
   double tickSize = MarketInfo(symbol, MODE_TICKSIZE);
   double tickValue = MarketInfo(symbol, MODE_TICKVALUE);

   if(tickSize <= 0 || tickValue <= 0)
   {
      LogMessage("RISK", "ERROR: Invalid tick size or tick value", m_logging);
      return 0;
   }

   // Calculate lot size
   double slDistanceInTicks = slDistance / tickSize;
   double lotSize = riskAmount / (slDistanceInTicks * tickValue);

   // Apply lot size constraints
   double minLot = MarketInfo(symbol, MODE_MINLOT);
   double maxLot = MarketInfo(symbol, MODE_MAXLOT);
   double lotStep = MarketInfo(symbol, MODE_LOTSTEP);

   // Round to lot step
   lotSize = MathFloor(lotSize / lotStep) * lotStep;

   // Clamp to min/max
   lotSize = MathMax(minLot, MathMin(maxLot, lotSize));

   // Cap at configured max
   lotSize = MathMin(lotSize, m_maxLotSize);

   return NormalizeDouble(lotSize, 2);
}

//+------------------------------------------------------------------+
//| Check for new day and reset counters                             |
//+------------------------------------------------------------------+
void CRiskManager::CheckNewDay()
{
   datetime currentDay = iTime(Symbol(), PERIOD_D1, 0);

   if(currentDay != m_currentDay)
   {
      LogMessage("RISK", StringFormat("=== NEW DAY: %s ===", TimeToString(currentDay, TIME_DATE)), m_logging);

      m_currentDay = currentDay;
      m_tradesToday = 0;
      m_dailyStartEquity = AccountEquity();
      m_dailyTradingEnabled = true;

      LogMessage("RISK", StringFormat("Daily start equity: %.2f", m_dailyStartEquity), m_logging);
   }
}

//+------------------------------------------------------------------+
//| Check drawdown limits                                            |
//+------------------------------------------------------------------+
void CRiskManager::CheckDrawdownLimits()
{
   double currentEquity = AccountEquity();

   // Check daily drawdown
   if(m_dailyStartEquity > 0)
   {
      double dailyDD = GetDailyDD();

      if(dailyDD >= m_dailyLossLimitPct)
      {
         if(m_dailyTradingEnabled)
         {
            m_dailyTradingEnabled = false;
            string msg = StringFormat("DAILY DD LIMIT HIT: %.2f%% >= %.2f%%", dailyDD, m_dailyLossLimitPct);
            Alert("⛔ " + msg);
            LogMessage("RISK", "CRITICAL: " + msg, m_logging);

            if(m_closeOnDDLimit)
               CloseAllTrades(m_magicNumber, "Daily DD Limit");
         }
      }
   }

   // Check max drawdown
   if(m_startingBalance > 0)
   {
      double maxDD = GetCurrentDD();

      if(maxDD >= m_maxLossLimitPct)
      {
         if(m_tradingEnabled)
         {
            m_tradingEnabled = false;
            string msg = StringFormat("MAX DD LIMIT HIT: %.2f%% >= %.2f%%", maxDD, m_maxLossLimitPct);
            Alert("🛑 " + msg);
            LogMessage("RISK", "CRITICAL: " + msg, m_logging);

            if(m_closeOnDDLimit)
               CloseAllTrades(m_magicNumber, "Max DD Limit");
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Check consistency rule (profit cap)                              |
//+------------------------------------------------------------------+
void CRiskManager::CheckConsistencyRule()
{
   if(m_phaseTargetAmount <= 0)
      return;

   double dailyProfit = GetDailyPnL();
   double profitCap = (m_dailyProfitCapPct / 100.0) * m_phaseTargetAmount;

   if(dailyProfit >= profitCap)
   {
      if(m_dailyTradingEnabled)
      {
         m_dailyTradingEnabled = false;
         double profitPct = (dailyProfit / m_phaseTargetAmount) * 100.0;
         string msg = StringFormat("CONSISTENCY RULE: Profit %.2f (%.1f%% of target) >= %.1f%% cap",
                                   dailyProfit, profitPct, m_dailyProfitCapPct);
         Alert("✋ " + msg);
         LogMessage("RISK", msg, m_logging);
      }
   }
}

//+------------------------------------------------------------------+
//| Disable trading                                                   |
//+------------------------------------------------------------------+
void CRiskManager::DisableTrading(string reason)
{
   m_tradingEnabled = false;
   LogMessage("RISK", "TRADING DISABLED: " + reason, m_logging);
}

//+------------------------------------------------------------------+
//| Count open trades with magic number                              |
//+------------------------------------------------------------------+
int CRiskManager::CountOpenTrades(int magic)
{
   int count = 0;
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == magic && OrderSymbol() == Symbol())
            count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Close all trades                                                  |
//+------------------------------------------------------------------+
void CRiskManager::CloseAllTrades(int magic, string reason)
{
   LogMessage("RISK", "CLOSING ALL TRADES: " + reason, m_logging);

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == magic && OrderSymbol() == Symbol())
         {
            bool closed = false;
            if(OrderType() == OP_BUY)
               closed = OrderClose(OrderTicket(), OrderLots(), Bid, 3);
            else if(OrderType() == OP_SELL)
               closed = OrderClose(OrderTicket(), OrderLots(), Ask, 3);

            if(closed)
               LogMessage("RISK", StringFormat("Closed ticket %d", OrderTicket()), m_logging);
            else
               LogMessage("RISK", StringFormat("Failed to close ticket %d", OrderTicket()), m_logging);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Print status                                                      |
//+------------------------------------------------------------------+
void CRiskManager::PrintStatus()
{
   Print("=== RISK MANAGER STATUS ===");
   Print("Trading enabled: ", m_tradingEnabled ? "YES" : "NO");
   Print("Daily trading enabled: ", m_dailyTradingEnabled ? "YES" : "NO");
   Print("Trades today: ", m_tradesToday, "/", m_maxTradesPerDay);
   Print("Open trades: ", CountOpenTrades(m_magicNumber), "/", m_maxOpenTrades);
   Print("Current equity: ", DoubleToString(AccountEquity(), 2));
   Print("Daily P&L: ", DoubleToString(GetDailyPnL(), 2));
   Print("Daily DD: ", DoubleToString(GetDailyDD(), 2), "%");
   Print("Max DD: ", DoubleToString(GetCurrentDD(), 2), "%");
   Print("Risk per trade: ", DoubleToString(m_riskPerTradePct, 2), "%");
   Print("Max lot size: ", DoubleToString(m_maxLotSize, 2));
   Print("===========================");
}

//+------------------------------------------------------------------+
