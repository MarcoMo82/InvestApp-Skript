//+------------------------------------------------------------------+
//| SymbolManager.mqh – Dynamisches Symbol-Management               |
//| Lädt Symbole aus Market Watch oder config.json Override         |
//| Kategorie-Erkennung primär via SYMBOL_TRADE_CALC_MODE           |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_SYMBOLMANAGER_MQH
#define INVESTAPP_SYMBOLMANAGER_MQH

#include <InvestApp/Logger.mqh>

//+------------------------------------------------------------------+
//| Kategorie-Erkennung via SYMBOL_TRADE_CALC_MODE                  |
//+------------------------------------------------------------------+

// Forex: SYMBOL_CALC_MODE_FOREX oder SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE
bool IsForexSymbol(string sym)
{
   long calc_mode = SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE);
   return (calc_mode == SYMBOL_CALC_MODE_FOREX ||
           calc_mode == SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE);
}

// Index: SYMBOL_CALC_MODE_CFDINDEX
bool IsIndexSymbol(string sym)
{
   long calc_mode = SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE);
   return (calc_mode == SYMBOL_CALC_MODE_CFDINDEX);
}

// Aktien: SYMBOL_CALC_MODE_CFD oder SYMBOL_CALC_MODE_CFDLEVERAGE
bool IsStockSymbol(string sym)
{
   long calc_mode = SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE);
   return (calc_mode == SYMBOL_CALC_MODE_CFD ||
           calc_mode == SYMBOL_CALC_MODE_CFDLEVERAGE);
}

// NASDAQ EA: Aktien (CFD/CFDLEVERAGE) + NASDAQ-Index (CFDINDEX mit Namenscheck)
bool IsNasdaqEASymbol(string sym)
{
   long calc_mode = SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE);

   if(calc_mode == SYMBOL_CALC_MODE_CFD || calc_mode == SYMBOL_CALC_MODE_CFDLEVERAGE)
      return true;

   if(calc_mode == SYMBOL_CALC_MODE_CFDINDEX)
   {
      string sym_upper = sym;
      StringToUpper(sym_upper);
      if(StringFind(sym_upper, "NAS")   >= 0 ||
         StringFind(sym_upper, "NDX")   >= 0 ||
         StringFind(sym_upper, "USTEC") >= 0 ||
         StringFind(sym_upper, "US100") >= 0 ||
         StringFind(sym_upper, "NQ")    >= 0)
         return true;
   }

   return false;
}

//+------------------------------------------------------------------+
//| Symbole aus Market Watch nach Kategorie laden                   |
//| category: "forex", "indexes" oder "nasdaq"                      |
//+------------------------------------------------------------------+
int LoadSymbolsFromMarketWatch(string &symbols[], string category)
{
   int count = 0;
   int total = SymbolsTotal(true); // true = nur Market Watch Symbole
   ArrayResize(symbols, total);

   for(int i = 0; i < total; i++)
   {
      string sym = SymbolName(i, true);
      bool match = false;

      if(category == "forex")
         match = IsForexSymbol(sym);
      else if(category == "indexes")
         match = IsIndexSymbol(sym);
      else if(category == "nasdaq")
         match = IsNasdaqEASymbol(sym);

      if(match)
      {
         symbols[count] = sym;
         count++;
      }
   }

   ArrayResize(symbols, count);
   return count;
}

//+------------------------------------------------------------------+
//| JSON-Array parsen: ["sym1", "sym2"] → string-Array              |
//+------------------------------------------------------------------+
int _ParseSymbolArray(string json_array, string &symbols[])
{
   ArrayResize(symbols, 0);

   int arr_start = StringFind(json_array, "[");
   int arr_end   = StringFind(json_array, "]");
   if(arr_start < 0 || arr_end < 0 || arr_end <= arr_start + 1)
      return 0;

   string content = StringSubstr(json_array, arr_start + 1, arr_end - arr_start - 1);
   StringTrimLeft(content);
   StringTrimRight(content);
   if(StringLen(content) == 0)
      return 0;

   // Alle gequoteten Strings extrahieren
   int count = 0;
   int pos   = 0;
   int len   = StringLen(content);

   while(pos < len)
   {
      int quote_start = StringFind(content, "\"", pos);
      if(quote_start < 0) break;
      int quote_end = StringFind(content, "\"", quote_start + 1);
      if(quote_end < 0) break;

      string sym = StringSubstr(content, quote_start + 1, quote_end - quote_start - 1);
      StringTrimLeft(sym);
      StringTrimRight(sym);

      if(StringLen(sym) > 0)
      {
         ArrayResize(symbols, count + 1);
         symbols[count] = sym;
         count++;
      }

      pos = quote_end + 1;
   }

   return count;
}

//+------------------------------------------------------------------+
//| Symbole laden: config.json Override hat Priorität              |
//| Fallback: automatisch aus Market Watch                          |
//| category:    "forex", "indexes" oder "nasdaq"                   |
//| config_path: leer = "config.json" in Common Files              |
//+------------------------------------------------------------------+
int LoadEASymbols(string &symbols[], string category, string config_path = "")
{
   // 1. config.json lesen und ea_symbols-Override prüfen
   string filename = (config_path == "") ? "config.json" : config_path;
   int fh = FileOpen(filename, FILE_READ | FILE_TXT | FILE_COMMON, '\n');

   if(fh != INVALID_HANDLE)
   {
      string json = "";
      while(!FileIsEnding(fh))
         json += FileReadString(fh) + "\n";
      FileClose(fh);

      // "ea_symbols"-Abschnitt extrahieren
      int sec_start = StringFind(json, "\"ea_symbols\"");
      if(sec_start >= 0)
      {
         int brace_start = StringFind(json, "{", sec_start);
         if(brace_start >= 0)
         {
            int depth = 0, jlen = StringLen(json);
            string sec = "";
            for(int i = brace_start; i < jlen; i++)
            {
               ushort ch = StringGetCharacter(json, i);
               if(ch == '{') depth++;
               else if(ch == '}')
               {
                  depth--;
                  if(depth == 0) { sec = StringSubstr(json, brace_start, i - brace_start + 1); break; }
               }
            }

            if(sec != "")
            {
               // Array für Kategorie suchen: "forex": [...] / "indexes": [...] / "nasdaq": [...]
               string key_search = "\"" + category + "\"";
               int key_pos = StringFind(sec, key_search);
               if(key_pos >= 0)
               {
                  int arr_start = StringFind(sec, "[", key_pos);
                  int arr_end   = StringFind(sec, "]", arr_start);
                  if(arr_start >= 0 && arr_end > arr_start)
                  {
                     string arr_str = StringSubstr(sec, arr_start, arr_end - arr_start + 1);
                     string override_syms[];
                     int override_count = _ParseSymbolArray(arr_str, override_syms);

                     if(override_count > 0)
                     {
                        ArrayResize(symbols, override_count);
                        for(int i = 0; i < override_count; i++)
                           symbols[i] = override_syms[i];
                        LOG_I("SymbolManager", category,
                              "Override aus config.json: " + IntegerToString(override_count) + " Symbole");
                        return override_count;
                     }
                  }
               }
            }
         }
      }
   }

   // 2. Fallback: dynamisch aus Market Watch laden
   int count = LoadSymbolsFromMarketWatch(symbols, category);

   if(count > 0)
      LOG_I("SymbolManager", category,
            "Market Watch: " + IntegerToString(count) + " Symbole geladen");
   else
      LOG_W("SymbolManager", category,
            "Keine Symbole gefunden! Market Watch und config.json prüfen.");

   return count;
}

#endif // INVESTAPP_SYMBOLMANAGER_MQH
