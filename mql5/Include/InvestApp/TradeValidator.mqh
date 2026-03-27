//+------------------------------------------------------------------+
//| TradeValidator.mqh – Finale Prüfung vor OrderSend               |
//| 7 Checks: Max-Trades, Duplikat, Gegenposition, Drawdown,        |
//|           Mindest-Equity, Handelserlaubnis                       |
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
};

//+------------------------------------------------------------------+
//| Hilfsfunktion: Offene Positionen zählen                         |
//| symbol="" → alle; sonst nur für dieses Symbol                   |
//+------------------------------------------------------------------+
int CountOpenTrades(string symbol = "")
{
   int count = 0;
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      if(symbol == "")
         count++;
      else if(PositionGetSymbol(i) == symbol)
         count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| Hilfsfunktion: Korrelations-Check (intern, nicht Pflicht-Check) |
//| USD-Paare / JPY-Paare: max. 2 Positionen in gleicher Gruppe     |
//+------------------------------------------------------------------+
bool CheckCorrelation(string symbol, int direction)
{
   string usd_group[] = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"};
   string jpy_group[] = {"USDJPY", "EURJPY", "GBPJPY"};

   int group_type = 0; // 0=kein Check, 1=USD, 2=JPY
   for(int i = 0; i < ArraySize(usd_group); i++)
      if(usd_group[i] == symbol) { group_type = 1; break; }
   if(group_type == 0)
      for(int i = 0; i < ArraySize(jpy_group); i++)
         if(jpy_group[i] == symbol) { group_type = 2; break; }

   if(group_type == 0) return true; // Kein Gruppen-Check für Indexes/NASDAQ

   string check_group[];
   if(group_type == 1)
   {
      ArrayResize(check_group, ArraySize(usd_group));
      for(int i = 0; i < ArraySize(usd_group); i++) check_group[i] = usd_group[i];
   }
   else
   {
      ArrayResize(check_group, ArraySize(jpy_group));
      for(int i = 0; i < ArraySize(jpy_group); i++) check_group[i] = jpy_group[i];
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
      bool same_dir = (direction ==  1 && pos_type == POSITION_TYPE_BUY) ||
                      (direction == -1 && pos_type == POSITION_TYPE_SELL);
      if(same_dir) corr_count++;
   }
   return (corr_count < 2);
}

//+------------------------------------------------------------------+
//| Hauptfunktion – Trade validieren                                 |
//| direction: 1=Long, -1=Short                                      |
//+------------------------------------------------------------------+
ValidationResult ValidateTrade(string symbol, int direction, AppConfig &cfg)
{
   ValidationResult res;
   res.isValid       = false;
   res.reject_reason = "";

   // [1] Max. offene Trades gesamt
   int total_open = CountOpenTrades();
   if(total_open >= cfg.risk.max_open_trades)
   {
      res.reject_reason = StringFormat("Max. offene Trades erreicht (%d/%d)",
                                       total_open, cfg.risk.max_open_trades);
      LOG_W("TradeValidator", symbol, res.reject_reason);
      return res;
   }

   // [2] Kein offener Trade auf gleichem Symbol + gleicher Richtung
   int sym_total = PositionsTotal();
   for(int i = 0; i < sym_total; i++)
   {
      if(PositionGetSymbol(i) != symbol) continue;
      if(!PositionSelect(symbol)) continue;
      long pos_type = PositionGetInteger(POSITION_TYPE);
      bool same_dir = (direction ==  1 && pos_type == POSITION_TYPE_BUY) ||
                      (direction == -1 && pos_type == POSITION_TYPE_SELL);
      if(same_dir)
      {
         res.reject_reason = "Bereits offene Position auf " + symbol;
         LOG_W("TradeValidator", symbol, res.reject_reason);
         return res;
      }
   }

   // [3] Keine gegenläufige Position auf gleichem Symbol
   for(int i = 0; i < sym_total; i++)
   {
      if(PositionGetSymbol(i) != symbol) continue;
      if(!PositionSelect(symbol)) continue;
      long pos_type = PositionGetInteger(POSITION_TYPE);
      bool opposite = (direction ==  1 && pos_type == POSITION_TYPE_SELL) ||
                      (direction == -1 && pos_type == POSITION_TYPE_BUY);
      if(opposite)
      {
         res.reject_reason = "Gegenläufige Position auf " + symbol + " aktiv";
         LOG_W("TradeValidator", symbol, res.reject_reason);
         return res;
      }
   }

   // [4] Daily Drawdown
   if(IsDailyDrawdownBreached(cfg))
   {
      res.reject_reason = "Tages-Drawdown-Limit erreicht";
      LOG_W("TradeValidator", symbol, res.reject_reason);
      return res;
   }

   // [5] Mindest-Kontostand
   if(AccountInfoDouble(ACCOUNT_EQUITY) < 100.0)
   {
      res.reject_reason = "Kontostand unter Minimum (< 100)";
      LOG_W("TradeValidator", symbol, res.reject_reason);
      return res;
   }

   // [6] Handelserlaubnis
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) == 0)
   {
      res.reject_reason = "Trading nicht erlaubt (Terminal)";
      LOG_W("TradeValidator", symbol, res.reject_reason);
      return res;
   }
   if(AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) == 0)
   {
      res.reject_reason = "Trading nicht erlaubt (Konto)";
      LOG_W("TradeValidator", symbol, res.reject_reason);
      return res;
   }

   // [7] Alle Checks bestanden
   res.isValid = true;
   string dir_label = (direction == 1) ? "Long" : "Short";
   LOG_I("TradeValidator", symbol,
         StringFormat("%s | ✓ Validiert | Offene Trades: %d/%d",
                      dir_label,
                      total_open + 1,
                      cfg.risk.max_open_trades));
   return res;
}

#endif // INVESTAPP_TRADEVALIDATOR_MQH
