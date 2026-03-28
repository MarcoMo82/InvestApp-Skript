//+------------------------------------------------------------------+
//| TradeManagement.mqh – 3-Phasen Trailing Stop State-Machine      |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_TRADEMANAGEMENT_MQH
#define INVESTAPP_TRADEMANAGEMENT_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>
#include <InvestApp/SessionManager.mqh>
#include <InvestApp/RiskManager.mqh>

//+------------------------------------------------------------------+
//| SL einer Position modifizieren                                   |
//+------------------------------------------------------------------+
bool ModifySL(ulong ticket, string symbol, double new_sl)
{
   if(!PositionSelectByTicket(ticket)) return false;

   int    digits    = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   new_sl = NormalizeDouble(new_sl, digits);

   ENUM_POSITION_TYPE pos_type     = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double             current_price = PositionGetDouble(POSITION_PRICE_CURRENT);

   // Mindestabstand (SYMBOL_TRADE_STOPS_LEVEL) prüfen
   int    stops_level = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double point       = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double min_dist    = stops_level * point;

   double dist = (pos_type == POSITION_TYPE_BUY)
                 ? current_price - new_sl
                 : new_sl - current_price;

   if(dist < min_dist && min_dist > 0)
   {
      LOG_W("TradeManagement", symbol,
            StringFormat("ModifySL: Mindestabstand nicht eingehalten | dist=%.5f | min=%.5f",
                         dist, min_dist));
      return false;
   }

   MqlTradeRequest req = {};
   MqlTradeResult  res = {};
   req.action   = TRADE_ACTION_SLTP;
   req.position = ticket;
   req.symbol   = symbol;
   req.sl       = new_sl;
   req.tp       = PositionGetDouble(POSITION_TP);

   bool ok = OrderSend(req, res);
   if(!ok || (res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_PLACED))
   {
      LOG_W("TradeManagement", symbol,
            StringFormat("ModifySL fehlgeschlagen | SL=%.5f | retcode=%d | error=%d",
                         new_sl, res.retcode, GetLastError()));
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Letztes signifikantes Higher Low (Long) finden                   |
//| Gibt das höchste Pivot-Low der letzten lookback Kerzen (15m)    |
//| Fallback: 0.0 wenn kein Pivot gefunden                          |
//+------------------------------------------------------------------+
double FindLastHigherLow(string symbol, int lookback)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   // +2 Pufferstellen damit Nachbarn für ersten/letzten Index vorhanden
   if(CopyRates(symbol, PERIOD_M15, 1, lookback + 2, rates) < lookback + 2)
      return 0.0;

   double highest_pivot_low = 0.0;

   for(int i = 1; i < lookback; i++)
   {
      // Pivot Low: Low[i] tiefer als beide Nachbarn (lokales Minimum)
      if(rates[i].low < rates[i - 1].low && rates[i].low < rates[i + 1].low)
      {
         if(rates[i].low > highest_pivot_low)
            highest_pivot_low = rates[i].low;
      }
   }

   return highest_pivot_low;
}

//+------------------------------------------------------------------+
//| Letztes signifikantes Lower High (Short) finden                  |
//| Gibt das niedrigste Pivot-High der letzten lookback Kerzen (15m) |
//| Fallback: 0.0 wenn kein Pivot gefunden                           |
//+------------------------------------------------------------------+
double FindLastLowerHigh(string symbol, int lookback)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(symbol, PERIOD_M15, 1, lookback + 2, rates) < lookback + 2)
      return 0.0;

   double lowest_pivot_high = 0.0;

   for(int i = 1; i < lookback; i++)
   {
      // Pivot High: High[i] höher als beide Nachbarn (lokales Maximum)
      if(rates[i].high > rates[i - 1].high && rates[i].high > rates[i + 1].high)
      {
         if(lowest_pivot_high <= 0.0 || rates[i].high < lowest_pivot_high)
            lowest_pivot_high = rates[i].high;
      }
   }

   return lowest_pivot_high;
}

//+------------------------------------------------------------------+
//| Trade-Management: 3-Phasen State-Machine für alle Positionen    |
//| Aufrufen in OnTimer() alle 30s                                   |
//+------------------------------------------------------------------+
void ManageTrades(string &symbols[], int count, AppConfig &cfg)
{
   int total = PositionsTotal();
   for(int p = 0; p < total; p++)
   {
      ulong ticket = PositionGetTicket(p);
      if(!PositionSelectByTicket(ticket)) continue;

      string symbol = PositionGetString(POSITION_SYMBOL);

      // Nur verwaltete Symbole
      bool managed = false;
      for(int s = 0; s < count; s++)
         if(symbols[s] == symbol) { managed = true; break; }
      if(!managed) continue;

      // Position-State suchen
      int idx = FindPositionState(ticket);
      if(idx < 0) continue;   // nicht registriert → überspringen

      ENUM_POSITION_TYPE pos_type     = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      int                direction    = (pos_type == POSITION_TYPE_BUY) ? 1 : -1;
      double             entry_price  = PositionGetDouble(POSITION_PRICE_OPEN);
      double             current_price = PositionGetDouble(POSITION_PRICE_CURRENT);
      double             current_sl   = PositionGetDouble(POSITION_SL);

      double pip_size = GetPipSize(symbol);
      double atr      = GetATR(symbol, PERIOD_M15, 14, 1);
      if(atr <= 0.0 || pip_size <= 0.0) continue;

      double profit_pips = direction * (current_price - entry_price) / pip_size;

      TRADE_STATE state = g_positions[idx].state;

      //----------------------------------------------------------------
      // Phase 1 → Phase 2: Breakeven
      //----------------------------------------------------------------
      if(state == STATE_INITIAL)
      {
         double be_trigger_pips = cfg.trade_management.breakeven_trigger_atr * (atr / pip_size);
         if(profit_pips >= be_trigger_pips)
         {
            double buffer = atr * 0.25;
            double new_sl = (direction == 1) ? entry_price + buffer : entry_price - buffer;

            bool sl_improved = (direction == 1) ? (new_sl > current_sl) : (new_sl < current_sl || current_sl <= 0.0);
            if(sl_improved)
            {
               if(ModifySL(ticket, symbol, new_sl))
               {
                  g_positions[idx].state = STATE_BREAKEVEN;
                  LOG_I("TradeManagement", symbol,
                        "Breakeven gesetzt | SL=" + DoubleToString(new_sl, 5));
               }
            }
         }
      }

      //----------------------------------------------------------------
      // Phase 2 → Phase 3: Struktur-Trailing aktivieren
      //----------------------------------------------------------------
      else if(state == STATE_BREAKEVEN)
      {
         double struct_trigger_pips = cfg.trade_management.structure_trigger_atr * (atr / pip_size);
         if(profit_pips >= struct_trigger_pips)
         {
            double structure_level = (direction == 1)
                                     ? FindLastHigherLow(symbol, 10)
                                     : FindLastLowerHigh(symbol, 10);

            if(structure_level > 0.0)
            {
               double dist_to_structure = direction * (current_price - structure_level) / pip_size;
               if(dist_to_structure >= struct_trigger_pips)
               {
                  if(direction == 1)
                     g_positions[idx].last_structure_low  = structure_level;
                  else
                     g_positions[idx].last_structure_high = structure_level;

                  g_positions[idx].state = STATE_TRAILING;

                  LOG_I("TradeManagement", symbol,
                        "Struktur-Trailing aktiviert | " +
                        (direction == 1 ? "HL=" : "LH=") +
                        DoubleToString(structure_level, 5));
               }
            }
         }
      }

      //----------------------------------------------------------------
      // Phase 3: Struktur-Trailing laufend nachziehen
      //----------------------------------------------------------------
      else if(state == STATE_TRAILING)
      {
         double new_structure;
         double last_structure;

         if(direction == 1)
         {
            new_structure  = FindLastHigherLow(symbol, 10);
            last_structure = g_positions[idx].last_structure_low;
         }
         else
         {
            new_structure  = FindLastLowerHigh(symbol, 10);
            last_structure = g_positions[idx].last_structure_high;
         }

         bool structure_improved = (new_structure > 0.0)
                                   && ((direction == 1) ? (new_structure > last_structure)
                                                        : (new_structure < last_structure || last_structure <= 0.0));

         if(structure_improved)
         {
            double dist_to_new = direction * (current_price - new_structure) / pip_size;
            double struct_trigger_pips = cfg.trade_management.structure_trigger_atr * (atr / pip_size);

            if(dist_to_new >= struct_trigger_pips)
            {
               double buffer  = cfg.trade_management.structure_sl_buffer_atr * atr;
               double spread  = (double)SymbolInfoInteger(symbol, SYMBOL_SPREAD)
                                * SymbolInfoDouble(symbol, SYMBOL_POINT);
               double new_sl  = (direction == 1) ? (new_structure - buffer - spread)
                                                  : (new_structure + buffer + spread);

               bool sl_improved = (direction == 1) ? (new_sl > current_sl)
                                                    : (new_sl < current_sl || current_sl <= 0.0);
               if(sl_improved)
               {
                  if(ModifySL(ticket, symbol, new_sl))
                  {
                     if(direction == 1)
                        g_positions[idx].last_structure_low  = new_structure;
                     else
                        g_positions[idx].last_structure_high = new_structure;

                     LOG_I("TradeManagement", symbol,
                           "SL nachgezogen | neues " +
                           (direction == 1 ? "HL=" : "LH=") +
                           DoubleToString(new_structure, 5) +
                           " | SL=" + DoubleToString(new_sl, 5));
                  }
               }
            }
         }
      }
   }
}

#endif // INVESTAPP_TRADEMANAGEMENT_MQH
