//+------------------------------------------------------------------+
//| LevelDetection.mqh – S/R Zonen aus zones.json (Hybrid)          |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_LEVELDETECTION_MQH
#define INVESTAPP_LEVELDETECTION_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>

//+------------------------------------------------------------------+
//| Struct                                                            |
//+------------------------------------------------------------------+
struct SymbolZones
{
   double   resistance[];          // alle Resistance-Level
   double   support[];             // alle Support-Level
   int      resistance_count;
   int      support_count;
   double   nearest_resistance;    // nächstes Resistance über aktuellem Preis
   double   nearest_support;       // nächstes Support unter aktuellem Preis
   double   dist_resistance_pips;  // Abstand in Pips
   double   dist_support_pips;
   bool     isValid;               // false wenn zones.json fehlt/veraltet
   datetime generated_at;
};

//+------------------------------------------------------------------+
//| Pip-Größe (lokal, um zirkuläre Abhängigkeit zu RiskManager zu   |
//| vermeiden falls LevelDetection standalone genutzt wird)          |
//+------------------------------------------------------------------+
double _LDGetPipSize(string symbol)
{
   double point  = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int    digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(digits >= 3)
      return point * 10.0;
   return point;
}

//+------------------------------------------------------------------+
//| Hilfsfunktion: kommagetrennte Zahlen-Array aus String parsen     |
//+------------------------------------------------------------------+
int _ParseDoubleArray(string arr_str, double &out[], int max_values = 100)
{
   ArrayResize(out, 0);
   int count = 0;
   int len   = StringLen(arr_str);
   int start = 0;

   for(int i = 0; i <= len; i++)
   {
      ushort ch = (i < len) ? StringGetCharacter(arr_str, i) : ',';
      if(ch == ',' || ch == ']' || i == len)
      {
         if(i > start)
         {
            string token = StringTrimLeft(StringTrimRight(StringSubstr(arr_str, start, i - start)));
            if(StringLen(token) > 0)
            {
               double val = StringToDouble(token);
               if(val != 0.0 || token == "0" || token == "0.0")
               {
                  ArrayResize(out, count + 1);
                  out[count++] = val;
                  if(count >= max_values) break;
               }
            }
         }
         start = i + 1;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Zonen für ein Symbol aus zones.json laden                        |
//+------------------------------------------------------------------+
bool LoadZones(string symbol, SymbolZones &zones, string path = "")
{
   // Defaults
   ArrayResize(zones.resistance, 0);
   ArrayResize(zones.support, 0);
   zones.resistance_count   = 0;
   zones.support_count      = 0;
   zones.nearest_resistance = 0.0;
   zones.nearest_support    = 0.0;
   zones.dist_resistance_pips = 0.0;
   zones.dist_support_pips    = 0.0;
   zones.isValid            = false;
   zones.generated_at       = 0;

   string filename = (path == "") ? "zones.json" : path;

   int fh = FileOpen(filename, FILE_READ | FILE_TXT | FILE_COMMON, '\n');
   if(fh == INVALID_HANDLE)
   {
      LOG_W("LevelDetection", symbol, "zones.json nicht gefunden: " + filename +
            " | Fehler: " + (string)GetLastError());
      return false;
   }

   string json = "";
   while(!FileIsEnding(fh))
      json += FileReadString(fh) + "\n";
   FileClose(fh);

   if(StringLen(json) < 2) return false;

   // valid_until prüfen (Veralterung > 20 Min)
   string valid_until_str = _JsonGetString(json, "valid_until", "");
   if(valid_until_str != "")
   {
      datetime valid_until = StringToTime(valid_until_str);
      if(valid_until > 0 && TimeCurrent() > valid_until + 20 * 60)
      {
         LOG_W("LevelDetection", symbol,
               "zones.json veraltet | valid_until: " + valid_until_str +
               " | Lade trotzdem (fail-graceful)");
         zones.isValid = false;
      }
      else
      {
         zones.isValid = true;
      }
   }
   else
   {
      zones.isValid = true;
   }

   // generated_at parsen
   string gen_at = _JsonGetString(json, "generated_at", "");
   if(gen_at != "")
      zones.generated_at = StringToTime(gen_at);

   // Symbol-Abschnitt extrahieren
   string sym_section = _JsonGetSection(json, symbol);
   if(sym_section == "")
   {
      LOG_W("LevelDetection", symbol, "Kein Symbol-Abschnitt in zones.json gefunden");
      return false;
   }

   // Resistance-Array
   string res_key = "\"resistance\"";
   int res_pos = StringFind(sym_section, res_key);
   if(res_pos >= 0)
   {
      int arr_start = StringFind(sym_section, "[", res_pos + StringLen(res_key));
      if(arr_start >= 0)
      {
         int arr_end = StringFind(sym_section, "]", arr_start);
         if(arr_end > arr_start)
         {
            string arr_str = StringSubstr(sym_section, arr_start + 1, arr_end - arr_start - 1);
            zones.resistance_count = _ParseDoubleArray(arr_str, zones.resistance);
         }
      }
   }

   // Support-Array
   string sup_key = "\"support\"";
   int sup_pos = StringFind(sym_section, sup_key);
   if(sup_pos >= 0)
   {
      int arr_start = StringFind(sym_section, "[", sup_pos + StringLen(sup_key));
      if(arr_start >= 0)
      {
         int arr_end = StringFind(sym_section, "]", arr_start);
         if(arr_end > arr_start)
         {
            string arr_str = StringSubstr(sym_section, arr_start + 1, arr_end - arr_start - 1);
            zones.support_count = _ParseDoubleArray(arr_str, zones.support);
         }
      }
   }

   // Nächstgelegene Level basierend auf aktuellem Bid-Preis berechnen
   double price   = SymbolInfoDouble(symbol, SYMBOL_BID);
   double pip     = _LDGetPipSize(symbol);

   // Nächstes Resistance über aktuellem Preis
   double nearest_res = 0.0;
   for(int i = 0; i < zones.resistance_count; i++)
   {
      if(zones.resistance[i] > price)
      {
         if(nearest_res == 0.0 || zones.resistance[i] < nearest_res)
            nearest_res = zones.resistance[i];
      }
   }
   zones.nearest_resistance = nearest_res;
   zones.dist_resistance_pips = (nearest_res > 0.0 && pip > 0.0)
                                ? (nearest_res - price) / pip
                                : 0.0;

   // Nächstes Support unter aktuellem Preis
   double nearest_sup = 0.0;
   for(int i = 0; i < zones.support_count; i++)
   {
      if(zones.support[i] < price)
      {
         if(nearest_sup == 0.0 || zones.support[i] > nearest_sup)
            nearest_sup = zones.support[i];
      }
   }
   zones.nearest_support = nearest_sup;
   zones.dist_support_pips = (nearest_sup > 0.0 && pip > 0.0)
                             ? (price - nearest_sup) / pip
                             : 0.0;

   LOG_D("LevelDetection", symbol,
         StringFormat("Zonen geladen | Res=%d (nächste=%.5f, %.1f Pips) | Sup=%d (nächste=%.5f, %.1f Pips)",
                      zones.resistance_count, zones.nearest_resistance, zones.dist_resistance_pips,
                      zones.support_count, zones.nearest_support, zones.dist_support_pips));
   return true;
}

//+------------------------------------------------------------------+
//| Prüfen ob Entry-Preis in sinnvollem Abstand zum Level liegt      |
//| direction: 1=Long (prüft Support), -1=Short (prüft Resistance)  |
//+------------------------------------------------------------------+
bool IsNearLevel(string symbol, SymbolZones &zones, int direction,
                 double min_distance_pips, double max_distance_pips)
{
   if(direction == 1)
   {
      // Long: Preis über Support und in Reichweite
      if(zones.nearest_support <= 0.0) return false;
      return (zones.dist_support_pips >= min_distance_pips &&
              zones.dist_support_pips <= max_distance_pips);
   }
   else if(direction == -1)
   {
      // Short: Preis unter Resistance und in Reichweite
      if(zones.nearest_resistance <= 0.0) return false;
      return (zones.dist_resistance_pips >= min_distance_pips &&
              zones.dist_resistance_pips <= max_distance_pips);
   }
   return false;
}

//+------------------------------------------------------------------+
//| Market-Data für Python Level Agent schreiben                     |
//| Letzten 200 Kerzen M15 + H1 für alle übergebenen Symbole        |
//+------------------------------------------------------------------+
void WriteMarketData(string &symbols[], int count, string path = "")
{
   string filename = (path == "") ? "market_data.json" : path;

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   string ts = StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                            dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);

   string json = "{\n  \"generated_at\": \"" + ts + "\",\n  \"symbols\": {\n";

   for(int s = 0; s < count; s++)
   {
      string sym = symbols[s];
      json += "    \"" + sym + "\": {\n";

      // M15 und H1 Daten
      ENUM_TIMEFRAMES tfs[2] = {PERIOD_M15, PERIOD_H1};
      string tf_names[2] = {"M15", "H1"};

      for(int t = 0; t < 2; t++)
      {
         MqlRates rates[];
         int copied = CopyRates(sym, tfs[t], 1, 200, rates);

         json += "      \"" + tf_names[t] + "\": [";

         if(copied > 0)
         {
            for(int i = 0; i < copied; i++)
            {
               MqlDateTime bar_dt;
               TimeToStruct(rates[i].time, bar_dt);
               string bar_ts = StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                                            bar_dt.year, bar_dt.mon, bar_dt.day,
                                            bar_dt.hour, bar_dt.min, bar_dt.sec);

               json += StringFormat("{\"t\":\"%s\",\"o\":%.5f,\"h\":%.5f,\"l\":%.5f,\"c\":%.5f,\"v\":%lld}",
                                    bar_ts,
                                    rates[i].open, rates[i].high,
                                    rates[i].low,  rates[i].close,
                                    rates[i].tick_volume);
               if(i < copied - 1) json += ",";
            }
         }

         json += "]";
         if(t < 1) json += ",\n";
         else       json += "\n";
      }

      json += "    }";
      if(s < count - 1) json += ",\n";
      else               json += "\n";
   }

   json += "  }\n}\n";

   // In Common Files schreiben
   int fh = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_COMMON);
   if(fh == INVALID_HANDLE)
   {
      LOG_E("LevelDetection", "ALL",
            "market_data.json konnte nicht geschrieben werden | Fehler: " + (string)GetLastError());
      return;
   }
   FileWriteString(fh, json);
   FileClose(fh);

   LOG_I("LevelDetection", "ALL",
         "market_data.json geschrieben | Symbole: " + (string)count);
}

#endif // INVESTAPP_LEVELDETECTION_MQH
