//+------------------------------------------------------------------+
//| SessionManager.mqh – Handelszeiten, Rollover, Smart-TP          |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_SESSIONMANAGER_MQH
#define INVESTAPP_SESSIONMANAGER_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>
#include <InvestApp/RiskManager.mqh>

//+------------------------------------------------------------------+
//| Enums + Structs                                                   |
//+------------------------------------------------------------------+
enum TRADE_STATE
{
   STATE_INITIAL   = 0,   // Entry-SL aktiv
   STATE_BREAKEVEN = 1,   // SL auf Breakeven+
   STATE_TRAILING  = 2    // Struktur-Trailing aktiv
};

struct PositionState
{
   ulong        ticket;
   TRADE_STATE  state;
   double       entry_price;
   double       atr_at_entry;
   double       last_structure_low;   // für Long: letztes Higher Low
   double       last_structure_high;  // für Short: letztes Lower High
   datetime     entry_time;
};

//--- Globales Array aller bekannten Positionen
PositionState g_positions[100];
int           g_position_count = 0;

//+------------------------------------------------------------------+
//| Neue Position registrieren                                        |
//+------------------------------------------------------------------+
void RegisterPosition(ulong ticket, double entry_price, double atr_value)
{
   // Doppelt-Registrierung verhindern
   for(int i = 0; i < g_position_count; i++)
   {
      if(g_positions[i].ticket == ticket)
         return;
   }

   if(g_position_count >= 100)
   {
      LOG_W("SessionManager", "-", "RegisterPosition: Array voll (100 Positionen)");
      return;
   }

   PositionState ps;
   ps.ticket               = ticket;
   ps.state                = STATE_INITIAL;
   ps.entry_price          = entry_price;
   ps.atr_at_entry         = atr_value;
   ps.last_structure_low   = 0.0;
   ps.last_structure_high  = 0.0;
   ps.entry_time           = TimeCurrent();

   g_positions[g_position_count] = ps;
   g_position_count++;

   LOG_I("SessionManager", "-", StringFormat("Position registriert | Ticket=%I64u | Entry=%.5f | ATR=%.5f",
         ticket, entry_price, atr_value));
}

//+------------------------------------------------------------------+
//| Index in g_positions suchen; -1 wenn nicht gefunden             |
//+------------------------------------------------------------------+
int FindPositionState(ulong ticket)
{
   for(int i = 0; i < g_position_count; i++)
   {
      if(g_positions[i].ticket == ticket)
         return i;
   }
   return -1;
}

//+------------------------------------------------------------------+
//| Geschlossene Positionen aus dem Array entfernen                  |
//+------------------------------------------------------------------+
void CleanupClosedPositions()
{
   for(int i = g_position_count - 1; i >= 0; i--)
   {
      if(!PositionSelectByTicket(g_positions[i].ticket))
      {
         // Position nicht mehr offen – aus Array entfernen
         LOG_D("SessionManager", "-", StringFormat("Position entfernt | Ticket=%I64u", g_positions[i].ticket));

         // Letztes Element an diese Stelle verschieben
         if(i < g_position_count - 1)
            g_positions[i] = g_positions[g_position_count - 1];
         g_position_count--;
      }
   }
}

//+------------------------------------------------------------------+
//| Rollover-Schließfenster prüfen                                   |
//| Gibt true wenn aktuelle UTC-Zeit im Fenster liegt:               |
//| [rollover_time - close_before_rollover_minutes, rollover_time+5] |
//+------------------------------------------------------------------+
bool IsRolloverWindow(AppConfig &cfg)
{
   string time_str = cfg.trade_exit.rollover_time_utc;
   int colon = StringFind(time_str, ":");
   if(colon < 0) return false;

   int rollover_hour = (int)StringToInteger(StringSubstr(time_str, 0, colon));
   int rollover_min  = (int)StringToInteger(StringSubstr(time_str, colon + 1));

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int current_min_of_day  = dt.hour * 60 + dt.min;
   int rollover_min_of_day = rollover_hour * 60 + rollover_min;

   // diff = Minuten seit Rollover-Zeitpunkt (negativ = noch davor)
   int diff = current_min_of_day - rollover_min_of_day;
   if(diff < -(24 * 60 / 2)) diff += 24 * 60;
   if(diff >  (24 * 60 / 2)) diff -= 24 * 60;

   return (diff >= -cfg.trade_exit.close_before_rollover_minutes && diff <= 5);
}

//+------------------------------------------------------------------+
//| Hilfsfunktion: Minuten bis Rollover (negativ = schon vorbei)     |
//+------------------------------------------------------------------+
int _MinutesUntilRollover(AppConfig &cfg)
{
   string time_str = cfg.trade_exit.rollover_time_utc;
   int colon = StringFind(time_str, ":");
   if(colon < 0) return 9999;

   int rollover_hour = (int)StringToInteger(StringSubstr(time_str, 0, colon));
   int rollover_min  = (int)StringToInteger(StringSubstr(time_str, colon + 1));

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int current_min_of_day  = dt.hour * 60 + dt.min;
   int rollover_min_of_day = rollover_hour * 60 + rollover_min;

   int mins_until = rollover_min_of_day - current_min_of_day;
   if(mins_until < 0) mins_until += 24 * 60;
   return mins_until;
}

//+------------------------------------------------------------------+
//| Alle Positionen eines Symbols zum Rollover schließen             |
//+------------------------------------------------------------------+
void CloseAllPositionsForRollover(string symbol, AppConfig &cfg)
{
   if(!cfg.trade_exit.close_before_rollover_enabled) return;

   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != symbol) continue;

      double profit = PositionGetDouble(POSITION_PROFIT);
      if(cfg.trade_exit.close_only_if_profitable && profit <= 0.0)
         continue;

      ENUM_POSITION_TYPE pos_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double price  = (pos_type == POSITION_TYPE_BUY)
                      ? SymbolInfoDouble(symbol, SYMBOL_BID)
                      : SymbolInfoDouble(symbol, SYMBOL_ASK);

      MqlTradeRequest req = {};
      MqlTradeResult  res = {};
      req.action       = TRADE_ACTION_DEAL;
      req.position     = ticket;
      req.symbol       = symbol;
      req.volume       = volume;
      req.type         = (pos_type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      req.price        = price;
      req.deviation    = 20;
      req.type_filling = ORDER_FILLING_IOC;

      bool ok = OrderSend(req, res);
      if(ok && (res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_PLACED))
      {
         LOG_I("SessionManager", symbol,
               StringFormat("Rollover-Close | Profit=%.2f USD", profit));
      }
      else
      {
         LOG_W("SessionManager", symbol,
               StringFormat("Rollover-Close fehlgeschlagen | retcode=%d", res.retcode));
      }
   }
}

//+------------------------------------------------------------------+
//| Dynamischen TP vor Rollover setzen                               |
//| direction: 1=Long, -1=Short                                      |
//+------------------------------------------------------------------+
bool SetSmartTP(ulong ticket, string symbol, int direction, AppConfig &cfg)
{
   if(!cfg.smart_tp.enabled) return false;
   if(!PositionSelectByTicket(ticket)) return false;

   int    lookback = cfg.smart_tp.range_candles_lookback;
   double pip_size = GetPipSize(symbol);
   double buffer   = cfg.smart_tp.range_buffer_pips * pip_size;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(symbol, PERIOD_M5, 1, lookback, rates) < lookback)
   {
      LOG_W("SessionManager", symbol, "SetSmartTP: CopyRates fehlgeschlagen");
      return false;
   }

   double range_high = rates[0].high;
   double range_low  = rates[0].low;
   for(int i = 1; i < lookback; i++)
   {
      if(rates[i].high > range_high) range_high = rates[i].high;
      if(rates[i].low  < range_low)  range_low  = rates[i].low;
   }

   double current_price = PositionGetDouble(POSITION_PRICE_CURRENT);
   double current_sl    = PositionGetDouble(POSITION_SL);
   double current_tp    = PositionGetDouble(POSITION_TP);

   double new_tp;
   if(direction == 1)
      new_tp = range_high - buffer;   // Long: knapp unter Range-High
   else
      new_tp = range_low  + buffer;   // Short: knapp über Range-Low

   // Nur setzen wenn TP sinnvoll (in Profitrichtung und besser als bestehender TP)
   bool tp_valid;
   if(direction == 1)
      tp_valid = (new_tp > current_price) && (current_tp <= 0.0 || new_tp < current_tp);
   else
      tp_valid = (new_tp < current_price) && (current_tp <= 0.0 || new_tp > current_tp);

   if(!tp_valid)
   {
      LOG_D("SessionManager", symbol, StringFormat("SetSmartTP: TP nicht sinnvoll | new_tp=%.5f | current=%.5f",
            new_tp, current_price));
      return false;
   }

   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   new_tp = NormalizeDouble(new_tp, digits);

   MqlTradeRequest req = {};
   MqlTradeResult  res = {};
   req.action   = TRADE_ACTION_SLTP;
   req.position = ticket;
   req.symbol   = symbol;
   req.sl       = current_sl;
   req.tp       = new_tp;

   bool ok = OrderSend(req, res);
   if(!ok || (res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_PLACED))
   {
      LOG_W("SessionManager", symbol,
            StringFormat("SetSmartTP: OrderSend fehlgeschlagen | retcode=%d", res.retcode));
      return false;
   }

   LOG_I("SessionManager", symbol,
         StringFormat("Smart-TP gesetzt auf %.5f (Range-%s=%.5f)",
                      new_tp,
                      direction == 1 ? "High" : "Low",
                      direction == 1 ? range_high : range_low));
   return true;
}

//+------------------------------------------------------------------+
//| Rollover-Management – aufrufen in OnTimer() alle 60s            |
//+------------------------------------------------------------------+
void ManageRollover(string &symbols[], int count, AppConfig &cfg)
{
   if(!cfg.trade_exit.close_before_rollover_enabled) return;

   int mins_until = _MinutesUntilRollover(cfg);

   // Schritt 1: Smart-TP setzen (activate_minutes_before_rollover vor Rollover)
   if(cfg.smart_tp.enabled
      && mins_until <= cfg.smart_tp.activate_minutes_before_rollover
      && mins_until >  cfg.trade_exit.close_before_rollover_minutes)
   {
      int pos_total = PositionsTotal();
      for(int p = 0; p < pos_total; p++)
      {
         ulong ticket = PositionGetTicket(p);
         if(!PositionSelectByTicket(ticket)) continue;

         string pos_sym = PositionGetString(POSITION_SYMBOL);
         for(int s = 0; s < count; s++)
         {
            if(symbols[s] == pos_sym)
            {
               int direction = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
               SetSmartTP(ticket, pos_sym, direction, cfg);
               break;
            }
         }
      }
   }

   // Schritt 2: Positionen schließen wenn im Schließfenster
   if(IsRolloverWindow(cfg))
   {
      for(int s = 0; s < count; s++)
         CloseAllPositionsForRollover(symbols[s], cfg);
   }
}

#endif // INVESTAPP_SESSIONMANAGER_MQH
