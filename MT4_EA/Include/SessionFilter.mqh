//+------------------------------------------------------------------+
//|                                                SessionFilter.mqh |
//|                         HuxORB PRO - Session Control             |
//+------------------------------------------------------------------+
#property copyright "HuxORB Team"
#property link      "https://github.com/ys2cody/Huxorb"
#property strict

#include "Utils.mqh"

//+------------------------------------------------------------------+
//| Trading Session Structure                                         |
//+------------------------------------------------------------------+
struct TradingSession
{
   string   name;               // Session name (e.g., "London")
   int      startHour;          // Start hour (UTC)
   int      startMinute;        // Start minute
   int      endHour;            // End hour (UTC)
   int      endMinute;          // End minute
   bool     monday;             // Trade on Monday
   bool     tuesday;
   bool     wednesday;
   bool     thursday;
   bool     friday;
   bool     enabled;            // Session enabled
};

//+------------------------------------------------------------------+
//| Session Filter Class                                              |
//+------------------------------------------------------------------+
class CSessionFilter
{
private:
   TradingSession m_sessions[];
   int            m_sessionCount;
   int            m_serverOffsetHrs;
   bool           m_logging;

public:
   CSessionFilter();
   ~CSessionFilter() {};

   void Init(int serverOffset, bool logging);

   // Session management
   void AddSession(string name, int startH, int startM, int endH, int endM,
                   bool mon, bool tue, bool wed, bool thu, bool fri, bool enabled);
   void ClearSessions();

   // Validation
   bool IsInSession(string &reasonOut);
   bool IsInSession() { string dummy; return IsInSession(dummy); }

   // Presets
   void LoadLondonSession(bool enabled = true);
   void LoadNewYorkSession(bool enabled = true);
   void LoadAsiaSession(bool enabled = true);
   void LoadAllMajorSessions();

   // Diagnostics
   void PrintStatus();
   void PrintCurrentSession();
   bool GetCurrentSession(string &sessionName);

private:
   bool IsTimeInSession(TradingSession &session, datetime utcTime, int dayOfWeek);
   bool IsSessionCrossingMidnight(TradingSession &session);
};

//+------------------------------------------------------------------+
//| Constructor                                                       |
//+------------------------------------------------------------------+
CSessionFilter::CSessionFilter()
{
   m_sessionCount = 0;
   m_serverOffsetHrs = 2;
   m_logging = true;
   ArrayResize(m_sessions, 0);
}

//+------------------------------------------------------------------+
//| Initialize                                                        |
//+------------------------------------------------------------------+
void CSessionFilter::Init(int serverOffset, bool logging)
{
   m_serverOffsetHrs = serverOffset;
   m_logging = logging;
}

//+------------------------------------------------------------------+
//| Add trading session                                               |
//+------------------------------------------------------------------+
void CSessionFilter::AddSession(string name, int startH, int startM, int endH, int endM,
                                bool mon, bool tue, bool wed, bool thu, bool fri, bool enabled)
{
   int index = m_sessionCount;
   ArrayResize(m_sessions, m_sessionCount + 1);

   m_sessions[index].name = name;
   m_sessions[index].startHour = startH;
   m_sessions[index].startMinute = startM;
   m_sessions[index].endHour = endH;
   m_sessions[index].endMinute = endM;
   m_sessions[index].monday = mon;
   m_sessions[index].tuesday = tue;
   m_sessions[index].wednesday = wed;
   m_sessions[index].thursday = thu;
   m_sessions[index].friday = fri;
   m_sessions[index].enabled = enabled;

   m_sessionCount++;

   LogMessage("SESSION", StringFormat("Added session: %s (%02d:%02d-%02d:%02d) %s",
                                      name, startH, startM, endH, endM,
                                      enabled ? "ENABLED" : "DISABLED"), m_logging);
}

//+------------------------------------------------------------------+
//| Clear all sessions                                                |
//+------------------------------------------------------------------+
void CSessionFilter::ClearSessions()
{
   ArrayResize(m_sessions, 0);
   m_sessionCount = 0;
}

//+------------------------------------------------------------------+
//| Check if currently in a trading session                          |
//+------------------------------------------------------------------+
bool CSessionFilter::IsInSession(string &reasonOut)
{
   if(m_sessionCount == 0)
   {
      reasonOut = "NO_SESSIONS_CONFIGURED";
      return false;
   }

   // Get UTC time
   datetime utcTime = GetUTCTime(m_serverOffsetHrs);

   MqlDateTime dt;
   TimeToStruct(utcTime, dt);
   int dayOfWeek = dt.day_of_week;  // 0=Sunday, 1=Monday, ..., 6=Saturday

   // Check each session
   for(int i = 0; i < m_sessionCount; i++)
   {
      if(!m_sessions[i].enabled)
         continue;

      if(IsTimeInSession(m_sessions[i], utcTime, dayOfWeek))
      {
         reasonOut = m_sessions[i].name;
         return true;
      }
   }

   reasonOut = "OUTSIDE_ALL_SESSIONS";
   return false;
}

//+------------------------------------------------------------------+
//| Check if time is within a specific session                       |
//+------------------------------------------------------------------+
bool CSessionFilter::IsTimeInSession(TradingSession &session, datetime utcTime, int dayOfWeek)
{
   MqlDateTime dt;
   TimeToStruct(utcTime, dt);

   // Check day of week
   bool validDay = false;
   switch(dayOfWeek)
   {
      case 1: validDay = session.monday; break;
      case 2: validDay = session.tuesday; break;
      case 3: validDay = session.wednesday; break;
      case 4: validDay = session.thursday; break;
      case 5: validDay = session.friday; break;
      default: validDay = false;  // Weekend
   }

   if(!validDay)
      return false;

   // Check time
   int currentMinutes = dt.hour * 60 + dt.min;
   int startMinutes = session.startHour * 60 + session.startMinute;
   int endMinutes = session.endHour * 60 + session.endMinute;

   // Handle sessions crossing midnight
   if(IsSessionCrossingMidnight(session))
   {
      return (currentMinutes >= startMinutes || currentMinutes < endMinutes);
   }
   else
   {
      return (currentMinutes >= startMinutes && currentMinutes < endMinutes);
   }
}

//+------------------------------------------------------------------+
//| Check if session crosses midnight                                |
//+------------------------------------------------------------------+
bool CSessionFilter::IsSessionCrossingMidnight(TradingSession &session)
{
   int startMinutes = session.startHour * 60 + session.startMinute;
   int endMinutes = session.endHour * 60 + session.endMinute;
   return (endMinutes <= startMinutes);
}

//+------------------------------------------------------------------+
//| Load London session preset (07:00-10:00 UTC)                    |
//+------------------------------------------------------------------+
void CSessionFilter::LoadLondonSession(bool enabled = true)
{
   AddSession("London", 7, 0, 10, 0, true, true, true, true, true, enabled);
}

//+------------------------------------------------------------------+
//| Load New York session preset (12:00-16:00 UTC)                  |
//+------------------------------------------------------------------+
void CSessionFilter::LoadNewYorkSession(bool enabled = true)
{
   AddSession("NewYork", 12, 0, 16, 0, true, true, true, true, true, enabled);
}

//+------------------------------------------------------------------+
//| Load Asia session preset (00:00-04:00 UTC)                      |
//+------------------------------------------------------------------+
void CSessionFilter::LoadAsiaSession(bool enabled = true)
{
   AddSession("Asia", 0, 0, 4, 0, true, true, true, true, true, enabled);
}

//+------------------------------------------------------------------+
//| Load all major sessions                                           |
//+------------------------------------------------------------------+
void CSessionFilter::LoadAllMajorSessions()
{
   LoadAsiaSession(false);       // Disabled by default
   LoadLondonSession(true);
   LoadNewYorkSession(true);
}

//+------------------------------------------------------------------+
//| Print status                                                      |
//+------------------------------------------------------------------+
void CSessionFilter::PrintStatus()
{
   Print("=== SESSION FILTER STATUS ===");
   Print("Server UTC offset: ", m_serverOffsetHrs, " hours");
   Print("Sessions configured: ", m_sessionCount);

   for(int i = 0; i < m_sessionCount; i++)
   {
      Print(StringFormat("  %d. %s: %02d:%02d-%02d:%02d %s",
                         i+1,
                         m_sessions[i].name,
                         m_sessions[i].startHour, m_sessions[i].startMinute,
                         m_sessions[i].endHour, m_sessions[i].endMinute,
                         m_sessions[i].enabled ? "[ENABLED]" : "[DISABLED]"));
   }

   string currentSession;
   if(IsInSession(currentSession))
      Print("Current status: IN SESSION (", currentSession, ")");
   else
      Print("Current status: OUTSIDE SESSION (", currentSession, ")");

   Print("=============================");
}

//+------------------------------------------------------------------+
//| Print current session info                                       |
//+------------------------------------------------------------------+
void CSessionFilter::PrintCurrentSession()
{
   string sessionName;
   if(GetCurrentSession(sessionName))
      Print("Current session: ", sessionName);
   else
      Print("Not currently in any session");
}

//+------------------------------------------------------------------+
//| Get current session name                                          |
//+------------------------------------------------------------------+
bool CSessionFilter::GetCurrentSession(string &sessionName)
{
   return IsInSession(sessionName);
}

//+------------------------------------------------------------------+
