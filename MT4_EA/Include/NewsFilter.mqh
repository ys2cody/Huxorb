//+------------------------------------------------------------------+
//|                                                   NewsFilter.mqh |
//|                         HuxORB PRO - News Blackout Manager       |
//+------------------------------------------------------------------+
#property copyright "HuxORB Team"
#property link      "https://github.com/ys2cody/Huxorb"
#property strict

#include "Utils.mqh"

//+------------------------------------------------------------------+
//| News Event Structure                                              |
//+------------------------------------------------------------------+
struct NewsEvent
{
   datetime eventTime;          // Event time (server time)
   string   currency;           // Currency affected (EUR, USD, etc.)
   string   impact;             // HIGH, MEDIUM, LOW
   string   title;              // Event title
   datetime blackoutStart;      // Blackout window start
   datetime blackoutEnd;        // Blackout window end
};

//+------------------------------------------------------------------+
//| News Filter Class                                                 |
//+------------------------------------------------------------------+
class CNewsFilter
{
private:
   NewsEvent m_events[];        // Array of news events
   int       m_eventCount;      // Number of events loaded
   datetime  m_lastReloadTime;  // Last time calendar was reloaded
   int       m_reloadIntervalMin;  // Reload interval in minutes

   // Configuration
   bool      m_enabled;
   bool      m_useCSVCalendar;  // true = CSV mode, false = manual mode
   string    m_calendarFile;
   string    m_blackoutFile;
   int       m_minutesBefore;
   int       m_minutesAfter;
   bool      m_filterBySymbol;  // Only block if event affects symbol currencies
   bool      m_highImpactOnly;  // Only block HIGH impact events
   int       m_serverOffsetHrs;
   bool      m_logging;

public:
   CNewsFilter();
   ~CNewsFilter() {};

   // Initialization
   void Init(bool enabled, bool useCSV, string calFile, string blackoutFile,
             int minBefore, int minAfter, bool filterSymbol, bool highOnly,
             int serverOffset, bool logging);

   // Main validation
   bool IsNewsBlackout(string symbol, string &reasonOut);

   // Manual blackout window management
   void AddManualBlackout(datetime start, datetime end, string currency, string impact);
   void ClearManualBlackouts();

   // Calendar loading
   bool LoadCSVCalendar();
   bool LoadBlackoutWindows();
   void ReloadIfNeeded();

   // Diagnostics
   int  GetEventCount() { return m_eventCount; }
   void PrintStatus();
   bool GetNextEvent(string symbol, datetime &eventTime, string &title);

private:
   bool ParseCSVLine(string line, NewsEvent &event);
   bool IsEventAffectingSymbol(NewsEvent &event, string symbol);
   datetime ConvertToServerTime(datetime utcTime);
};

//+------------------------------------------------------------------+
//| Constructor                                                       |
//+------------------------------------------------------------------+
CNewsFilter::CNewsFilter()
{
   m_eventCount = 0;
   m_lastReloadTime = 0;
   m_reloadIntervalMin = 10;  // Reload every 10 minutes
   m_enabled = false;
   m_useCSVCalendar = false;
   m_minutesBefore = 30;
   m_minutesAfter = 10;
   m_filterBySymbol = true;
   m_highImpactOnly = false;
   m_serverOffsetHrs = 2;
   m_logging = true;
   ArrayResize(m_events, 0);
}

//+------------------------------------------------------------------+
//| Initialize filter                                                 |
//+------------------------------------------------------------------+
void CNewsFilter::Init(bool enabled, bool useCSV, string calFile, string blackoutFile,
                       int minBefore, int minAfter, bool filterSymbol, bool highOnly,
                       int serverOffset, bool logging)
{
   m_enabled = enabled;
   m_useCSVCalendar = useCSV;
   m_calendarFile = calFile;
   m_blackoutFile = blackoutFile;
   m_minutesBefore = minBefore;
   m_minutesAfter = minAfter;
   m_filterBySymbol = filterSymbol;
   m_highImpactOnly = highOnly;
   m_serverOffsetHrs = serverOffset;
   m_logging = logging;

   if(!m_enabled)
   {
      LogMessage("NEWS", "News filter DISABLED", m_logging);
      return;
   }

   // Load events based on mode
   if(m_useCSVCalendar)
   {
      if(LoadCSVCalendar())
         LogMessage("NEWS", StringFormat("CSV Calendar loaded: %d events", m_eventCount), m_logging);
      else
         LogMessage("NEWS", "WARNING: Failed to load CSV calendar", m_logging);
   }
   else
   {
      if(LoadBlackoutWindows())
         LogMessage("NEWS", StringFormat("Manual blackout windows loaded: %d events", m_eventCount), m_logging);
      else
         LogMessage("NEWS", "No manual blackout windows loaded", m_logging);
   }
}

//+------------------------------------------------------------------+
//| Check if we're in a news blackout                                |
//+------------------------------------------------------------------+
bool CNewsFilter::IsNewsBlackout(string symbol, string &reasonOut)
{
   if(!m_enabled)
      return false;

   // Reload calendar if needed
   ReloadIfNeeded();

   datetime currentTime = TimeCurrent();

   // Check each event
   for(int i = 0; i < m_eventCount; i++)
   {
      if(IsTimeInRange(currentTime, m_events[i].blackoutStart, m_events[i].blackoutEnd))
      {
         // Check if event affects this symbol
         if(m_filterBySymbol && !IsEventAffectingSymbol(m_events[i], symbol))
            continue;

         // Check impact filter
         if(m_highImpactOnly && m_events[i].impact != "HIGH")
            continue;

         // We're in blackout!
         reasonOut = StringFormat("NEWS:%s:%s (in %d min)",
                                  m_events[i].currency,
                                  m_events[i].impact,
                                  (int)((m_events[i].eventTime - currentTime) / 60));
         return true;
      }
   }

   return false;
}

//+------------------------------------------------------------------+
//| Add manual blackout window                                        |
//+------------------------------------------------------------------+
void CNewsFilter::AddManualBlackout(datetime start, datetime end, string currency, string impact)
{
   int index = m_eventCount;
   ArrayResize(m_events, m_eventCount + 1);

   m_events[index].eventTime = start;
   m_events[index].currency = currency;
   m_events[index].impact = impact;
   m_events[index].title = "Manual Blackout";
   m_events[index].blackoutStart = start;
   m_events[index].blackoutEnd = end;

   m_eventCount++;
}

//+------------------------------------------------------------------+
//| Clear all manual blackouts                                        |
//+------------------------------------------------------------------+
void CNewsFilter::ClearManualBlackouts()
{
   ArrayResize(m_events, 0);
   m_eventCount = 0;
}

//+------------------------------------------------------------------+
//| Load CSV calendar file                                            |
//+------------------------------------------------------------------+
bool CNewsFilter::LoadCSVCalendar()
{
   /*
      Expected CSV format:
      DateTime,Currency,Impact,Title
      2025-01-24 14:30:00,USD,HIGH,FOMC Rate Decision
      2025-01-24 08:30:00,EUR,MEDIUM,ECB Press Conference

      Notes:
      - DateTime must be in UTC (will be converted to server time)
      - Currency: EUR, USD, GBP, JPY, etc.
      - Impact: HIGH, MEDIUM, LOW
   */

   ClearManualBlackouts();

   int handle = FileOpen(m_calendarFile, FILE_READ|FILE_CSV|FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      LogMessage("NEWS", "Failed to open calendar file: " + m_calendarFile, m_logging);
      return false;
   }

   // Skip header
   string header = FileReadString(handle);

   int loaded = 0;
   while(!FileIsEnding(handle))
   {
      string line = FileReadString(handle);
      if(StringLen(line) < 10)
         continue;

      // Parse line manually since FileReadString already split by comma
      string dateTimeStr = FileReadString(handle);
      string currency = FileReadString(handle);
      string impact = FileReadString(handle);
      string title = FileReadString(handle);

      // Parse datetime (format: YYYY-MM-DD HH:MM:SS)
      datetime eventTime = ParseISODateTime(dateTimeStr);
      if(eventTime == 0)
         continue;

      // Convert UTC to server time
      datetime serverTime = ConvertToServerTime(eventTime);

      // Calculate blackout window
      datetime blackoutStart = serverTime - (m_minutesBefore * 60);
      datetime blackoutEnd = serverTime + (m_minutesAfter * 60);

      // Skip past events (more than 1 hour ago)
      if(blackoutEnd < TimeCurrent() - 3600)
         continue;

      // Add event
      int index = m_eventCount;
      ArrayResize(m_events, m_eventCount + 1);

      m_events[index].eventTime = serverTime;
      m_events[index].currency = StringTrim(currency);
      m_events[index].impact = StringTrim(impact);
      m_events[index].title = StringTrim(title);
      m_events[index].blackoutStart = blackoutStart;
      m_events[index].blackoutEnd = blackoutEnd;

      m_eventCount++;
      loaded++;
   }

   FileClose(handle);

   LogMessage("NEWS", StringFormat("Loaded %d events from CSV calendar", loaded), m_logging);
   return (loaded > 0);
}

//+------------------------------------------------------------------+
//| Load manual blackout windows file                                |
//+------------------------------------------------------------------+
bool CNewsFilter::LoadBlackoutWindows()
{
   /*
      Expected format:
      StartDateTime,EndDateTime,Currency,Impact
      2025-01-24 14:00:00,2025-01-24 15:00:00,USD,HIGH
      2025-01-24 08:00:00,2025-01-24 09:00:00,EUR,MEDIUM

      All times in SERVER time (not UTC!)
   */

   ClearManualBlackouts();

   int handle = FileOpen(m_blackoutFile, FILE_READ|FILE_CSV|FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      LogMessage("NEWS", "No manual blackout file found: " + m_blackoutFile, m_logging);
      return false;
   }

   // Skip header
   string header = FileReadString(handle);

   int loaded = 0;
   while(!FileIsEnding(handle))
   {
      string startStr = FileReadString(handle);
      string endStr = FileReadString(handle);
      string currency = FileReadString(handle);
      string impact = FileReadString(handle);

      datetime startTime = ParseISODateTime(startStr);
      datetime endTime = ParseISODateTime(endStr);

      if(startTime == 0 || endTime == 0)
         continue;

      // Skip past windows
      if(endTime < TimeCurrent() - 3600)
         continue;

      AddManualBlackout(startTime, endTime, currency, impact);
      loaded++;
   }

   FileClose(handle);

   LogMessage("NEWS", StringFormat("Loaded %d manual blackout windows", loaded), m_logging);
   return (loaded > 0);
}

//+------------------------------------------------------------------+
//| Reload calendar if interval passed                               |
//+------------------------------------------------------------------+
void CNewsFilter::ReloadIfNeeded()
{
   datetime now = TimeCurrent();
   if(now - m_lastReloadTime < m_reloadIntervalMin * 60)
      return;

   m_lastReloadTime = now;

   if(m_useCSVCalendar)
      LoadCSVCalendar();
   else
      LoadBlackoutWindows();
}

//+------------------------------------------------------------------+
//| Convert UTC time to server time                                  |
//+------------------------------------------------------------------+
datetime CNewsFilter::ConvertToServerTime(datetime utcTime)
{
   return utcTime + (m_serverOffsetHrs * 3600);
}

//+------------------------------------------------------------------+
//| Check if event affects symbol                                    |
//+------------------------------------------------------------------+
bool CNewsFilter::IsEventAffectingSymbol(NewsEvent &event, string symbol)
{
   return SymbolContainsCurrency(symbol, event.currency);
}

//+------------------------------------------------------------------+
//| Print current status                                              |
//+------------------------------------------------------------------+
void CNewsFilter::PrintStatus()
{
   Print("=== NEWS FILTER STATUS ===");
   Print("Enabled: ", m_enabled ? "YES" : "NO");
   Print("Mode: ", m_useCSVCalendar ? "CSV Calendar" : "Manual Blackout Windows");
   Print("Events loaded: ", m_eventCount);
   Print("Minutes before/after: ", m_minutesBefore, "/", m_minutesAfter);
   Print("Filter by symbol: ", m_filterBySymbol ? "YES" : "NO");
   Print("High impact only: ", m_highImpactOnly ? "YES" : "NO");

   datetime now = TimeCurrent();
   Print("\nUpcoming events (next 24h):");
   for(int i = 0; i < m_eventCount; i++)
   {
      if(m_events[i].eventTime > now && m_events[i].eventTime < now + 86400)
      {
         Print(StringFormat("  %s | %s | %s | %s",
                            TimeToString(m_events[i].eventTime),
                            m_events[i].currency,
                            m_events[i].impact,
                            m_events[i].title));
      }
   }
   Print("==========================");
}

//+------------------------------------------------------------------+
//| Get next event for symbol                                        |
//+------------------------------------------------------------------+
bool CNewsFilter::GetNextEvent(string symbol, datetime &eventTime, string &title)
{
   datetime now = TimeCurrent();
   datetime nextEvent = 0;
   string nextTitle = "";

   for(int i = 0; i < m_eventCount; i++)
   {
      if(m_events[i].eventTime > now)
      {
         if(m_filterBySymbol && !IsEventAffectingSymbol(m_events[i], symbol))
            continue;

         if(nextEvent == 0 || m_events[i].eventTime < nextEvent)
         {
            nextEvent = m_events[i].eventTime;
            nextTitle = m_events[i].title;
         }
      }
   }

   if(nextEvent > 0)
   {
      eventTime = nextEvent;
      title = nextTitle;
      return true;
   }

   return false;
}

//+------------------------------------------------------------------+
