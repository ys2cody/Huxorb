//+------------------------------------------------------------------+
//|                                                        Utils.mqh |
//|                         HuxORB PRO - Utility Functions           |
//+------------------------------------------------------------------+
#property copyright "HuxORB Team"
#property link      "https://github.com/ys2cody/Huxorb"
#property strict

//+------------------------------------------------------------------+
//| String trimming                                                   |
//+------------------------------------------------------------------+
string StringTrim(string str)
{
   StringTrimLeft(str);
   StringTrimRight(str);
   return str;
}

//+------------------------------------------------------------------+
//| Convert datetime to string in ISO format                        |
//+------------------------------------------------------------------+
string DateTimeToISO(datetime dt)
{
   MqlDateTime mdt;
   TimeToStruct(dt, mdt);
   return StringFormat("%04d-%02d-%02d %02d:%02d:%02d",
                       mdt.year, mdt.mon, mdt.day,
                       mdt.hour, mdt.min, mdt.sec);
}

//+------------------------------------------------------------------+
//| Parse ISO datetime string (YYYY-MM-DD HH:MM:SS)                 |
//+------------------------------------------------------------------+
datetime ParseISODateTime(string isoStr)
{
   MqlDateTime dt;
   StringReplace(isoStr, "-", " ");
   StringReplace(isoStr, ":", " ");

   string parts[];
   int count = StringSplit(isoStr, ' ', parts);

   if(count >= 6)
   {
      dt.year = (int)StringToInteger(parts[0]);
      dt.mon = (int)StringToInteger(parts[1]);
      dt.day = (int)StringToInteger(parts[2]);
      dt.hour = (int)StringToInteger(parts[3]);
      dt.min = (int)StringToInteger(parts[4]);
      dt.sec = (int)StringToInteger(parts[5]);

      return StructToTime(dt);
   }

   return 0;
}

//+------------------------------------------------------------------+
//| Generate stable seed from account info                          |
//+------------------------------------------------------------------+
int GenerateAccountSeed(string profileName, int instanceID)
{
   long accountNum = AccountNumber();
   int hash = (int)(accountNum % 2147483647);

   // Mix in profile name
   for(int i = 0; i < StringLen(profileName); i++)
   {
      hash = hash * 31 + StringGetChar(profileName, i);
   }

   // Mix in instance ID
   hash = hash * 31 + instanceID;

   // Ensure positive
   return MathAbs(hash);
}

//+------------------------------------------------------------------+
//| Check if symbol contains currency                               |
//+------------------------------------------------------------------+
bool SymbolContainsCurrency(string symbol, string currency)
{
   // Normalize
   StringToUpper(symbol);
   StringToUpper(currency);

   // Check if currency is in first 3 or last 3 chars
   if(StringLen(symbol) >= 6)
   {
      string base = StringSubstr(symbol, 0, 3);
      string quote = StringSubstr(symbol, 3, 3);

      return (base == currency || quote == currency);
   }

   // Fallback: simple contains check
   return (StringFind(symbol, currency) >= 0);
}

//+------------------------------------------------------------------+
//| Format reason code for logging                                   |
//+------------------------------------------------------------------+
string FormatBlockReason(string reasonCode, string details = "")
{
   string msg = "[BLOCKED:" + reasonCode + "]";
   if(StringLen(details) > 0)
      msg += " " + details;
   return msg;
}

//+------------------------------------------------------------------+
//| Safe file read with error handling                              |
//+------------------------------------------------------------------+
bool SafeFileRead(string filename, string &lines[])
{
   ArrayResize(lines, 0);

   int handle = FileOpen(filename, FILE_READ|FILE_TXT|FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      Print("SafeFileRead: Failed to open ", filename, " Error: ", GetLastError());
      return false;
   }

   int count = 0;
   while(!FileIsEnding(handle))
   {
      string line = FileReadString(handle);
      if(StringLen(line) > 0)
      {
         ArrayResize(lines, count + 1);
         lines[count] = line;
         count++;
      }
   }

   FileClose(handle);
   return (count > 0);
}

//+------------------------------------------------------------------+
//| Get current UTC time from server time                           |
//+------------------------------------------------------------------+
datetime GetUTCTime(int serverOffsetHours)
{
   return TimeCurrent() - (serverOffsetHours * 3600);
}

//+------------------------------------------------------------------+
//| Check if datetime is within range                               |
//+------------------------------------------------------------------+
bool IsTimeInRange(datetime checkTime, datetime startTime, datetime endTime)
{
   return (checkTime >= startTime && checkTime <= endTime);
}

//+------------------------------------------------------------------+
//| Log with timestamp                                               |
//+------------------------------------------------------------------+
void LogMessage(string category, string message, bool enableLogging = true)
{
   if(enableLogging)
   {
      string timestamp = TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS);
      Print("[", timestamp, "][", category, "] ", message);
   }
}

//+------------------------------------------------------------------+
