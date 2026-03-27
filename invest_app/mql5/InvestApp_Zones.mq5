//+------------------------------------------------------------------+
//|                                         InvestApp_Zones.mq5     |
//|                     InvestApp – MT5 Zonen-Visualisierung        |
//|                                                                  |
//|  Liest Output/mt5_zones.json und zeichnet alle Zonen live       |
//|  in den MT5-Chart. Alle 60 Sekunden (OnTimer) wird neu geladen. |
//+------------------------------------------------------------------+
#property copyright "InvestApp"
#property link      ""
#property version   "1.00"
#property strict

//--- Eingabe-Parameter
input string   InpZonesFile              = "mt5_zones.json";  // Dateiname (nur Name, kein Pfad – FILE_COMMON)
input color    InpColorEntryLong         = C'0,128,255';  // Entry-Zone Long
input color    InpColorEntryShort        = clrRed;        // Entry-Zone Short
input color    InpColorSL               = clrRed;        // Stop Loss
input color    InpColorTP               = clrLime;       // Take Profit
input color    InpColorOrderBlockBull   = clrYellow;     // Order Block Bullish
input color    InpColorOrderBlockBear   = clrOrange;     // Order Block Bearish
input color    InpColorPsychLevel       = clrGray;       // Psychologisches Level
input color    InpColorKeySupport       = clrLime;       // Key Level Support
input color    InpColorKeyResistance    = clrRed;        // Key Level Resistance
input int      InpLineWidthMain         = 2;             // Linienbreite (Haupt)
input int      InpLineWidthSecondary    = 1;             // Linienbreite (Neben)
input int      InpEntryZoneBars         = 10;            // Breite der Entry-Zone (Bars)
input int      InpOrderBlockBars        = 20;            // Breite der Order-Blocks (Bars)
input int      InpTimerSeconds          = 60;            // Aktualisierungsintervall (Sek.)

//--- Internes Prefix für alle InvestApp-Objekte
#define IA_PREFIX "IA_"

//+------------------------------------------------------------------+
//|  Trade-Management: Breakeven + ATR-Trailing                      |
//|  Der EA verwaltet SL autonom – Python liest nur Status.          |
//+------------------------------------------------------------------+
#define IA_MAX_TRADES 20

struct TradeManagement
{
   ulong  ticket;
   double entry_price;
   double atr_value;
   double breakeven_trigger;   // Preis ab dem Breakeven gesetzt wird (in Preis-Units)
   double trailing_distance;   // Trailing-Abstand in Preis-Units (1.5 × ATR)
   bool   breakeven_set;
   ENUM_POSITION_TYPE direction;
};

TradeManagement g_trades[IA_MAX_TRADES];
int             g_trade_count = 0;

//--- Globale Zustandsvariablen
string g_last_update        = "";
int    g_active_count       = 0;
int    g_timer_counter      = 0;
int    g_export_counter     = 0;
bool   g_file_missing_logged = false;  // Einmalig loggen wenn Datei fehlt

//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(1);  // 1s-Takt: Order-Polling + Zone-Update alle InpTimerSeconds
   ExportAvailableSymbols();
   LoadAndDraw();
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteAllIAObjects();
   Comment("");
}

//+------------------------------------------------------------------+
void OnTick() {}

//+------------------------------------------------------------------+
void OnTimer()
{
   g_timer_counter++;
   g_export_counter++;

   // Alle 10s kurze Heartbeat-Meldung damit sichtbar ist ob Timer läuft
   if(g_timer_counter % 10 == 0)
      Print("InvestApp Timer: ", g_timer_counter, "s | pending_order.json vorhanden: ",
            FileIsExist("pending_order.json", FILE_COMMON) ? "JA" : "NEIN");

   CheckPendingOrder();
   ManageTrades();

   if(g_timer_counter >= InpTimerSeconds)
   {
      g_timer_counter = 0;
      LoadAndDraw();
   }
   if(g_export_counter >= 60)
   {
      g_export_counter = 0;
      ExportAvailableSymbols();
   }
}

//+------------------------------------------------------------------+
//|  Hauptfunktion: JSON laden und alle Objekte für dieses Symbol    |
//|  neu zeichnen.                                                   |
//+------------------------------------------------------------------+
void LoadAndDraw()
{
   string json = ReadFileContent(InpZonesFile);
   if(StringLen(json) == 0)
   {
      Comment("InvestApp Zones\nDatei nicht gefunden:\n" + InpZonesFile +
              "\n(erwartet in MT5 Common Files)");
      return;
   }

   g_last_update = ExtractString(json, "generated_at");
   string sym    = Symbol();
   string block  = ExtractSymbolBlock(json, sym);

   DeleteAllIAObjects();
   g_active_count = 0;

   if(StringLen(block) == 0)
   {
      UpdateComment(sym);
      return;
   }

   if(ExtractBool(block, "signal_active"))
      g_active_count = 1;

   //--- Entry-Zone
   string ez_block = ExtractSubBlock(block, "entry_zone");
   if(StringLen(ez_block) > 0)
   {
      double ep     = ExtractDouble(ez_block, "price");
      double tol    = ExtractDouble(ez_block, "tolerance_pct");
      string ep_dir = ExtractString(ez_block, "direction");
      if(ep > 0.0)
      {
         double half = ep * tol / 100.0;
         color  clr  = (ep_dir == "long") ? InpColorEntryLong : InpColorEntryShort;
         DrawZoneRect("entry_zone", ep - half, ep + half, InpEntryZoneBars, clr);
      }
   }

   //--- Stop Loss
   double sl = ExtractDouble(block, "stop_loss");
   if(sl > 0.0)
      DrawHLine("sl", sl, "SL", InpColorSL, InpLineWidthMain, STYLE_SOLID);

   //--- Take Profit
   double tp = ExtractDouble(block, "take_profit");
   if(tp > 0.0)
      DrawHLine("tp", tp, "TP", InpColorTP, InpLineWidthMain, STYLE_SOLID);

   //--- EMA21-Referenzlinie
   double ema21 = ExtractDouble(block, "ema21");
   if(ema21 > 0.0)
      DrawHLine("ema21", ema21, "EMA21", InpColorPsychLevel, InpLineWidthSecondary, STYLE_DOT);

   //--- Order Blocks
   string ob_arr = ExtractArray(block, "order_blocks");
   if(StringLen(ob_arr) > 0)
      DrawOrderBlocks(ob_arr);

   //--- Psychologische Level
   string pl_arr = ExtractArray(block, "psychological_levels");
   if(StringLen(pl_arr) > 0)
      DrawPsychLevels(pl_arr);

   //--- Key Levels
   string kl_arr = ExtractArray(block, "key_levels");
   if(StringLen(kl_arr) > 0)
      DrawKeyLevels(kl_arr);

   UpdateComment(sym);
   ChartRedraw();
}

//+------------------------------------------------------------------+
//|  Zeichenfunktionen                                               |
//+------------------------------------------------------------------+

void DrawZoneRect(string id, double price_low, double price_high, int bars_back, color clr)
{
   string   name = IA_PREFIX + id;
   datetime t1   = iTime(NULL, 0, bars_back);
   datetime t2   = iTime(NULL, 0, 0) + (datetime)(PeriodSeconds() * 3);

   ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, price_low, t2, price_high);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_WIDTH,      InpLineWidthMain);
   ObjectSetInteger(0, name, OBJPROP_FILL,       true);
   ObjectSetInteger(0, name, OBJPROP_BACK,       true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN,     true);
}

void DrawHLine(string id, double price, string label, color clr, int width, ENUM_LINE_STYLE style)
{
   string name = IA_PREFIX + id;
   ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_WIDTH,      width);
   ObjectSetInteger(0, name, OBJPROP_STYLE,      style);
   ObjectSetString (0, name, OBJPROP_TEXT,       label + " " + DoubleToString(price, _Digits));
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_BACK,       true);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN,     true);
}

void DrawOrderBlocks(string arr)
{
   int count = 0;
   int idx   = 0;
   while(idx < 50)
   {
      string item = ExtractArrayItem(arr, idx);
      if(StringLen(item) == 0) break;

      double ob_high  = ExtractDouble(item, "high");
      double ob_low   = ExtractDouble(item, "low");
      string ob_dir   = ExtractString(item, "direction");
      bool   consumed = ExtractBool(item, "consumed");

      if(ob_high > 0.0 && ob_low > 0.0 && !consumed)
      {
         color    clr  = (ob_dir == "bullish") ? InpColorOrderBlockBull : InpColorOrderBlockBear;
         string   name = IA_PREFIX + "ob_" + IntegerToString(count);
         datetime t1   = iTime(NULL, 0, InpOrderBlockBars);
         datetime t2   = iTime(NULL, 0, 0) + (datetime)(PeriodSeconds() * 3);

         ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, ob_low, t2, ob_high);
         ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
         ObjectSetInteger(0, name, OBJPROP_WIDTH,      InpLineWidthSecondary);
         ObjectSetInteger(0, name, OBJPROP_FILL,       true);
         ObjectSetInteger(0, name, OBJPROP_BACK,       true);
         ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, name, OBJPROP_HIDDEN,     true);
         count++;
      }
      idx++;
   }
}

void DrawPsychLevels(string arr)
{
   int count = 0;
   int idx   = 0;
   while(idx < 20)
   {
      string item = ExtractSimpleArrayItem(arr, idx);
      if(StringLen(item) == 0) break;

      double price = StringToDouble(item);
      if(price > 0.0)
      {
         string name  = IA_PREFIX + "psych_" + IntegerToString(count);
         string label = "Psych " + DoubleToString(price, _Digits);
         DrawHLine("psych_" + IntegerToString(count), price, label,
                   InpColorPsychLevel, InpLineWidthSecondary, STYLE_DASH);
         count++;
      }
      idx++;
   }
}

void DrawKeyLevels(string arr)
{
   int count = 0;
   int idx   = 0;
   while(idx < 20)
   {
      string item = ExtractArrayItem(arr, idx);
      if(StringLen(item) == 0) break;

      double price    = ExtractDouble(item, "price");
      string kl_type  = ExtractString(item, "type");
      int    strength = (int)ExtractDouble(item, "strength");

      if(price > 0.0)
      {
         color  clr   = (kl_type == "support") ? InpColorKeySupport : InpColorKeyResistance;
         string stars = "";
         for(int s = 0; s < strength; s++) stars += "*";
         string label = kl_type + " " + stars;
         DrawHLine("kl_" + IntegerToString(count), price, label,
                   clr, InpLineWidthSecondary, STYLE_DASH);
         count++;
      }
      idx++;
   }
}

void UpdateComment(string sym)
{
   string active_str = (g_active_count > 0) ? IntegerToString(g_active_count) : "0";
   Comment(
      "InvestApp Zones\n" +
      "Symbol: " + sym + "\n" +
      "Letztes Update: " + g_last_update + "\n" +
      "Aktive Signale: " + active_str
   );
}

void DeleteAllIAObjects()
{
   int total = ObjectsTotal(0);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i);
      if(StringFind(name, IA_PREFIX) == 0)
         ObjectDelete(0, name);
   }
}

//+------------------------------------------------------------------+
//|  Verfügbare Symbole nach available_symbols.json exportieren      |
//|  Format: ["EURUSD","GBPUSD",...]  (einfaches JSON-Array)        |
//+------------------------------------------------------------------+
void ExportAvailableSymbols()
{
   string filename = "available_symbols.json";
   int total = SymbolsTotal(true);  // true = nur sichtbare Symbole

   string json = "[";
   bool first = true;
   for(int i = 0; i < total; i++)
   {
      string sym = SymbolName(i, true);
      if(StringLen(sym) == 0) continue;
      if(!first) json += ",";
      json += "\"" + sym + "\"";
      first = false;
   }
   json += "]";

   int fh = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh == INVALID_HANDLE)
   {
      Print("ExportAvailableSymbols: Fehler beim Öffnen von ", filename,
            " (Fehler ", GetLastError(), ")");
      return;
   }
   FileWriteString(fh, json);
   FileClose(fh);
   Print("ExportAvailableSymbols: ", total, " Symbole exportiert → ", filename);
}

//+------------------------------------------------------------------+
//|  Datei einlesen                                                  |
//+------------------------------------------------------------------+
string ReadFileContent(string filename)
{
   // Nur Dateiname (kein Pfad) + FILE_COMMON → MT5 Common Files Verzeichnis
   int handle = FileOpen(filename, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);

   if(handle == INVALID_HANDLE)
   {
      // Datei existiert noch nicht (z.B. beim ersten Start, Fehler 5004) – still ignorieren
      if(!g_file_missing_logged)
      {
         Print("InvestApp_Zones: Warte auf ", filename, " in Common Files ...");
         g_file_missing_logged = true;
      }
      return "";
   }

   g_file_missing_logged = false;  // Datei gefunden – beim nächsten Fehlen wieder loggen

   string content = "";
   while(!FileIsEnding(handle))
      content += FileReadString(handle) + "\n";

   FileClose(handle);
   return content;
}

//+------------------------------------------------------------------+
//|  JSON-Parsing-Hilfsfunktionen                                    |
//+------------------------------------------------------------------+

// Extrahiert den Symbol-Block aus dem JSON: "SYMBOL": { ... }
string ExtractSymbolBlock(string json, string sym)
{
   string search = "\"" + sym + "\":";
   int pos = StringFind(json, search);
   if(pos < 0) return "";

   pos = StringFind(json, "{", pos + StringLen(search));
   if(pos < 0) return "";

   return ExtractBracedBlock(json, pos);
}

// Extrahiert einen Sub-Block: "key": { ... }
string ExtractSubBlock(string block, string key)
{
   string search = "\"" + key + "\":";
   int pos = StringFind(block, search);
   if(pos < 0) return "";

   pos = StringFind(block, "{", pos + StringLen(search));
   if(pos < 0) return "";

   return ExtractBracedBlock(block, pos);
}

// Extrahiert den Inhalt eines Arrays: "key": [ ... ] → Inhalt zwischen den eckigen Klammern
string ExtractArray(string block, string key)
{
   string search = "\"" + key + "\":";
   int pos = StringFind(block, search);
   if(pos < 0) return "";

   pos = StringFind(block, "[", pos + StringLen(search));
   if(pos < 0) return "";

   int depth = 0, end = -1;
   int len = StringLen(block);
   for(int i = pos; i < len; i++)
   {
      ushort c = StringGetCharacter(block, i);
      if(c == '[')      depth++;
      else if(c == ']') { depth--; if(depth == 0) { end = i; break; } }
   }
   if(end < 0) return "";
   return StringSubstr(block, pos + 1, end - pos - 1);
}

// Extrahiert einen in geschweifte Klammern eingeschlossenen Block ab Position start
string ExtractBracedBlock(string str, int start)
{
   int depth = 0, end = -1;
   int len = StringLen(str);
   for(int i = start; i < len; i++)
   {
      ushort c = StringGetCharacter(str, i);
      if(c == '{')      depth++;
      else if(c == '}') { depth--; if(depth == 0) { end = i; break; } }
   }
   if(end < 0) return "";
   return StringSubstr(str, start, end - start + 1);
}

// Extrahiert das n-te Objekt { ... } aus einem Array-String
string ExtractArrayItem(string arr, int index)
{
   int found = 0, pos = 0;
   int len = StringLen(arr);
   while(pos < len)
   {
      int start = StringFind(arr, "{", pos);
      if(start < 0) break;
      string item = ExtractBracedBlock(arr, start);
      if(StringLen(item) == 0) break;
      if(found == index) return item;
      found++;
      pos = start + StringLen(item);
   }
   return "";
}

// Extrahiert das n-te Element aus einem einfachen Zahlen-Array [1.0, 2.0, 3.0]
string ExtractSimpleArrayItem(string arr, int index)
{
   int found = 0, pos = 0;
   int len = StringLen(arr);

   while(pos < len)
   {
      // Whitespace überspringen
      ushort c = StringGetCharacter(arr, pos);
      while(pos < len && (c == ' ' || c == '\n' || c == '\r' || c == '\t'))
      {
         pos++;
         if(pos < len) c = StringGetCharacter(arr, pos);
      }
      if(pos >= len) break;

      // Wert-Ende suchen (bis Komma oder Ende des Arrays)
      int end = pos;
      while(end < len)
      {
         c = StringGetCharacter(arr, end);
         if(c == ',' || c == ']') break;
         end++;
      }

      string val = StringSubstr(arr, pos, end - pos);
      StringTrimLeft(val);
      StringTrimRight(val);

      if(StringLen(val) > 0)
      {
         if(found == index) return val;
         found++;
      }
      pos = end + 1;
   }
   return "";
}

// Liest einen Double-Wert: "key": 1.234
double ExtractDouble(string block, string key)
{
   string search = "\"" + key + "\":";
   int pos = StringFind(block, search);
   if(pos < 0) return 0.0;

   pos += StringLen(search);
   int len = StringLen(block);

   // Whitespace überspringen
   while(pos < len)
   {
      ushort c = StringGetCharacter(block, pos);
      if(c != ' ' && c != '\n' && c != '\r' && c != '\t') break;
      pos++;
   }

   // Zahl extrahieren
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

// Liest einen String-Wert: "key": "value"
string ExtractString(string block, string key)
{
   // Mit Leerzeichen nach Doppelpunkt
   string search = "\"" + key + "\": \"";
   int pos = StringFind(block, search);
   if(pos < 0)
   {
      // Ohne Leerzeichen
      search = "\"" + key + "\":\"";
      pos = StringFind(block, search);
   }
   if(pos < 0) return "";

   pos += StringLen(search);
   int end = StringFind(block, "\"", pos);
   if(end < 0) return "";
   return StringSubstr(block, pos, end - pos);
}

// Liest einen Bool-Wert: "key": true / false
bool ExtractBool(string block, string key)
{
   string search = "\"" + key + "\": ";
   int pos = StringFind(block, search);
   if(pos < 0)
   {
      search = "\"" + key + "\":";
      pos = StringFind(block, search);
   }
   if(pos < 0) return false;

   pos += StringLen(search);
   int len = StringLen(block);

   // Whitespace überspringen
   while(pos < len)
   {
      ushort c = StringGetCharacter(block, pos);
      if(c != ' ' && c != '\t') break;
      pos++;
   }

   return (StringSubstr(block, pos, 4) == "true");
}

//+------------------------------------------------------------------+
//|  JSON-Parser für pending_order.json (robuste Variante)           |
//+------------------------------------------------------------------+
string ParseJsonString(string json, string key)
{
   string search = "\"" + key + "\"";
   int key_pos = StringFind(json, search);
   if(key_pos < 0) return "";
   int colon_pos = StringFind(json, ":", key_pos);
   if(colon_pos < 0) return "";
   int first_quote = StringFind(json, "\"", colon_pos + 1);
   if(first_quote < 0) return "";
   int second_quote = StringFind(json, "\"", first_quote + 1);
   if(second_quote < 0) return "";
   return StringSubstr(json, first_quote + 1, second_quote - first_quote - 1);
}

double ParseJsonDouble(string json, string key)
{
   string search = "\"" + key + "\"";
   int key_pos = StringFind(json, search);
   if(key_pos < 0) return 0.0;
   int colon_pos = StringFind(json, ":", key_pos);
   if(colon_pos < 0) return 0.0;
   int start = colon_pos + 1;
   int len = StringLen(json);
   while(start < len)
   {
      ushort ch = StringGetCharacter(json, start);
      if(ch != ' ' && ch != '\t' && ch != '\r' && ch != '\n') break;
      start++;
   }
   int end = start;
   while(end < len)
   {
      ushort ch = StringGetCharacter(json, end);
      if(!((ch >= '0' && ch <= '9') || ch == '.' || ch == '-' || ch == '+')) break;
      end++;
   }
   return StringToDouble(StringSubstr(json, start, end - start));
}

double NormalizeVolume(const string symbol, double volume)
{
   double min_vol  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double max_vol  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double step_vol = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(step_vol <= 0) return volume;
   volume = MathMax(min_vol, MathMin(max_vol, volume));
   volume = MathFloor(volume / step_vol) * step_vol;
   int digits = 2;
   if(step_vol == 1.0)      digits = 0;
   else if(step_vol == 0.1) digits = 1;
   else if(step_vol == 0.001) digits = 3;
   return NormalizeDouble(volume, digits);
}

//+------------------------------------------------------------------+
//|  Trade-Management: Breakeven + ATR-Trailing (EA-autonom)        |
//+------------------------------------------------------------------+

// Hilfsfunktion: SL einer Position modifizieren
bool ModifySL(ulong ticket, double new_sl)
{
   MqlTradeRequest req = {};
   MqlTradeResult  res = {};
   req.action   = TRADE_ACTION_SLTP;
   req.position = ticket;
   if(!PositionSelectByTicket(ticket)) return false;
   req.symbol = PositionGetString(POSITION_SYMBOL);
   req.sl     = NormalizeDouble(new_sl, (int)SymbolInfoInteger(req.symbol, SYMBOL_DIGITS));
   req.tp     = PositionGetDouble(POSITION_TP);
   bool ok = OrderSend(req, res);
   if(!ok || res.retcode != TRADE_RETCODE_DONE)
      Print("ModifySL Fehler Ticket=", ticket, " SL=", new_sl, " retcode=", res.retcode);
   return ok && (res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_PLACED);
}

// Hilfsfunktion: TradeManagement-Eintrag für ein Ticket suchen (-1 wenn nicht gefunden)
int FindTradeIndex(ulong ticket)
{
   for(int i = 0; i < g_trade_count; i++)
      if(g_trades[i].ticket == ticket) return i;
   return -1;
}

// Hilfsfunktion: Neuen TradeManagement-Eintrag anlegen
void RegisterTrade(ulong ticket, double entry, double atr_val, double be_trigger_pips, double trailing_mult)
{
   if(g_trade_count >= IA_MAX_TRADES) return;
   if(!PositionSelectByTicket(ticket)) return;

   ENUM_POSITION_TYPE pos_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   string symbol = PositionGetString(POSITION_SYMBOL);
   double point  = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int    digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

   // ATR als Preis-Units (aus pending_order.json direkt in Preis-Units)
   double atr_price = atr_val;

   // Breakeven-Trigger in Preis-Units (be_trigger_pips × Point × 10 für 5-digit-Broker)
   double be_trigger_price = (be_trigger_pips > 0) ? (be_trigger_pips * point * 10) : atr_price;

   // Trailing-Abstand = trailing_mult × ATR
   double trailing_dist = trailing_mult * atr_price;

   int idx = g_trade_count;
   g_trades[idx].ticket           = ticket;
   g_trades[idx].entry_price      = entry;
   g_trades[idx].atr_value        = atr_price;
   g_trades[idx].breakeven_trigger = be_trigger_price;
   g_trades[idx].trailing_distance = trailing_dist;
   g_trades[idx].breakeven_set    = false;
   g_trades[idx].direction        = pos_type;
   g_trade_count++;

   Print("InvestApp TradeManagement registriert: Ticket=", ticket,
         " Entry=", NormalizeDouble(entry, digits),
         " BE-Trigger=", NormalizeDouble(be_trigger_price, digits),
         " Trailing=", NormalizeDouble(trailing_dist, digits));
}

void ManageTrades()
{
   // Nicht mehr vorhandene Positionen aus Array entfernen
   for(int i = g_trade_count - 1; i >= 0; i--)
   {
      if(!PositionSelectByTicket(g_trades[i].ticket))
      {
         // Position geschlossen → aus Array entfernen
         for(int j = i; j < g_trade_count - 1; j++)
            g_trades[j] = g_trades[j + 1];
         g_trade_count--;
      }
   }

   // Alle registrierten offenen Positionen verwalten
   for(int i = 0; i < g_trade_count; i++)
   {
      ulong ticket = g_trades[i].ticket;
      if(!PositionSelectByTicket(ticket)) continue;

      double current_price = PositionGetDouble(POSITION_PRICE_CURRENT);
      double current_sl    = PositionGetDouble(POSITION_SL);
      double entry         = g_trades[i].entry_price;
      ENUM_POSITION_TYPE pos_type = g_trades[i].direction;

      // ── BREAKEVEN: Wenn Preis ≥ entry + breakeven_trigger ─────────
      if(!g_trades[i].breakeven_set)
      {
         bool be_condition = false;
         if(pos_type == POSITION_TYPE_BUY)
            be_condition = (current_price >= entry + g_trades[i].breakeven_trigger);
         else
            be_condition = (current_price <= entry - g_trades[i].breakeven_trigger);

         if(be_condition)
         {
            double be_price = NormalizeDouble(entry,
               (int)SymbolInfoInteger(PositionGetString(POSITION_SYMBOL), SYMBOL_DIGITS));
            // SL auf Entry setzen (Breakeven)
            if((pos_type == POSITION_TYPE_BUY  && be_price > current_sl) ||
               (pos_type == POSITION_TYPE_SELL && be_price < current_sl))
            {
               if(ModifySL(ticket, be_price))
               {
                  g_trades[i].breakeven_set = true;
                  Print("InvestApp Breakeven gesetzt: Ticket=", ticket, " SL=", be_price);
               }
            }
            else
            {
               // Bereits on Breakeven oder besser
               g_trades[i].breakeven_set = true;
            }
         }
      }
      // ── ATR-TRAILING: Erst nach Breakeven ─────────────────────────
      else
      {
         string sym   = PositionGetString(POSITION_SYMBOL);
         int    digs  = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
         double new_sl;

         if(pos_type == POSITION_TYPE_BUY)
         {
            new_sl = NormalizeDouble(current_price - g_trades[i].trailing_distance, digs);
            // SL nur verbessern (niemals zurückziehen)
            if(new_sl > current_sl)
               ModifySL(ticket, new_sl);
         }
         else
         {
            new_sl = NormalizeDouble(current_price + g_trades[i].trailing_distance, digs);
            if(new_sl < current_sl || current_sl == 0)
               ModifySL(ticket, new_sl);
         }
      }
   }
}

//+------------------------------------------------------------------+
//|  Order-Polling: liest pending_order.json und führt Order aus     |
//+------------------------------------------------------------------+
void CheckPendingOrder()
{
   string path = "pending_order.json";
   if(!FileIsExist(path, FILE_COMMON)) return;

   // Datei einlesen
   int fh = FileOpen(path, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh == INVALID_HANDLE)
   {
      Print("InvestApp: Fehler beim Öffnen pending_order.json: ", GetLastError());
      return;
   }
   string content = "";
   while(!FileIsEnding(fh))
      content += FileReadString(fh);
   FileClose(fh);

   Print("InvestApp: JSON gelesen (", StringLen(content), " Zeichen): ", StringSubstr(content, 0, 120));

   // Status prüfen
   string status = ParseJsonString(content, "status");
   StringToLower(status);
   if(status != "pending")
   {
      Print("InvestApp: Status='", status, "' – keine Aktion");
      return;
   }

   // Alters-Check
   double created_at = ParseJsonDouble(content, "created_at");
   if(created_at > 0 && (double)TimeCurrent() - created_at > 30.0)
   {
      Print("InvestApp: Order veraltet (>30s) – setze 'expired'");
      string upd = content;
      StringReplace(upd, "\"pending\"", "\"expired\"");
      int fw = FileOpen(path, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
      if(fw != INVALID_HANDLE) { FileWriteString(fw, upd); FileClose(fw); }
      return;
   }

   // Felder parsen
   string symbol    = ParseJsonString(content, "symbol");
   string direction = ParseJsonString(content, "direction");
   double volume    = ParseJsonDouble(content, "volume");
   double sl        = ParseJsonDouble(content, "sl");
   double tp        = ParseJsonDouble(content, "tp");
   string comment   = ParseJsonString(content, "comment");
   StringToLower(direction);

   if(symbol == "" || direction == "" || volume <= 0)
   {
      Print("InvestApp: Pflichtfelder fehlen – symbol='", symbol, "' direction='", direction, "' volume=", volume);
      return;
   }

   // Symbol aktivieren
   if(!SymbolSelect(symbol, true))
      Print("InvestApp: SymbolSelect fehlgeschlagen für ", symbol);

   // Marktpreise
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   if(ask <= 0 || bid <= 0)
   {
      Print("InvestApp: Keine gültigen Preise für ", symbol, " ask=", ask, " bid=", bid);
      return;
   }

   ENUM_ORDER_TYPE order_type;
   double price;
   if(direction == "buy")  { order_type = ORDER_TYPE_BUY;  price = ask; }
   else                    { order_type = ORDER_TYPE_SELL; price = bid; }

   // Volumen normalisieren
   volume = NormalizeVolume(symbol, volume);

   // Filling-Mode ermitteln
   long filling_mode = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   long exec_mode    = SymbolInfoInteger(symbol, SYMBOL_TRADE_EXEMODE);
   ENUM_ORDER_TYPE_FILLING type_filling;
   if((filling_mode & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      type_filling = ORDER_FILLING_IOC;
   else if((filling_mode & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      type_filling = ORDER_FILLING_FOK;
   else if(exec_mode != SYMBOL_TRADE_EXECUTION_MARKET)
      type_filling = ORDER_FILLING_RETURN;
   else
      type_filling = ORDER_FILLING_IOC;  // Fallback

   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};
   MqlTradeCheckResult check = {};

   request.action       = TRADE_ACTION_DEAL;
   request.symbol       = symbol;
   request.volume       = volume;
   request.type         = order_type;
   request.type_filling = type_filling;
   request.price        = NormalizeDouble(price, digits);
   request.sl           = NormalizeDouble(sl, digits);
   request.tp           = NormalizeDouble(tp, digits);
   request.deviation    = 20;
   request.magic        = 20260324;
   request.comment      = (comment != "") ? comment : "InvestApp";

   // Vorab-Validierung
   if(!OrderCheck(request, check))
   {
      Print("InvestApp OrderCheck FEHLER: retcode=", check.retcode, " comment=", check.comment);
      return;
   }

   bool sent = OrderSend(request, result);
   bool success = sent && (result.retcode == TRADE_RETCODE_DONE ||
                           result.retcode == TRADE_RETCODE_PLACED ||
                           result.retcode == TRADE_RETCODE_DONE_PARTIAL);
   string new_status = success ? "executed" : "failed";

   if(success)
   {
      Print("InvestApp Order ERFOLG: ", symbol, " ", direction,
            " Vol=", DoubleToString(volume,2), " Preis=", NormalizeDouble(price,digits),
            " SL=", NormalizeDouble(sl,digits), " TP=", NormalizeDouble(tp,digits),
            " Order=", result.order, " Deal=", result.deal);

      // Trade-Management registrieren (Breakeven + ATR-Trailing)
      double atr_val        = ParseJsonDouble(content, "atr_value");
      double be_pips        = ParseJsonDouble(content, "breakeven_trigger_pips");
      double trailing_mult  = ParseJsonDouble(content, "trailing_atr_multiplier");
      if(trailing_mult <= 0) trailing_mult = 1.5;  // Default
      if(atr_val > 0 && result.order > 0)
         RegisterTrade((ulong)result.order, price, atr_val, be_pips, trailing_mult);
   }
   else
      Print("InvestApp Order FEHLER: retcode=", result.retcode,
            " comment=", result.comment, " filling=", EnumToString(type_filling));

   // JSON aktualisieren
   string updated = content;
   StringReplace(updated, "\"pending\"", "\"" + new_status + "\"");
   if(result.order > 0)
      StringReplace(updated, "\"status\"", "\"ticket\":" + IntegerToString(result.order) + ",\"status\"");
   if(!success)
      StringReplace(updated, "\"status\"", "\"retcode\":" + IntegerToString(result.retcode) + ",\"status\"");

   fh = FileOpen(path, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, updated); FileClose(fh); }
}

//+------------------------------------------------------------------+
