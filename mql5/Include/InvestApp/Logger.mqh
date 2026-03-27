//+------------------------------------------------------------------+
//| Logger.mqh – Strukturiertes Logging für InvestApp EAs            |
//| Ausgabe ins Experten-Fenster + optional in Datei (Common Files)  |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_LOGGER_MQH
#define INVESTAPP_LOGGER_MQH

//--- Log-Level-Konstanten
#define LOG_DEBUG   0
#define LOG_INFO    1
#define LOG_WARNING 2
#define LOG_ERROR   3

//--- Globale Konfiguration
int    g_LogLevel    = LOG_INFO;   // Mindest-Level für Ausgabe
bool   g_LogToFile   = false;      // Datei-Logging aktivieren
int    g_LogFileHandle = INVALID_HANDLE;

//--- Interne Hilfsfunktion: Datei öffnen/rotieren
void _LogEnsureFile()
{
   if(!g_LogToFile) return;
   if(g_LogFileHandle != INVALID_HANDLE) return;

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   string filename = StringFormat("ea_log_%04d-%02d-%02d.txt",
                                  dt.year, dt.mon, dt.day);

   g_LogFileHandle = FileOpen(filename,
                              FILE_WRITE | FILE_READ | FILE_TXT | FILE_COMMON,
                              '\n');
   if(g_LogFileHandle == INVALID_HANDLE)
   {
      Print("[Logger] WARNUNG: Log-Datei konnte nicht geöffnet werden: ", filename,
            " Fehler: ", GetLastError());
      g_LogToFile = false;
   }
   else
   {
      // An das Ende der Datei springen (append)
      FileSeek(g_LogFileHandle, 0, SEEK_END);
   }
}

//--- Interne Hilfsfunktion: Level-String
string _LevelStr(int level)
{
   switch(level)
   {
      case LOG_DEBUG:   return "DEBUG";
      case LOG_INFO:    return "INFO";
      case LOG_WARNING: return "WARNING";
      case LOG_ERROR:   return "ERROR";
      default:          return "UNKNOWN";
   }
}

//+------------------------------------------------------------------+
//| Log-Datei schließen (in OnDeinit aufrufen)                       |
//+------------------------------------------------------------------+
void LogClose()
{
   if(g_LogFileHandle != INVALID_HANDLE)
   {
      FileClose(g_LogFileHandle);
      g_LogFileHandle = INVALID_HANDLE;
   }
}

//+------------------------------------------------------------------+
//| Haupt-Log-Funktion                                               |
//| Format: [YYYY-MM-DD HH:MM:SS] [LEVEL] [module] symbol | message |
//+------------------------------------------------------------------+
void Log(int level, string module, string symbol, string message)
{
   if(level < g_LogLevel) return;

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   string timestamp = StringFormat("%04d-%02d-%02d %02d:%02d:%02d",
                                   dt.year, dt.mon, dt.day,
                                   dt.hour, dt.min, dt.sec);

   string line = StringFormat("[%s] [%s] [%s] %s | %s",
                              timestamp,
                              _LevelStr(level),
                              module,
                              symbol,
                              message);

   Print(line);

   if(g_LogToFile)
   {
      _LogEnsureFile();
      if(g_LogFileHandle != INVALID_HANDLE)
         FileWriteString(g_LogFileHandle, line + "\n");
   }
}

//+------------------------------------------------------------------+
//| Fehler-Log mit MT5-Fehlercode                                    |
//+------------------------------------------------------------------+
void LogError(string module, string symbol, string message, int error_code)
{
   string full_msg = StringFormat("%s | ErrorCode: %d (%s)",
                                  message,
                                  error_code,
                                  (string)error_code);
   Log(LOG_ERROR, module, symbol, full_msg);
}

//+------------------------------------------------------------------+
//| Zyklus-Start loggen                                              |
//+------------------------------------------------------------------+
void LogCycleStart(string ea_name)
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   string timestamp = StringFormat("%04d-%02d-%02d %02d:%02d:%02d",
                                   dt.year, dt.mon, dt.day,
                                   dt.hour, dt.min, dt.sec);
   string line = StringFormat("[%s] [INFO] [%s] --- ZYKLUS START ---",
                              timestamp, ea_name);
   Print(line);

   if(g_LogToFile)
   {
      _LogEnsureFile();
      if(g_LogFileHandle != INVALID_HANDLE)
         FileWriteString(g_LogFileHandle, line + "\n");
   }
}

//+------------------------------------------------------------------+
//| Zyklus-Ende loggen                                               |
//+------------------------------------------------------------------+
void LogCycleEnd(string ea_name, int symbols_checked, int signals_found)
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   string timestamp = StringFormat("%04d-%02d-%02d %02d:%02d:%02d",
                                   dt.year, dt.mon, dt.day,
                                   dt.hour, dt.min, dt.sec);
   string line = StringFormat("[%s] [INFO] [%s] --- ZYKLUS ENDE | Symbole: %d | Signale: %d ---",
                              timestamp, ea_name, symbols_checked, signals_found);
   Print(line);

   if(g_LogToFile)
   {
      _LogEnsureFile();
      if(g_LogFileHandle != INVALID_HANDLE)
         FileWriteString(g_LogFileHandle, line + "\n");
   }
}

//--- Makros als Kurzformen
#define LOG_D(module, symbol, msg) Log(LOG_DEBUG,   module, symbol, msg)
#define LOG_I(module, symbol, msg) Log(LOG_INFO,    module, symbol, msg)
#define LOG_W(module, symbol, msg) Log(LOG_WARNING, module, symbol, msg)
#define LOG_E(module, symbol, msg) Log(LOG_ERROR,   module, symbol, msg)

#endif // INVESTAPP_LOGGER_MQH
