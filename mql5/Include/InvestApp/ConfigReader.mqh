//+------------------------------------------------------------------+
//| ConfigReader.mqh – config.json lesen und in Structs laden       |
//| Einfaches String-basiertes JSON-Parsing (kein nativer Parser)   |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_CONFIGREADER_MQH
#define INVESTAPP_CONFIGREADER_MQH

#include <InvestApp/Logger.mqh>

//+------------------------------------------------------------------+
//| Konfigurations-Structs                                           |
//+------------------------------------------------------------------+
struct RiskConfig
{
   double risk_per_trade_pct;    // Standard: 1.0
   int    max_open_trades;       // Standard: 3
   double max_daily_drawdown_pct;// Standard: 3.0
   double min_rr_ratio;          // Standard: 1.5
};

struct FiltersConfig
{
   double min_atr_multiplier;    // Standard: 0.8
   double max_atr_multiplier;    // Standard: 2.5
   double max_spread_pips;       // Standard: 2.0
   int    adx_min_threshold;     // Standard: 20
   int    rsi_overbought;        // Standard: 70
   int    rsi_oversold;          // Standard: 30
};

struct EntryConfig
{
   double sl_atr_multiplier;           // Standard: 1.5
   double tp_rr_ratio;                 // Standard: 2.0
   double signal_confidence_threshold; // Standard: 0.65
};

struct TradeManagementConfig
{
   double breakeven_trigger_atr;    // Phase 1→2: Profit >= x*ATR → Breakeven (Standard: 1.0)
   int    breakeven_buffer_pips;    // Puffer über Entry beim Breakeven-SL (Standard: 2)
   double structure_trigger_atr;   // Phase 2→3: Profit >= x*ATR → Struktur-Trailing (Standard: 2.0)
   double structure_sl_buffer_atr; // SL-Abstand zur Struktur in ATR (Standard: 0.25)
   double trailing_atr_multiplier; // Phase 3: SL = Struktur - x*ATR (Standard: 1.5)
   int    watch_poll_interval_seconds; // Polling-Intervall für TradeWatch (Standard: 60)
};

struct TradeExitConfig
{
   bool   use_fixed_tp;                  // Standard: false
   bool   close_before_rollover_enabled; // Standard: true
   int    close_before_rollover_minutes; // Standard: 30
   bool   close_only_if_profitable;      // Standard: false
   string rollover_time_utc;             // Standard: "22:00"
};

struct SessionConfig
{
   bool trade_london;    // Standard: true
   bool trade_new_york;  // Standard: true
   bool trade_asian;     // Standard: false
};

struct SmartTpConfig
{
   bool   enabled;
   int    activate_minutes_before_rollover; // Standard: 60
   int    range_candles_lookback;           // Standard: 12
   int    range_buffer_pips;                // Standard: 2
};

struct AppConfig
{
   RiskConfig            risk;
   FiltersConfig         filters;
   EntryConfig           entry;
   TradeManagementConfig trade_management;
   TradeExitConfig       trade_exit;
   SessionConfig         session;
   SmartTpConfig         smart_tp;
   string                last_updated;
   string                version;
};

//+------------------------------------------------------------------+
//| Interne Hilfsfunktionen: JSON-String-Parsing                     |
//+------------------------------------------------------------------+

// Extrahiert einen JSON-Abschnitt für einen Objekt-Key.
// Sucht nach "key": { ... } und gibt den Inhalt zwischen { } zurück.
string _JsonGetSection(string json, string key)
{
   string search = "\"" + key + "\"";
   int key_pos = StringFind(json, search);
   if(key_pos < 0) return "";

   // Nach dem Key das erste '{' finden
   int brace_start = StringFind(json, "{", key_pos + StringLen(search));
   if(brace_start < 0) return "";

   // Verschachtelungstiefe zählen um das schließende '}' zu finden
   int depth = 0;
   int len   = StringLen(json);
   for(int i = brace_start; i < len; i++)
   {
      ushort ch = StringGetCharacter(json, i);
      if(ch == '{') depth++;
      else if(ch == '}')
      {
         depth--;
         if(depth == 0)
            return StringSubstr(json, brace_start, i - brace_start + 1);
      }
   }
   return "";
}

// Extrahiert den Rohwert zu einem Key aus einem flachen JSON-Objekt.
// Gibt den String zwischen ':' und dem nächsten ',' oder '}' zurück.
string _JsonGetRawValue(string json, string key)
{
   string search = "\"" + key + "\"";
   int key_pos = StringFind(json, search);
   if(key_pos < 0) return "";

   // ':' nach dem Key finden
   int colon_pos = StringFind(json, ":", key_pos + StringLen(search));
   if(colon_pos < 0) return "";

   // Wert-Anfang: erstes Nicht-Leerzeichen nach ':'
   int val_start = colon_pos + 1;
   int len       = StringLen(json);
   while(val_start < len)
   {
      ushort ch = StringGetCharacter(json, val_start);
      if(ch != ' ' && ch != '\t' && ch != '\n' && ch != '\r') break;
      val_start++;
   }
   if(val_start >= len) return "";

   // Wert-Ende: bis ',' oder '}' (außer bei String-Werten in Anführungszeichen)
   ushort first_ch = StringGetCharacter(json, val_start);
   int val_end;

   if(first_ch == '"')
   {
      // String-Wert: bis schließendem '"' lesen
      val_end = val_start + 1;
      while(val_end < len)
      {
         ushort ch = StringGetCharacter(json, val_end);
         if(ch == '"') { val_end++; break; }
         // Escaped character überspringen
         if(ch == '\\') val_end++;
         val_end++;
      }
   }
   else
   {
      val_end = val_start + 1;
      while(val_end < len)
      {
         ushort ch = StringGetCharacter(json, val_end);
         if(ch == ',' || ch == '}' || ch == '\n') break;
         val_end++;
      }
   }

   string raw = StringSubstr(json, val_start, val_end - val_start);
   StringTrimLeft(raw);
   StringTrimRight(raw);
   return raw;
}

double _JsonGetDouble(string json, string key, double default_val)
{
   string raw = _JsonGetRawValue(json, key);
   if(raw == "") return default_val;
   double val = StringToDouble(raw);
   // StringToDouble gibt 0 zurück wenn Parsing fehlschlägt – Fallback auf Default
   if(val == 0.0 && raw != "0" && raw != "0.0") return default_val;
   return val;
}

int _JsonGetInt(string json, string key, int default_val)
{
   string raw = _JsonGetRawValue(json, key);
   if(raw == "") return default_val;
   return (int)StringToInteger(raw);
}

bool _JsonGetBool(string json, string key, bool default_val)
{
   string raw = _JsonGetRawValue(json, key);
   if(raw == "") return default_val;
   StringToLower(raw);
   if(raw == "true")  return true;
   if(raw == "false") return false;
   return default_val;
}

string _JsonGetString(string json, string key, string default_val)
{
   string raw = _JsonGetRawValue(json, key);
   if(raw == "") return default_val;
   // Anführungszeichen entfernen
   if(StringGetCharacter(raw, 0) == '"')
      raw = StringSubstr(raw, 1, StringLen(raw) - 2);
   return raw;
}

//+------------------------------------------------------------------+
//| Standardwerte in AppConfig schreiben                             |
//+------------------------------------------------------------------+
void _SetConfigDefaults(AppConfig &cfg)
{
   cfg.risk.risk_per_trade_pct     = 1.0;
   cfg.risk.max_open_trades        = 3;
   cfg.risk.max_daily_drawdown_pct = 3.0;
   cfg.risk.min_rr_ratio           = 1.5;

   cfg.filters.min_atr_multiplier  = 0.8;
   cfg.filters.max_atr_multiplier  = 2.5;
   cfg.filters.max_spread_pips     = 2.0;
   cfg.filters.adx_min_threshold   = 20;
   cfg.filters.rsi_overbought      = 70;
   cfg.filters.rsi_oversold        = 30;

   cfg.entry.sl_atr_multiplier            = 1.5;
   cfg.entry.tp_rr_ratio                  = 2.0;
   cfg.entry.signal_confidence_threshold  = 0.65;

   cfg.trade_management.breakeven_trigger_atr        = 1.0;
   cfg.trade_management.breakeven_buffer_pips        = 2;
   cfg.trade_management.structure_trigger_atr        = 2.0;
   cfg.trade_management.structure_sl_buffer_atr      = 0.25;
   cfg.trade_management.trailing_atr_multiplier      = 1.5;
   cfg.trade_management.watch_poll_interval_seconds  = 60;

   cfg.trade_exit.use_fixed_tp                  = false;
   cfg.trade_exit.close_before_rollover_enabled = true;
   cfg.trade_exit.close_before_rollover_minutes = 30;
   cfg.trade_exit.close_only_if_profitable      = false;
   cfg.trade_exit.rollover_time_utc             = "22:00";

   cfg.session.trade_london    = true;
   cfg.session.trade_new_york  = true;
   cfg.session.trade_asian     = false;

   cfg.smart_tp.enabled                          = true;
   cfg.smart_tp.activate_minutes_before_rollover = 60;
   cfg.smart_tp.range_candles_lookback           = 12;
   cfg.smart_tp.range_buffer_pips                = 2;

   cfg.last_updated = "";
   cfg.version      = "0.0";
}

//+------------------------------------------------------------------+
//| Konfiguration aus JSON-String in AppConfig parsen               |
//+------------------------------------------------------------------+
void _ParseConfig(string json, AppConfig &cfg)
{
   // Top-Level-Felder
   cfg.version      = _JsonGetString(json, "version",      cfg.version);
   cfg.last_updated = _JsonGetString(json, "last_updated",  cfg.last_updated);

   // Abschnitt "risk"
   string sec = _JsonGetSection(json, "risk");
   if(sec != "")
   {
      cfg.risk.risk_per_trade_pct     = _JsonGetDouble(sec, "risk_per_trade_pct",     cfg.risk.risk_per_trade_pct);
      cfg.risk.max_open_trades        = _JsonGetInt   (sec, "max_open_trades",        cfg.risk.max_open_trades);
      cfg.risk.max_daily_drawdown_pct = _JsonGetDouble(sec, "max_daily_drawdown_pct", cfg.risk.max_daily_drawdown_pct);
      cfg.risk.min_rr_ratio           = _JsonGetDouble(sec, "min_rr_ratio",           cfg.risk.min_rr_ratio);
   }

   // Abschnitt "filters"
   sec = _JsonGetSection(json, "filters");
   if(sec != "")
   {
      cfg.filters.min_atr_multiplier  = _JsonGetDouble(sec, "min_atr_multiplier",  cfg.filters.min_atr_multiplier);
      cfg.filters.max_atr_multiplier  = _JsonGetDouble(sec, "max_atr_multiplier",  cfg.filters.max_atr_multiplier);
      cfg.filters.max_spread_pips     = _JsonGetDouble(sec, "max_spread_pips",     cfg.filters.max_spread_pips);
      cfg.filters.adx_min_threshold   = _JsonGetInt   (sec, "adx_min_threshold",   cfg.filters.adx_min_threshold);
      cfg.filters.rsi_overbought      = _JsonGetInt   (sec, "rsi_overbought",      cfg.filters.rsi_overbought);
      cfg.filters.rsi_oversold        = _JsonGetInt   (sec, "rsi_oversold",        cfg.filters.rsi_oversold);
   }

   // Abschnitt "entry"
   sec = _JsonGetSection(json, "entry");
   if(sec != "")
   {
      cfg.entry.sl_atr_multiplier           = _JsonGetDouble(sec, "sl_atr_multiplier",           cfg.entry.sl_atr_multiplier);
      cfg.entry.tp_rr_ratio                 = _JsonGetDouble(sec, "tp_rr_ratio",                 cfg.entry.tp_rr_ratio);
      cfg.entry.signal_confidence_threshold = _JsonGetDouble(sec, "signal_confidence_threshold", cfg.entry.signal_confidence_threshold);
   }

   // Abschnitt "trade_management"
   sec = _JsonGetSection(json, "trade_management");
   if(sec != "")
   {
      cfg.trade_management.breakeven_trigger_atr       = _JsonGetDouble(sec, "breakeven_trigger_atr",       cfg.trade_management.breakeven_trigger_atr);
      cfg.trade_management.breakeven_buffer_pips       = _JsonGetInt   (sec, "breakeven_buffer_pips",       cfg.trade_management.breakeven_buffer_pips);
      cfg.trade_management.structure_trigger_atr       = _JsonGetDouble(sec, "structure_trigger_atr",       cfg.trade_management.structure_trigger_atr);
      cfg.trade_management.structure_sl_buffer_atr     = _JsonGetDouble(sec, "structure_sl_buffer_atr",     cfg.trade_management.structure_sl_buffer_atr);
      cfg.trade_management.trailing_atr_multiplier     = _JsonGetDouble(sec, "trailing_atr_multiplier",     cfg.trade_management.trailing_atr_multiplier);
      cfg.trade_management.watch_poll_interval_seconds = _JsonGetInt   (sec, "watch_poll_interval_seconds", cfg.trade_management.watch_poll_interval_seconds);
   }

   // Abschnitt "trade_exit"
   sec = _JsonGetSection(json, "trade_exit");
   if(sec != "")
   {
      cfg.trade_exit.use_fixed_tp                  = _JsonGetBool  (sec, "use_fixed_tp",                  cfg.trade_exit.use_fixed_tp);
      cfg.trade_exit.close_before_rollover_enabled = _JsonGetBool  (sec, "close_before_rollover_enabled", cfg.trade_exit.close_before_rollover_enabled);
      cfg.trade_exit.close_before_rollover_minutes = _JsonGetInt   (sec, "close_before_rollover_minutes", cfg.trade_exit.close_before_rollover_minutes);
      cfg.trade_exit.close_only_if_profitable      = _JsonGetBool  (sec, "close_only_if_profitable",      cfg.trade_exit.close_only_if_profitable);
      cfg.trade_exit.rollover_time_utc             = _JsonGetString(sec, "rollover_time_utc",             cfg.trade_exit.rollover_time_utc);
   }

   // Abschnitt "session"
   sec = _JsonGetSection(json, "session");
   if(sec != "")
   {
      cfg.session.trade_london    = _JsonGetBool(sec, "trade_london",   cfg.session.trade_london);
      cfg.session.trade_new_york  = _JsonGetBool(sec, "trade_new_york", cfg.session.trade_new_york);
      cfg.session.trade_asian     = _JsonGetBool(sec, "trade_asian",    cfg.session.trade_asian);
   }

   // Abschnitt "smart_tp"
   sec = _JsonGetSection(json, "smart_tp");
   if(sec != "")
   {
      cfg.smart_tp.enabled                          = _JsonGetBool(sec, "enabled",                          cfg.smart_tp.enabled);
      cfg.smart_tp.activate_minutes_before_rollover = _JsonGetInt (sec, "activate_minutes_before_rollover", cfg.smart_tp.activate_minutes_before_rollover);
      cfg.smart_tp.range_candles_lookback           = _JsonGetInt (sec, "range_candles_lookback",           cfg.smart_tp.range_candles_lookback);
      cfg.smart_tp.range_buffer_pips                = _JsonGetInt (sec, "range_buffer_pips",                cfg.smart_tp.range_buffer_pips);
   }
}

//+------------------------------------------------------------------+
//| Konfiguration laden                                              |
//| path: Pfad zur config.json (leer = "config.json" in Common Files)|
//| Gibt true zurück wenn Datei erfolgreich gelesen und geparst      |
//+------------------------------------------------------------------+
bool LoadConfig(AppConfig &cfg, string path = "")
{
   // Standardwerte vorbelegen
   _SetConfigDefaults(cfg);

   string filename = (path == "") ? "config.json" : path;

   int file_handle = FileOpen(filename,
                              FILE_READ | FILE_TXT | FILE_COMMON,
                              '\n');
   if(file_handle == INVALID_HANDLE)
   {
      LOG_W("ConfigReader", "-", "config.json nicht gefunden: " + filename +
            " | Fehler: " + (string)GetLastError() + " | Nutze Standardwerte");
      return false;
   }

   // Gesamten Datei-Inhalt lesen
   string json = "";
   while(!FileIsEnding(file_handle))
      json += FileReadString(file_handle) + "\n";

   FileClose(file_handle);

   if(StringLen(json) < 2)
   {
      LOG_W("ConfigReader", "-", "config.json ist leer: " + filename + " | Nutze Standardwerte");
      return false;
   }

   _ParseConfig(json, cfg);

   LOG_I("ConfigReader", "-",
         StringFormat("Config geladen | Version: %s | Stand: %s | Datei: %s",
                      cfg.version, cfg.last_updated, filename));
   return true;
}

//+------------------------------------------------------------------+
//| Prüfen ob config.json älter als max_age_seconds Sekunden ist    |
//| Gibt true zurück wenn die Datei veraltet (oder nicht lesbar) ist |
//+------------------------------------------------------------------+
bool IsConfigStale(string path = "", int max_age_seconds = 900)
{
   string filename = (path == "") ? "config.json" : path;

   long modify_time = FileGetInteger(filename,
                                     FILE_MODIFY_DATE,
                                     true); // true = Common Files
   if(modify_time <= 0)
   {
      LOG_W("ConfigReader", "-", "IsConfigStale: Datei nicht gefunden oder nicht lesbar: " + filename);
      return true;
   }

   long age = (long)TimeCurrent() - modify_time;
   if(age > max_age_seconds)
   {
      LOG_W("ConfigReader", "-",
            StringFormat("IsConfigStale: config.json ist %d Sekunden alt (Limit: %d)",
                         (int)age, max_age_seconds));
      return true;
   }

   return false;
}

#endif // INVESTAPP_CONFIGREADER_MQH
