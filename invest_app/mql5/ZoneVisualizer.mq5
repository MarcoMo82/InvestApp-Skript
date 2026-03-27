//+------------------------------------------------------------------+
//|                                          ZoneVisualizer.mq5      |
//|                   InvestApp – Forecast-Zone & Signal Visualizer  |
//|                                                                  |
//|  Liest mt5_zones.json alle 15 Sekunden (OnTimer) und zeichnet:  |
//|   - Forecast-Zones  → oranges transparentes Rechteck (FZ_)     |
//|   - Signal Ready    → grüne Linie + Kaufpfeil/Verkaufspfeil     |
//|                        (SIG_LINE_ / SIG_TRI_)                  |
//|   - Active Trades   → blaue Entry-Linie (AT_)                  |
//+------------------------------------------------------------------+
#property copyright "InvestApp"
#property link      ""
#property version   "1.00"
#property strict

//--- Eingabe-Parameter
input string   InpZonesFile       = "mt5_zones.json";   // Dateiname (FILE_COMMON)
input int      InpTimerSeconds    = 15;                  // Aktualisierungsintervall (Sek.)
input int      InpForecastBars    = 30;                  // Breite Forecast-Rechteck (Bars)
input color    InpColorForecast   = clrOrange;           // Forecast-Zone Farbe
input color    InpColorSignalLine = clrLime;             // Signal-Linie Farbe
input color    InpColorActiveLine = C'100,160,255';      // Active-Trade Linie Farbe
input int      InpLineWidth       = 2;                   // Linienbreite

//--- Prefixe
#define FZ_PREFIX   "FZ_"
#define SIG_PREFIX  "SIG_"
#define AT_PREFIX   "AT_"

//--- Globale Zustandsvariablen
int    g_timer_ticks      = 0;
string g_last_update      = "";
bool   g_file_missing_log = false;

//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(1);
   LoadAndDraw();
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteByPrefix(FZ_PREFIX);
   DeleteByPrefix(SIG_PREFIX);
   DeleteByPrefix(AT_PREFIX);
   Comment("");
}

//+------------------------------------------------------------------+
void OnTick() {}

//+------------------------------------------------------------------+
void OnTimer()
{
   g_timer_ticks++;
   if(g_timer_ticks >= InpTimerSeconds)
   {
      g_timer_ticks = 0;
      LoadAndDraw();
   }
}

//+------------------------------------------------------------------+
//|  Hauptfunktion: JSON laden und Objekte zeichnen                  |
//+------------------------------------------------------------------+
void LoadAndDraw()
{
   string json = ReadFileContent(InpZonesFile);
   if(StringLen(json) == 0) return;

   g_last_update = ZvExtractString(json, "generated_at");

   // Alle bestehenden Zonen-Objekte löschen
   DeleteByPrefix(FZ_PREFIX);
   DeleteByPrefix(SIG_PREFIX);
   DeleteByPrefix(AT_PREFIX);

   string sym = Symbol();
   int zone_count = 0;

   // Zonen-Array auslesen
   string zones_arr = ZvExtractArray(json, "zones");
   if(StringLen(zones_arr) == 0)
   {
      UpdateComment(sym, 0);
      return;
   }

   int idx = 0;
   while(idx < 200)
   {
      string item = ZvExtractArrayItem(zones_arr, idx);
      if(StringLen(item) == 0) break;
      idx++;

      // Nur Einträge für das aktuelle Chart-Symbol
      string item_sym = ZvExtractString(item, "symbol");
      if(item_sym != sym) continue;

      string z_type = ZvExtractString(item, "type");

      if(z_type == "forecast_zone")
      {
         DrawForecastZone(item, sym, zone_count);
         zone_count++;
      }
      else if(z_type == "signal_ready")
      {
         DrawSignalReady(item, sym, zone_count);
         zone_count++;
      }
      else if(z_type == "active_trade")
      {
         DrawActiveTrade(item, sym, zone_count);
         zone_count++;
      }
   }

   UpdateComment(sym, zone_count);
   ChartRedraw();
}

//+------------------------------------------------------------------+
//|  Forecast-Zone: oranges transparentes Rechteck                   |
//+------------------------------------------------------------------+
void DrawForecastZone(string item, string sym, int idx)
{
   double zone_high = ZvExtractDouble(item, "zone_high");
   double zone_low  = ZvExtractDouble(item, "zone_low");
   if(zone_high <= 0.0 || zone_low <= 0.0 || zone_high <= zone_low) return;

   // Anker-Zeit (anchor_time als ISO-String → näherungsweise aktuelle Zeit nutzen)
   datetime t1 = iTime(NULL, 0, InpForecastBars);
   datetime t2 = iTime(NULL, 0, 0) + (datetime)(PeriodSeconds() * InpForecastBars);

   string name = FZ_PREFIX + sym + "_" + IntegerToString(idx);
   ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, zone_low, t2, zone_high);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      InpColorForecast);
   ObjectSetInteger(0, name, OBJPROP_WIDTH,      1);
   ObjectSetInteger(0, name, OBJPROP_FILL,       false);  // Transparent (nur Rahmen)
   ObjectSetInteger(0, name, OBJPROP_BACK,       true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN,     true);

   string dir   = ZvExtractString(item, "direction");
   double conf  = ZvExtractDouble(item, "confidence");
   string label = "FZ " + sym + " " + dir + " (" + DoubleToString(conf, 0) + "%)";
   ObjectSetString(0, name, OBJPROP_TEXT, label);
}

//+------------------------------------------------------------------+
//|  Signal Ready: grüne Linie + Pfeil                               |
//+------------------------------------------------------------------+
void DrawSignalReady(string item, string sym, int idx)
{
   double entry = ZvExtractDouble(item, "entry_price");
   double sl    = ZvExtractDouble(item, "stop_loss");
   double tp    = ZvExtractDouble(item, "take_profit");
   string dir   = ZvExtractString(item, "direction");
   string hint  = ZvExtractString(item, "trigger_hint");
   if(entry <= 0.0) return;

   string idx_str = IntegerToString(idx);

   // Entry-Linie
   string line_name = SIG_PREFIX + "LINE_" + sym + "_" + idx_str;
   ObjectCreate(0, line_name, OBJ_HLINE, 0, 0, entry);
   ObjectSetInteger(0, line_name, OBJPROP_COLOR,      InpColorSignalLine);
   ObjectSetInteger(0, line_name, OBJPROP_WIDTH,      InpLineWidth);
   ObjectSetInteger(0, line_name, OBJPROP_STYLE,      STYLE_SOLID);
   ObjectSetInteger(0, line_name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, line_name, OBJPROP_BACK,       true);
   ObjectSetInteger(0, line_name, OBJPROP_HIDDEN,     true);
   string entry_label = "SIG " + sym + " " + StringSubstr(dir, 0, 1) + " | " + hint;
   ObjectSetString(0, line_name, OBJPROP_TEXT, entry_label);

   // SL-Linie (rot gestrichelt)
   if(sl > 0.0)
   {
      string sl_name = SIG_PREFIX + "SL_" + sym + "_" + idx_str;
      ObjectCreate(0, sl_name, OBJ_HLINE, 0, 0, sl);
      ObjectSetInteger(0, sl_name, OBJPROP_COLOR,      clrRed);
      ObjectSetInteger(0, sl_name, OBJPROP_WIDTH,      1);
      ObjectSetInteger(0, sl_name, OBJPROP_STYLE,      STYLE_DASH);
      ObjectSetInteger(0, sl_name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, sl_name, OBJPROP_BACK,       true);
      ObjectSetInteger(0, sl_name, OBJPROP_HIDDEN,     true);
      ObjectSetString(0, sl_name, OBJPROP_TEXT, "SL " + DoubleToString(sl, _Digits));
   }

   // TP-Linie (grün gestrichelt)
   if(tp > 0.0)
   {
      string tp_name = SIG_PREFIX + "TP_" + sym + "_" + idx_str;
      ObjectCreate(0, tp_name, OBJ_HLINE, 0, 0, tp);
      ObjectSetInteger(0, tp_name, OBJPROP_COLOR,      clrLime);
      ObjectSetInteger(0, tp_name, OBJPROP_WIDTH,      1);
      ObjectSetInteger(0, tp_name, OBJPROP_STYLE,      STYLE_DASH);
      ObjectSetInteger(0, tp_name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, tp_name, OBJPROP_BACK,       true);
      ObjectSetInteger(0, tp_name, OBJPROP_HIDDEN,     true);
      ObjectSetString(0, tp_name, OBJPROP_TEXT, "TP " + DoubleToString(tp, _Digits));
   }

   // Pfeil-Objekt (Kauf/Verkauf)
   string tri_name = SIG_PREFIX + "TRI_" + sym + "_" + idx_str;
   datetime arrow_time = iTime(NULL, 0, 0);
   ENUM_OBJECT arrow_type = (dir == "long") ? OBJ_ARROW_BUY : OBJ_ARROW_SELL;
   ObjectCreate(0, tri_name, arrow_type, 0, arrow_time, entry);
   ObjectSetInteger(0, tri_name, OBJPROP_COLOR,      InpColorSignalLine);
   ObjectSetInteger(0, tri_name, OBJPROP_WIDTH,      InpLineWidth);
   ObjectSetInteger(0, tri_name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, tri_name, OBJPROP_HIDDEN,     true);
}

//+------------------------------------------------------------------+
//|  Active Trade: blaue Entry-Linie                                 |
//+------------------------------------------------------------------+
void DrawActiveTrade(string item, string sym, int idx)
{
   double entry = ZvExtractDouble(item, "entry_price");
   double sl    = ZvExtractDouble(item, "stop_loss");
   double tp    = ZvExtractDouble(item, "take_profit");
   string dir   = ZvExtractString(item, "direction");
   if(entry <= 0.0) return;

   string idx_str = IntegerToString(idx);

   // Entry-Linie (blau)
   string line_name = AT_PREFIX + "LINE_" + sym + "_" + idx_str;
   ObjectCreate(0, line_name, OBJ_HLINE, 0, 0, entry);
   ObjectSetInteger(0, line_name, OBJPROP_COLOR,      InpColorActiveLine);
   ObjectSetInteger(0, line_name, OBJPROP_WIDTH,      InpLineWidth);
   ObjectSetInteger(0, line_name, OBJPROP_STYLE,      STYLE_SOLID);
   ObjectSetInteger(0, line_name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, line_name, OBJPROP_BACK,       true);
   ObjectSetInteger(0, line_name, OBJPROP_HIDDEN,     true);
   ObjectSetString(0, line_name, OBJPROP_TEXT,
      "AT " + sym + " " + StringSubstr(dir, 0, 1) + " Entry:" + DoubleToString(entry, _Digits));

   // SL
   if(sl > 0.0)
   {
      string sl_name = AT_PREFIX + "SL_" + sym + "_" + idx_str;
      ObjectCreate(0, sl_name, OBJ_HLINE, 0, 0, sl);
      ObjectSetInteger(0, sl_name, OBJPROP_COLOR,      clrRed);
      ObjectSetInteger(0, sl_name, OBJPROP_WIDTH,      1);
      ObjectSetInteger(0, sl_name, OBJPROP_STYLE,      STYLE_DASH);
      ObjectSetInteger(0, sl_name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, sl_name, OBJPROP_BACK,       true);
      ObjectSetInteger(0, sl_name, OBJPROP_HIDDEN,     true);
      ObjectSetString(0, sl_name, OBJPROP_TEXT, "SL " + DoubleToString(sl, _Digits));
   }

   // TP
   if(tp > 0.0)
   {
      string tp_name = AT_PREFIX + "TP_" + sym + "_" + idx_str;
      ObjectCreate(0, tp_name, OBJ_HLINE, 0, 0, tp);
      ObjectSetInteger(0, tp_name, OBJPROP_COLOR,      clrLime);
      ObjectSetInteger(0, tp_name, OBJPROP_WIDTH,      1);
      ObjectSetInteger(0, tp_name, OBJPROP_STYLE,      STYLE_DASH);
      ObjectSetInteger(0, tp_name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, tp_name, OBJPROP_BACK,       true);
      ObjectSetInteger(0, tp_name, OBJPROP_HIDDEN,     true);
      ObjectSetString(0, tp_name, OBJPROP_TEXT, "TP " + DoubleToString(tp, _Digits));
   }
}

//+------------------------------------------------------------------+
//|  Kommentar aktualisieren                                         |
//+------------------------------------------------------------------+
void UpdateComment(string sym, int count)
{
   Comment(
      "InvestApp ZoneVisualizer\n" +
      "Symbol: " + sym + "\n" +
      "Letztes Update: " + g_last_update + "\n" +
      "Aktive Zonen/Signale: " + IntegerToString(count)
   );
}

//+------------------------------------------------------------------+
//|  Alle Objekte mit Prefix löschen                                |
//+------------------------------------------------------------------+
void DeleteByPrefix(string prefix)
{
   int total = ObjectsTotal(0);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i);
      if(StringFind(name, prefix) == 0)
         ObjectDelete(0, name);
   }
}

//+------------------------------------------------------------------+
//|  Datei einlesen                                                  |
//+------------------------------------------------------------------+
string ReadFileContent(string filename)
{
   int handle = FileOpen(filename, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      if(!g_file_missing_log)
      {
         Print("ZoneVisualizer: Warte auf ", filename, " in Common Files ...");
         g_file_missing_log = true;
      }
      return "";
   }
   g_file_missing_log = false;
   string content = "";
   while(!FileIsEnding(handle))
      content += FileReadString(handle) + "\n";
   FileClose(handle);
   return content;
}

//+------------------------------------------------------------------+
//|  JSON-Hilfsroutinen (Prefix "Zv" = ZoneVisualizer)             |
//+------------------------------------------------------------------+

string ZvExtractString(string block, string key)
{
   string search = "\"" + key + "\": \"";
   int pos = StringFind(block, search);
   if(pos < 0) { search = "\"" + key + "\":\""; pos = StringFind(block, search); }
   if(pos < 0) return "";
   pos += StringLen(search);
   int end = StringFind(block, "\"", pos);
   if(end < 0) return "";
   return StringSubstr(block, pos, end - pos);
}

double ZvExtractDouble(string block, string key)
{
   string search = "\"" + key + "\":";
   int pos = StringFind(block, search);
   if(pos < 0) { search = "\"" + key + "\": "; pos = StringFind(block, search); }
   if(pos < 0) return 0.0;
   pos += StringLen(search);
   int len = StringLen(block);
   while(pos < len) { ushort c = StringGetCharacter(block, pos); if(c != ' ' && c != '\t') break; pos++; }
   int end = pos;
   while(end < len)
   {
      ushort c = StringGetCharacter(block, end);
      if((c < '0' || c > '9') && c != '.' && c != '-' && c != 'e' && c != 'E' && c != '+') break;
      end++;
   }
   if(end == pos) return 0.0;
   return StringToDouble(StringSubstr(block, pos, end - pos));
}

string ZvExtractArray(string block, string key)
{
   string search = "\"" + key + "\":";
   int pos = StringFind(block, search);
   if(pos < 0) { search = "\"" + key + "\": "; pos = StringFind(block, search); }
   if(pos < 0) return "";
   pos = StringFind(block, "[", pos + StringLen(search));
   if(pos < 0) return "";
   int depth = 0, end = -1, len = StringLen(block);
   for(int i = pos; i < len; i++)
   {
      ushort c = StringGetCharacter(block, i);
      if(c == '[') depth++;
      else if(c == ']') { depth--; if(depth == 0) { end = i; break; } }
   }
   if(end < 0) return "";
   return StringSubstr(block, pos + 1, end - pos - 1);
}

string ZvExtractBracedBlock(string str, int start)
{
   int depth = 0, end = -1, len = StringLen(str);
   for(int i = start; i < len; i++)
   {
      ushort c = StringGetCharacter(str, i);
      if(c == '{') depth++;
      else if(c == '}') { depth--; if(depth == 0) { end = i; break; } }
   }
   if(end < 0) return "";
   return StringSubstr(str, start, end - start + 1);
}

string ZvExtractArrayItem(string arr, int index)
{
   int found = 0, pos = 0, len = StringLen(arr);
   while(pos < len)
   {
      int start = StringFind(arr, "{", pos);
      if(start < 0) break;
      string item = ZvExtractBracedBlock(arr, start);
      if(StringLen(item) == 0) break;
      if(found == index) return item;
      found++;
      pos = start + StringLen(item);
   }
   return "";
}
//+------------------------------------------------------------------+
