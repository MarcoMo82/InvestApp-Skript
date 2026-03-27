//+------------------------------------------------------------------+
//| TradeValidator.mqh – Finale Plausibilitätsprüfung               |
//| Prüft Max-Trades, Duplikate, RR, Drawdown, Korrelation          |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_TRADEVALIDATOR_MQH
#define INVESTAPP_TRADEVALIDATOR_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>
#include <InvestApp/RiskManager.mqh>

//+------------------------------------------------------------------+
//| Ergebnis-Struct                                                   |
//+------------------------------------------------------------------+
struct ValidationResult
{
   bool   isValid;
   string reject_reason;
   int    open_trades_symbol;   // offene Trades auf diesem Symbol
   int    open_trades_total;    // gesamt offene Trades
   bool   duplicate_check;      // true = kein Duplikat vorhanden
   bool   rr_check;             // true = RR ausreichend (oder kein fixer TP)
   bool   drawdown_check;       // true = Drawdown ok
   bool   correlation_check;    // true = keine Überkorrelation
};

//+------------------------------------------------------------------+
//| Offene Positionen zählen                                         |
//| symbol="" → alle Positionen; sonst nur für dieses Symbol         |
//+------------------------------------------------------------------+
int CountOpenTrades(string symbol = "")
{
   int count = 0;
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      if(symbol == "")
      {
         count++;
      }
      else
      {
         if(PositionGetSymbol(i) == symbol)
            count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Prüft ob bereits eine Position in dieser Richtung offen ist     |
//| direction: 1=Long, -1=Short                                      |
//+------------------------------------------------------------------+
bool HasOpenPositionInDirection(string symbol, int direction)
{
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      if(PositionGetSymbol(i) != symbol) continue;

      if(!PositionSelect(symbol)) continue;

      long pos_type = PositionGetInteger(POSITION_TYPE);
      if(direction == 1  && pos_type == POSITION_TYPE_BUY)  return true;
      if(direction == -1 && pos_type == POSITION_TYPE_SELL) return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Korrelations-Check                                               |
//| USD-Paare: EURUSD GBPUSD AUDUSD NZDUSD                          |
//| JPY-Paare: USDJPY EURJPY GBPJPY                                 |
//| Mehr als 2 Positionen in gleicher Gruppe → false                 |
//| Indexes/NASDAQ: kein Check (zu unterschiedlich)                  |
//+------------------------------------------------------------------+
bool CheckCorrelation(string symbol, int direction)
{
   // Korrelationsgruppen definieren
   string usd_group[] = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"};
   string jpy_group[] = {"USDJPY", "EURJPY", "GBPJPY"};

   // Bestimmen ob Symbol zu einer Gruppe gehört
   int group_type = 0; // 0=kein Check, 1=USD, 2=JPY

   for(int i = 0; i < ArraySize(usd_group); i++)
      if(usd_group[i] == symbol) { group_type = 1; break; }

   if(group_type == 0)
      for(int i = 0; i < ArraySize(jpy_group); i++)
         if(jpy_group[i] == symbol) { group_type = 2; break; }

   // Kein Gruppen-Check für Indexes/NASDAQ
   if(group_type == 0) return true;

   // Zähle Positionen in der gleichen Gruppe mit gleicher Richtung
   string *group = NULL;
   int group_size = 0;

   // Für USD-Gruppe: Long auf EURUSD/GBPUSD/AUDUSD/NZDUSD bedeutet alle USD Short
   // Gleiche Richtung = korreliert
   string check_group[];
   if(group_type == 1)
   {
      ArrayResize(check_group, ArraySize(usd_group));
      for(int i = 0; i < ArraySize(usd_group); i++)
         check_group[i] = usd_group[i];
   }
   else
   {
      ArrayResize(check_group, ArraySize(jpy_group));
      for(int i = 0; i < ArraySize(jpy_group); i++)
         check_group[i] = jpy_group[i];
   }

   int corr_count = 0;
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      string pos_sym = PositionGetSymbol(i);
      bool in_group = false;
      for(int j = 0; j < ArraySize(check_group); j++)
         if(check_group[j] == pos_sym) { in_group = true; break; }

      if(!in_group) continue;

      if(!PositionSelect(pos_sym)) continue;

      long pos_type = PositionGetInteger(POSITION_TYPE);
      bool same_direction = (direction == 1  && pos_type == POSITION_TYPE_BUY) ||
                            (direction == -1 && pos_type == POSITION_TYPE_SELL);
      if(same_direction) corr_count++;
   }

   return (corr_count < 2);
}

//+------------------------------------------------------------------+
//| Hauptfunktion – Trade validieren                                 |
//+------------------------------------------------------------------+
ValidationResult ValidateTrade(string symbol, int direction, RiskResult &risk, AppConfig &cfg)
{
   ValidationResult res;
   res.isValid             = false;
   res.reject_reason       = "";
   res.open_trades_symbol  = CountOpenTrades(symbol);
   res.open_trades_total   = CountOpenTrades();
   res.duplicate_check     = true;
   res.rr_check            = true;
   res.drawdown_check      = true;
   res.correlation_check   = true;

   // [1] Max offene Trades gesamt
   if(res.open_trades_total >= cfg.risk.max_open_trades)
   {
      res.reject_reason = StringFormat("Max offene Trades erreicht (%d/%d)",
                                       res.open_trades_total, cfg.risk.max_open_trades);
      LOG_W("TradeValidator", symbol, res.reject_reason);
      return res;
   }

   // [2] Duplikat-Check
   res.duplicate_check = !HasOpenPositionInDirection(symbol, direction);
   if(!res.duplicate_check)
   {
      res.reject_reason = "Bereits Position in dieser Richtung offen";
      LOG_W("TradeValidator", symbol, res.reject_reason);
      return res;
   }

   // [3] RR-Check (nur wenn fixer TP aktiv)
   if(cfg.trade_exit.use_fixed_tp)
   {
      res.rr_check = (risk.rr_ratio >= cfg.risk.min_rr_ratio);
      if(!res.rr_check)
      {
         res.reject_reason = StringFormat("RR %.2f < Minimum %.2f",
                                          risk.rr_ratio, cfg.risk.min_rr_ratio);
         LOG_W("TradeValidator", symbol, res.reject_reason);
         return res;
      }
   }

   // [4] Drawdown-Check
   res.drawdown_check = !IsDailyDrawdownBreached(cfg);
   if(!res.drawdown_check)
   {
      res.reject_reason = "Tages-Drawdown erreicht";
      LOG_W("TradeValidator", symbol, res.reject_reason);
      return res;
   }

   // [5] Korrelations-Check
   res.correlation_check = CheckCorrelation(symbol, direction);
   if(!res.correlation_check)
   {
      res.reject_reason = "Zu viele korrelierte Positionen";
      LOG_W("TradeValidator", symbol, res.reject_reason);
      return res;
   }

   // Alle Checks bestanden
   res.isValid = true;

   double equity          = AccountInfoDouble(ACCOUNT_EQUITY);
   double drawdown_pct    = (g_dailyEquityStart > 0.0)
      ? (g_dailyEquityStart - equity) / g_dailyEquityStart * 100.0
      : 0.0;

   string dir_label = (direction == 1) ? "Long" : "Short";
   LOG_I("TradeValidator", symbol,
         StringFormat("%s | ✓ Validiert | Offene Trades: %d/%d | Drawdown: %.1f%%/%.1f%%",
                      dir_label,
                      res.open_trades_total + 1,   // inkl. geplanten Trade
                      cfg.risk.max_open_trades,
                      drawdown_pct,
                      cfg.risk.max_daily_drawdown_pct));

   return res;
}

#endif // INVESTAPP_TRADEVALIDATOR_MQH
