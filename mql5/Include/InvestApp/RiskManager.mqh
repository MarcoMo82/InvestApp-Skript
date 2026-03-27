//+------------------------------------------------------------------+
//| RiskManager.mqh – Lotgröße, SL und TP Berechnung                |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_RISKMANAGER_MQH
#define INVESTAPP_RISKMANAGER_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>

//+------------------------------------------------------------------+
//| Ergebnis-Struct                                                   |
//+------------------------------------------------------------------+
struct RiskResult
{
   bool   isValid;          // false wenn kein Trade möglich
   double lots;             // normierte Lotgröße
   double sl_price;         // absoluter SL-Preis
   double tp_price;         // absoluter TP-Preis (0 wenn kein fixer TP)
   double sl_pips;          // SL in Pips (für Logging)
   double tp_pips;          // TP in Pips (0 wenn kein fixer TP)
   double rr_ratio;         // CRV
   double atr_value;        // ATR zum Zeitpunkt der Berechnung
   string reject_reason;    // Ablehnungsgrund wenn isValid=false
};

//--- Globale Variable für Tages-Startkapital
double g_dailyEquityStart = 0.0;

//+------------------------------------------------------------------+
//| Pip-Größe für Symbol ermitteln                                   |
//+------------------------------------------------------------------+
double GetPipSize(string symbol)
{
   double point  = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int    digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

   // Forex 5-stellig (z.B. EURUSD: digits=5) und 3-stellig (JPY: digits=3):
   // Pip = Point * 10
   // Indexes mit 1–2 Nachkommastellen (digits<=2): Pip = Point
   if(digits >= 3)
      return point * 10.0;

   return point;
}

//+------------------------------------------------------------------+
//| ATR berechnen (letzte abgeschlossene Kerze)                      |
//+------------------------------------------------------------------+
double GetATR(string symbol, ENUM_TIMEFRAMES tf, int period, int shift = 1)
{
   int handle = iATR(symbol, tf, period);
   if(handle == INVALID_HANDLE)
   {
      LOG_E("RiskManager", symbol, "iATR Handle ungültig");
      return 0.0;
   }

   double buf[];
   ArraySetAsSeries(buf, true);

   if(CopyBuffer(handle, 0, shift, 1, buf) <= 0)
   {
      LOG_E("RiskManager", symbol, "CopyBuffer für ATR fehlgeschlagen: " + (string)GetLastError());
      IndicatorRelease(handle);
      return 0.0;
   }

   IndicatorRelease(handle);
   return buf[0];
}

//+------------------------------------------------------------------+
//| Risiko berechnen – Hauptfunktion                                 |
//| direction: 1=Long, -1=Short                                      |
//+------------------------------------------------------------------+
RiskResult CalculateRisk(string symbol, int direction, double entry_price, AppConfig &cfg)
{
   RiskResult res;
   res.isValid       = false;
   res.lots          = 0.0;
   res.sl_price      = 0.0;
   res.tp_price      = 0.0;
   res.sl_pips       = 0.0;
   res.tp_pips       = 0.0;
   res.rr_ratio      = 0.0;
   res.atr_value     = 0.0;
   res.reject_reason = "";

   // ATR berechnen (14 Perioden, aktueller Chart-Timeframe)
   double atr = GetATR(symbol, PERIOD_CURRENT, 14, 1);
   if(atr <= 0.0)
   {
      res.reject_reason = "ATR nicht verfügbar";
      return res;
   }
   res.atr_value = atr;

   double pip_size = GetPipSize(symbol);
   if(pip_size <= 0.0)
   {
      res.reject_reason = "Pip-Größe nicht ermittelbar";
      return res;
   }

   // SL-Abstand in Preis
   double sl_distance = atr * cfg.entry.sl_atr_multiplier;

   // Absoluter SL-Preis
   if(direction == 1)        // Long
      res.sl_price = entry_price - sl_distance;
   else                      // Short
      res.sl_price = entry_price + sl_distance;

   // SL in Pips
   res.sl_pips = sl_distance / pip_size;
   if(res.sl_pips <= 0.0)
   {
      res.reject_reason = "SL-Pips <= 0";
      return res;
   }

   // Pip-Wert pro Lot berechnen
   double tick_value = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_size  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_size <= 0.0 || tick_value <= 0.0)
   {
      res.reject_reason = "Tick-Wert nicht verfügbar";
      return res;
   }
   double pip_value_per_lot = (tick_value / tick_size) * pip_size;

   // Lotgröße berechnen
   double balance     = AccountInfoDouble(ACCOUNT_BALANCE);
   double risk_amount = balance * cfg.risk.risk_per_trade_pct / 100.0;
   double lots_raw    = risk_amount / (res.sl_pips * pip_value_per_lot);

   // Lotgröße normieren
   double vol_min  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double vol_max  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double vol_step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(vol_step <= 0.0) vol_step = 0.01;

   double lots_norm = MathFloor(lots_raw / vol_step) * vol_step;
   lots_norm = MathMax(vol_min, MathMin(vol_max, lots_norm));
   lots_norm = NormalizeDouble(lots_norm, 2);

   // Max-Lots-Grenze
   if(lots_norm > 2.0)
   {
      LOG_W("RiskManager", symbol,
            StringFormat("Lots %.2f > 2.0 – wird auf 2.0 gekappt", lots_norm));
      lots_norm = 2.0;
   }

   if(lots_norm < vol_min)
   {
      res.reject_reason = StringFormat("Lotgröße %.4f < Minimum %.4f", lots_norm, vol_min);
      return res;
   }
   res.lots = lots_norm;

   // TP berechnen
   if(cfg.trade_exit.use_fixed_tp)
   {
      double tp_distance = res.sl_pips * cfg.entry.tp_rr_ratio * pip_size;
      res.tp_pips        = res.sl_pips * cfg.entry.tp_rr_ratio;
      res.rr_ratio       = cfg.entry.tp_rr_ratio;

      if(direction == 1)
         res.tp_price = entry_price + tp_distance;
      else
         res.tp_price = entry_price - tp_distance;

      // CRV prüfen
      if(res.rr_ratio < cfg.risk.min_rr_ratio)
      {
         res.reject_reason = StringFormat("CRV %.2f < Minimum %.2f",
                                          res.rr_ratio, cfg.risk.min_rr_ratio);
         return res;
      }
   }
   else
   {
      res.tp_price = 0.0;
      res.tp_pips  = 0.0;
      res.rr_ratio = 0.0;
   }

   res.isValid = true;

   // Logging
   string tp_info = (cfg.trade_exit.use_fixed_tp)
      ? StringFormat("%.4f (%.1f Pips)", res.tp_price, res.tp_pips)
      : "0 (kein fixer TP)";

   LOG_I("RiskManager", symbol,
         StringFormat("Lots=%.2f | SL=%.5f (%.1f Pips) | TP=%s | ATR=%.5f",
                      res.lots, res.sl_price, res.sl_pips, tp_info, res.atr_value));

   return res;
}

//+------------------------------------------------------------------+
//| Prüfen ob maximale offene Trades erreicht                        |
//+------------------------------------------------------------------+
bool IsMaxTradesReached(string symbol, AppConfig &cfg)
{
   int count = 0;
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      string pos_symbol = PositionGetSymbol(i);
      if(pos_symbol == symbol)
         count++;
   }
   return (count >= cfg.risk.max_open_trades);
}

//+------------------------------------------------------------------+
//| Prüfen ob täglicher Drawdown überschritten                       |
//+------------------------------------------------------------------+
bool IsDailyDrawdownBreached(AppConfig &cfg)
{
   if(g_dailyEquityStart <= 0.0)
      return false;

   double equity   = AccountInfoDouble(ACCOUNT_EQUITY);
   double drawdown = (g_dailyEquityStart - equity) / g_dailyEquityStart * 100.0;

   if(drawdown > cfg.risk.max_daily_drawdown_pct)
   {
      LOG_W("RiskManager", "-",
            StringFormat("Tages-Drawdown %.2f%% > Limit %.2f%%",
                         drawdown, cfg.risk.max_daily_drawdown_pct));
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Tages-Equity-Peak speichern (in OnInit + täglich um Mitternacht) |
//+------------------------------------------------------------------+
void UpdateDailyEquityPeak()
{
   g_dailyEquityStart = AccountInfoDouble(ACCOUNT_EQUITY);
   LOG_I("RiskManager", "-",
         StringFormat("Tages-Equity-Start gesetzt: %.2f", g_dailyEquityStart));
}

#endif // INVESTAPP_RISKMANAGER_MQH
