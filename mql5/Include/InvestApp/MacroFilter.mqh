//+------------------------------------------------------------------+
//| MacroFilter.mqh – Makro-Kontext + News-Sperre                   |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_MACROFILTER_MQH
#define INVESTAPP_MACROFILTER_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>

//+------------------------------------------------------------------+
//| Structs                                                           |
//+------------------------------------------------------------------+
struct MacroContext
{
   string   regime;         // "risk_on", "risk_off", "neutral"
   string   overall_bias;   // "bullish", "bearish", "neutral"
   bool     trade_enabled;  // globaler Schalter
   string   generated_at;
};

struct NewsEvent
{
   datetime event_time;
   string   currency;
   string   impact;         // "high", "medium", "low"
   string   title;
   int      block_before;   // Minuten vor Event
   int      block_after;    // Minuten nach Event
};

struct MacroResult
{
   bool   isAllowed;
   string reject_reason;
   string regime;
   string bias;
};

//+------------------------------------------------------------------+
//| Währungen aus Symbol extrahieren                                 |
//| Gibt erste Währung zurück, schreibt zweite in currency2          |
//| Bei Indexes (z.B. DE40): Leerstring                              |
//+------------------------------------------------------------------+
string GetSymbolCurrencies(string symbol, string &currency2)
{
   currency2 = "";

   // Forex: genau 6 Zeichen, beide Teile je 3 Buchstaben
   if(StringLen(symbol) == 6)
   {
      string c1 = StringSubstr(symbol, 0, 3);
      string c2 = StringSubstr(symbol, 3, 3);

      // Einfacher Plausibilitäts-Check: nur Buchstaben
      bool valid = true;
      for(int i = 0; i < 3; i++)
      {
         ushort ch1 = StringGetCharacter(c1, i);
         ushort ch2 = StringGetCharacter(c2, i);
         if(!((ch1 >= 'A' && ch1 <= 'Z') || (ch1 >= 'a' && ch1 <= 'z'))) { valid = false; break; }
         if(!((ch2 >= 'A' && ch2 <= 'Z') || (ch2 >= 'a' && ch2 <= 'z'))) { valid = false; break; }
      }

      if(valid)
      {
         currency2 = c2;
         return c1;
      }
   }

   // Index oder unbekanntes Format → kein Währungsfilter
   return "";
}

//+------------------------------------------------------------------+
//| Makro-Kontext aus macro_context.json laden                       |
//+------------------------------------------------------------------+
bool LoadMacroContext(MacroContext &ctx, string path = "")
{
   // Defaults
   ctx.regime       = "neutral";
   ctx.overall_bias = "neutral";
   ctx.trade_enabled = true;
   ctx.generated_at = "";

   string filename = (path == "") ? "macro_context.json" : path;

   int fh = FileOpen(filename, FILE_READ | FILE_TXT | FILE_COMMON, '\n');
   if(fh == INVALID_HANDLE)
   {
      LOG_W("MacroFilter", "-", "macro_context.json nicht gefunden: " + filename +
            " | Fehler: " + (string)GetLastError() + " | Nutze Defaults");
      return false;
   }

   string json = "";
   while(!FileIsEnding(fh))
      json += FileReadString(fh) + "\n";
   FileClose(fh);

   if(StringLen(json) < 2) return false;

   ctx.regime        = _JsonGetString(json, "regime",        ctx.regime);
   ctx.overall_bias  = _JsonGetString(json, "overall_bias",  ctx.overall_bias);
   ctx.trade_enabled = _JsonGetBool  (json, "trade_enabled", ctx.trade_enabled);
   ctx.generated_at  = _JsonGetString(json, "generated_at",  ctx.generated_at);

   return true;
}

//+------------------------------------------------------------------+
//| News-Events aus news_events.json laden                           |
//| Gibt Anzahl geladener Events zurück                              |
//+------------------------------------------------------------------+
int LoadNewsEvents(NewsEvent &events[], string path = "")
{
   ArrayResize(events, 0);

   string filename = (path == "") ? "news_events.json" : path;

   int fh = FileOpen(filename, FILE_READ | FILE_TXT | FILE_COMMON, '\n');
   if(fh == INVALID_HANDLE)
   {
      LOG_W("MacroFilter", "-", "news_events.json nicht gefunden: " + filename +
            " | Fehler: " + (string)GetLastError());
      return 0;
   }

   string json = "";
   while(!FileIsEnding(fh))
      json += FileReadString(fh) + "\n";
   FileClose(fh);

   if(StringLen(json) < 2) return 0;

   // Array-Abschnitt "events": [ {...}, {...} ] extrahieren
   string events_key = "\"events\"";
   int key_pos = StringFind(json, events_key);
   if(key_pos < 0) return 0;

   int arr_start = StringFind(json, "[", key_pos + StringLen(events_key));
   if(arr_start < 0) return 0;

   // Ende des Arrays finden
   int depth = 0;
   int arr_end = -1;
   int len = StringLen(json);
   for(int i = arr_start; i < len; i++)
   {
      ushort ch = StringGetCharacter(json, i);
      if(ch == '[') depth++;
      else if(ch == ']') { depth--; if(depth == 0) { arr_end = i; break; } }
   }
   if(arr_end < 0) return 0;

   string arr_content = StringSubstr(json, arr_start + 1, arr_end - arr_start - 1);

   // Einzelne Objekte { ... } parsen
   int count = 0;
   int pos = 0;
   int arr_len = StringLen(arr_content);
   while(pos < arr_len)
   {
      int obj_start = StringFind(arr_content, "{", pos);
      if(obj_start < 0) break;

      // Verschachtelungstiefe → schließendes }
      int obj_depth = 0;
      int obj_end = -1;
      for(int i = obj_start; i < arr_len; i++)
      {
         ushort ch = StringGetCharacter(arr_content, i);
         if(ch == '{') obj_depth++;
         else if(ch == '}') { obj_depth--; if(obj_depth == 0) { obj_end = i; break; } }
      }
      if(obj_end < 0) break;

      string obj = StringSubstr(arr_content, obj_start, obj_end - obj_start + 1);

      ArrayResize(events, count + 1);
      string time_str = _JsonGetString(obj, "event_time", "");
      events[count].event_time  = (time_str != "") ? StringToTime(time_str) : 0;
      events[count].currency    = _JsonGetString(obj, "currency",     "");
      events[count].impact      = _JsonGetString(obj, "impact",       "low");
      events[count].title       = _JsonGetString(obj, "title",        "");
      events[count].block_before = _JsonGetInt  (obj, "block_before", 30);
      events[count].block_after  = _JsonGetInt  (obj, "block_after",  30);

      count++;
      pos = obj_end + 1;
   }

   return count;
}

//+------------------------------------------------------------------+
//| Prüfen ob Symbol durch ein News-Event geblockt ist              |
//+------------------------------------------------------------------+
bool IsNewsBlocked(string symbol, NewsEvent &events[], int event_count)
{
   if(event_count <= 0) return false;

   string currency2 = "";
   string currency1 = GetSymbolCurrencies(symbol, currency2);

   // Index → kein Währungsfilter, kein Block
   if(currency1 == "") return false;

   datetime now = TimeCurrent();

   for(int i = 0; i < event_count; i++)
   {
      string ev_cur = events[i].currency;
      StringToUpper(ev_cur);
      string c1_upper = currency1; StringToUpper(c1_upper);
      string c2_upper = currency2; StringToUpper(c2_upper);

      bool currency_match = (ev_cur == c1_upper || ev_cur == c2_upper);
      if(!currency_match) continue;

      datetime block_start = events[i].event_time - (datetime)(events[i].block_before * 60);
      datetime block_end   = events[i].event_time + (datetime)(events[i].block_after  * 60);

      if(now >= block_start && now <= block_end)
      {
         LOG_W("MacroFilter", symbol,
               "News-Sperre: " + events[i].title +
               " | Währung: " + events[i].currency +
               " | Impact: " + events[i].impact);
         return true;
      }
   }

   return false;
}

//+------------------------------------------------------------------+
//| Hauptfunktion: Makro-Kontext und News-Sperre prüfen              |
//+------------------------------------------------------------------+
MacroResult CheckMacro(string symbol, AppConfig &cfg)
{
   MacroResult result;
   result.isAllowed     = false;
   result.reject_reason = "";
   result.regime        = "neutral";
   result.bias          = "neutral";

   // [1] Makro-Kontext laden
   MacroContext ctx;
   bool ctx_loaded = LoadMacroContext(ctx);

   if(ctx_loaded)
   {
      result.regime = ctx.regime;
      result.bias   = ctx.overall_bias;

      // Globaler Trade-Schalter
      if(!ctx.trade_enabled)
      {
         result.isAllowed     = false;
         result.reject_reason = "Globaler Trade-Schalter deaktiviert";
         LOG_W("MacroFilter", symbol, "BLOCK | " + result.reject_reason);
         return result;
      }
   }
   else
   {
      // Datei fehlt → fail-open mit Defaults
      LOG_W("MacroFilter", symbol, "macro_context.json nicht verfügbar | Fail-open mit Defaults");
   }

   // [2] News-Events laden und prüfen
   NewsEvent events[];
   int event_count = LoadNewsEvents(events);

   if(event_count > 0)
   {
      if(IsNewsBlocked(symbol, events, event_count))
      {
         result.isAllowed     = false;
         result.reject_reason = "News-Sperre aktiv";
         LOG_W("MacroFilter", symbol, "BLOCK | " + result.reject_reason);
         return result;
      }
   }
   else if(event_count == 0)
   {
      LOG_W("MacroFilter", symbol, "news_events.json nicht verfügbar oder leer | Kein News-Filter");
   }

   // [3] Risk-Off Warnung (kein harter Block)
   if(ctx_loaded && ctx.regime == "risk_off")
   {
      string currency2 = "";
      string currency1 = GetSymbolCurrencies(symbol, currency2);
      // Forex-Symbole als potenzielle Risk-Assets behandeln
      if(currency1 != "")
         LOG_W("MacroFilter", symbol, "Warnung: regime=risk_off | Erhöhte Vorsicht bei Risk-Assets");
   }

   // [4] Erlaubt
   result.isAllowed = true;
   LOG_I("MacroFilter", symbol,
         "✓ | Regime=" + result.regime + " | Bias=" + result.bias);

   return result;
}

#endif // INVESTAPP_MACROFILTER_MQH
