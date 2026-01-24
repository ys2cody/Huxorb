//+------------------------------------------------------------------+
//|                                              ConfigProfiles.mqh |
//|                         HuxORB PRO - Multi-Account Profiles      |
//+------------------------------------------------------------------+
#property copyright "HuxORB Team"
#property link      "https://github.com/ys2cody/Huxorb"
#property strict

#include "Utils.mqh"

//+------------------------------------------------------------------+
//| Account Profile Structure                                         |
//+------------------------------------------------------------------+
struct AccountProfile
{
   string   profileName;        // Profile identifier
   int      instanceID;         // Instance ID (for multiple accounts)
   string   accountGroup;       // Account group (e.g., "EURUSD_LONDON")

   // Risk settings
   double   riskPerTradePct;
   double   maxLotSize;
   int      maxOpenTrades;
   int      maxTradesPerDay;

   // Timing settings
   int      entryDelayJitterSec; // 0-90 seconds jitter
   int      entryDelayBaseSec;   // Base delay before entry

   // Session settings
   bool     useLondon;
   bool     useNewYork;
   bool     useAsia;

   // News settings
   bool     newsFilterEnabled;
   int      newsMinutesBefore;
   int      newsMinutesAfter;

   // Spread settings
   int      maxSpreadPoints;

   // Seed for jitter (stable per account)
   int      accountSeed;
};

//+------------------------------------------------------------------+
//| Config Profiles Manager                                          |
//+------------------------------------------------------------------+
class CConfigProfiles
{
private:
   AccountProfile m_currentProfile;
   bool           m_initialized;
   bool           m_logging;
   datetime       m_lastJitterCalc;
   int            m_currentJitterSec;

public:
   CConfigProfiles();
   ~CConfigProfiles() {};

   // Initialization
   void Init(string profileName, int instanceID, string accountGroup, bool logging);

   // Profile loading
   void LoadProfile(string profileName);
   void LoadDefaultProfile();
   void LoadConservativeProfile();
   void LoadAggressiveProfile();

   // Getters
   double GetRiskPerTrade() { return m_currentProfile.riskPerTradePct; }
   double GetMaxLotSize() { return m_currentProfile.maxLotSize; }
   int    GetMaxOpenTrades() { return m_currentProfile.maxOpenTrades; }
   int    GetMaxTradesPerDay() { return m_currentProfile.maxTradesPerDay; }
   int    GetMaxSpreadPoints() { return m_currentProfile.maxSpreadPoints; }
   bool   GetNewsFilterEnabled() { return m_currentProfile.newsFilterEnabled; }
   int    GetNewsMinutesBefore() { return m_currentProfile.newsMinutesBefore; }
   int    GetNewsMinutesAfter() { return m_currentProfile.newsMinutesAfter; }
   bool   UseLondonSession() { return m_currentProfile.useLondon; }
   bool   UseNewYorkSession() { return m_currentProfile.useNewYork; }
   bool   UseAsiaSession() { return m_currentProfile.useAsia; }
   string GetProfileName() { return m_currentProfile.profileName; }
   int    GetInstanceID() { return m_currentProfile.instanceID; }

   // Jitter management
   int    CalculateEntryDelayJitter();
   bool   ShouldDelayEntry(datetime signalTime);
   void   ResetJitter();

   // Diagnostics
   void   PrintProfile();

private:
   void   GenerateAccountSeed();
   int    GetStableRandom(int min, int max, int seed);
};

//+------------------------------------------------------------------+
//| Constructor                                                       |
//+------------------------------------------------------------------+
CConfigProfiles::CConfigProfiles()
{
   m_initialized = false;
   m_logging = true;
   m_lastJitterCalc = 0;
   m_currentJitterSec = 0;

   // Initialize with defaults
   m_currentProfile.profileName = "DEFAULT";
   m_currentProfile.instanceID = 1;
   m_currentProfile.accountGroup = "DEFAULT";
   m_currentProfile.riskPerTradePct = 0.5;
   m_currentProfile.maxLotSize = 10.0;
   m_currentProfile.maxOpenTrades = 2;
   m_currentProfile.maxTradesPerDay = 2;
   m_currentProfile.entryDelayJitterSec = 0;
   m_currentProfile.entryDelayBaseSec = 0;
   m_currentProfile.useLondon = true;
   m_currentProfile.useNewYork = true;
   m_currentProfile.useAsia = false;
   m_currentProfile.newsFilterEnabled = false;
   m_currentProfile.newsMinutesBefore = 30;
   m_currentProfile.newsMinutesAfter = 10;
   m_currentProfile.maxSpreadPoints = 20;
   m_currentProfile.accountSeed = 12345;
}

//+------------------------------------------------------------------+
//| Initialize with account-specific settings                        |
//+------------------------------------------------------------------+
void CConfigProfiles::Init(string profileName, int instanceID, string accountGroup, bool logging)
{
   m_currentProfile.profileName = profileName;
   m_currentProfile.instanceID = instanceID;
   m_currentProfile.accountGroup = accountGroup;
   m_logging = logging;

   // Generate stable seed based on account info
   GenerateAccountSeed();

   // Load profile
   LoadProfile(profileName);

   m_initialized = true;

   LogMessage("PROFILE", StringFormat("Initialized profile: %s (Instance %d, Group: %s, Seed: %d)",
                                      profileName, instanceID, accountGroup, m_currentProfile.accountSeed),
              m_logging);
}

//+------------------------------------------------------------------+
//| Load profile by name                                             |
//+------------------------------------------------------------------+
void CConfigProfiles::LoadProfile(string profileName)
{
   // Normalize profile name
   StringToUpper(profileName);

   if(profileName == "CONSERVATIVE")
      LoadConservativeProfile();
   else if(profileName == "AGGRESSIVE")
      LoadAggressiveProfile();
   else
      LoadDefaultProfile();

   LogMessage("PROFILE", StringFormat("Loaded profile: %s", m_currentProfile.profileName), m_logging);
}

//+------------------------------------------------------------------+
//| Load default profile                                             |
//+------------------------------------------------------------------+
void CConfigProfiles::LoadDefaultProfile()
{
   m_currentProfile.profileName = "DEFAULT";
   m_currentProfile.riskPerTradePct = 0.5;
   m_currentProfile.maxLotSize = 10.0;
   m_currentProfile.maxOpenTrades = 2;
   m_currentProfile.maxTradesPerDay = 2;
   m_currentProfile.entryDelayJitterSec = 30;   // 0-30 sec jitter
   m_currentProfile.entryDelayBaseSec = 0;
   m_currentProfile.useLondon = true;
   m_currentProfile.useNewYork = true;
   m_currentProfile.useAsia = false;
   m_currentProfile.newsFilterEnabled = true;
   m_currentProfile.newsMinutesBefore = 30;
   m_currentProfile.newsMinutesAfter = 10;
   m_currentProfile.maxSpreadPoints = 20;
}

//+------------------------------------------------------------------+
//| Load conservative profile                                        |
//+------------------------------------------------------------------+
void CConfigProfiles::LoadConservativeProfile()
{
   m_currentProfile.profileName = "CONSERVATIVE";
   m_currentProfile.riskPerTradePct = 0.5;
   m_currentProfile.maxLotSize = 5.0;           // Lower lot cap
   m_currentProfile.maxOpenTrades = 1;          // Only 1 open trade
   m_currentProfile.maxTradesPerDay = 2;
   m_currentProfile.entryDelayJitterSec = 60;   // Longer jitter 0-60 sec
   m_currentProfile.entryDelayBaseSec = 10;     // 10 sec base delay
   m_currentProfile.useLondon = true;
   m_currentProfile.useNewYork = true;
   m_currentProfile.useAsia = false;
   m_currentProfile.newsFilterEnabled = true;
   m_currentProfile.newsMinutesBefore = 60;     // Wider news buffer
   m_currentProfile.newsMinutesAfter = 30;
   m_currentProfile.maxSpreadPoints = 15;       // Tighter spread
}

//+------------------------------------------------------------------+
//| Load aggressive profile                                          |
//+------------------------------------------------------------------+
void CConfigProfiles::LoadAggressiveProfile()
{
   m_currentProfile.profileName = "AGGRESSIVE";
   m_currentProfile.riskPerTradePct = 1.0;      // Higher risk
   m_currentProfile.maxLotSize = 20.0;          // Higher lot cap
   m_currentProfile.maxOpenTrades = 3;          // More open trades
   m_currentProfile.maxTradesPerDay = 3;
   m_currentProfile.entryDelayJitterSec = 15;   // Shorter jitter 0-15 sec
   m_currentProfile.entryDelayBaseSec = 0;
   m_currentProfile.useLondon = true;
   m_currentProfile.useNewYork = true;
   m_currentProfile.useAsia = true;             // Trade Asia too
   m_currentProfile.newsFilterEnabled = false;  // No news filter
   m_currentProfile.newsMinutesBefore = 15;
   m_currentProfile.newsMinutesAfter = 5;
   m_currentProfile.maxSpreadPoints = 30;       // Wider spread tolerance
}

//+------------------------------------------------------------------+
//| Calculate entry delay jitter (stable for current signal)         |
//+------------------------------------------------------------------+
int CConfigProfiles::CalculateEntryDelayJitter()
{
   /*
      IMPORTANT: Jitter is ONLY used to avoid identical timing across accounts.

      - Uses stable per-account seed (AccountNumber + InstanceID + ProfileName)
      - Jitter is recalculated every 5 minutes to provide variation
      - NEVER increases risk
      - NEVER overrides RuleGuard checks
      - NEVER causes entry during blocked windows

      Compliance: This is NOT trade mirroring - each account has:
      - Different account numbers
      - Different instance IDs
      - Different profiles (potentially)
      - Deterministic jitter based on account-specific seed
   */

   datetime currentTime = TimeCurrent();

   // Recalculate jitter every 5 minutes
   if(currentTime - m_lastJitterCalc > 300)
   {
      // Use current 5-minute bar time as additional seed component
      datetime barTime = iTime(Symbol(), PERIOD_M5, 0);
      int timeSeed = (int)(barTime % 1000);

      // Combine account seed with time seed
      int combinedSeed = m_currentProfile.accountSeed + timeSeed;

      // Generate stable random jitter
      m_currentJitterSec = GetStableRandom(0, m_currentProfile.entryDelayJitterSec, combinedSeed);

      m_lastJitterCalc = currentTime;

      LogMessage("PROFILE", StringFormat("Jitter recalculated: %d sec (max: %d)",
                                         m_currentJitterSec,
                                         m_currentProfile.entryDelayJitterSec),
                 m_logging);
   }

   return m_currentJitterSec + m_currentProfile.entryDelayBaseSec;
}

//+------------------------------------------------------------------+
//| Check if should delay entry (for jitter implementation)          |
//+------------------------------------------------------------------+
bool CConfigProfiles::ShouldDelayEntry(datetime signalTime)
{
   if(m_currentProfile.entryDelayJitterSec == 0 && m_currentProfile.entryDelayBaseSec == 0)
      return false;  // No delay configured

   int delaySec = CalculateEntryDelayJitter();
   datetime requiredTime = signalTime + delaySec;

   return (TimeCurrent() < requiredTime);
}

//+------------------------------------------------------------------+
//| Reset jitter (call when signal is executed)                      |
//+------------------------------------------------------------------+
void CConfigProfiles::ResetJitter()
{
   m_lastJitterCalc = 0;
   m_currentJitterSec = 0;
}

//+------------------------------------------------------------------+
//| Generate stable seed from account info                           |
//+------------------------------------------------------------------+
void CConfigProfiles::GenerateAccountSeed()
{
   m_currentProfile.accountSeed = GenerateAccountSeed(m_currentProfile.profileName,
                                                       m_currentProfile.instanceID);
}

//+------------------------------------------------------------------+
//| Get stable pseudo-random number                                  |
//+------------------------------------------------------------------+
int CConfigProfiles::GetStableRandom(int min, int max, int seed)
{
   // Simple LCG (Linear Congruential Generator)
   int a = 1103515245;
   int c = 12345;
   int m = 2147483647;

   int random = (a * seed + c) % m;
   int range = max - min;

   if(range <= 0)
      return min;

   return min + (MathAbs(random) % (range + 1));
}

//+------------------------------------------------------------------+
//| Print profile configuration                                      |
//+------------------------------------------------------------------+
void CConfigProfiles::PrintProfile()
{
   Print("=== ACCOUNT PROFILE ===");
   Print("Profile Name: ", m_currentProfile.profileName);
   Print("Instance ID: ", m_currentProfile.instanceID);
   Print("Account Group: ", m_currentProfile.accountGroup);
   Print("Account Seed: ", m_currentProfile.accountSeed);
   Print("");
   Print("Risk Settings:");
   Print("  Risk per trade: ", DoubleToString(m_currentProfile.riskPerTradePct, 2), "%");
   Print("  Max lot size: ", DoubleToString(m_currentProfile.maxLotSize, 2));
   Print("  Max open trades: ", m_currentProfile.maxOpenTrades);
   Print("  Max trades/day: ", m_currentProfile.maxTradesPerDay);
   Print("");
   Print("Timing Settings:");
   Print("  Entry delay jitter: 0-", m_currentProfile.entryDelayJitterSec, " sec");
   Print("  Entry delay base: ", m_currentProfile.entryDelayBaseSec, " sec");
   Print("  Current jitter: ", m_currentJitterSec, " sec");
   Print("");
   Print("Session Settings:");
   Print("  London: ", m_currentProfile.useLondon ? "YES" : "NO");
   Print("  New York: ", m_currentProfile.useNewYork ? "YES" : "NO");
   Print("  Asia: ", m_currentProfile.useAsia ? "YES" : "NO");
   Print("");
   Print("News Settings:");
   Print("  News filter: ", m_currentProfile.newsFilterEnabled ? "ENABLED" : "DISABLED");
   Print("  Minutes before: ", m_currentProfile.newsMinutesBefore);
   Print("  Minutes after: ", m_currentProfile.newsMinutesAfter);
   Print("");
   Print("Spread Settings:");
   Print("  Max spread: ", m_currentProfile.maxSpreadPoints, " points");
   Print("=======================");
}

//+------------------------------------------------------------------+
