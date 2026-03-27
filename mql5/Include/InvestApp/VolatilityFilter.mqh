//+------------------------------------------------------------------+
//| VolatilityFilter.mqh – ATR + Spread Prüfung                     |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_VOLATILITYFILTER_MQH
#define INVESTAPP_VOLATILITYFILTER_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>

//+------------------------------------------------------------------+
//| Ergebnis-Struct                                                   |
//+------------------------------------------------------------------+
struct VolatilityResult
{
   bool   isAcceptable;     // true wenn handelbar
   double atr_current;      // aktueller ATR
   double atr_avg;          // Durchschnitts-ATR (20 Perioden)
   double atr_ratio;        // atr_current / atr_avg
   double spread_pips;      // aktueller Spread in Pips
   string market_phase;     // "trending", "ranging", "high_volatility", "low_volatility"
   string reject_reason;    // Ablehnungsgrund wenn isAcceptable=false
};

//+------------------------------------------------------------------+
//| Volatilität prüfen – Hauptfunktion                               |
//+------------------------------------------------------------------+
VolatilityResult CheckVolatility(string symbol, AppConfig &cfg)
{
   VolatilityResult res;
   res.isAcceptable  = false;
   res.atr_current   = 0.0;
   res.atr_avg       = 0.0;
   res.atr_ratio     = 0.0;
   res.spread_pips   = 0.0;
   res.market_phase  = "";
   res.reject_reason = "";

   // ATR-Handle (14 Perioden, 15m TF)
   int handle = iATR(symbol, PERIOD_M15, 14);
   if(handle == INVALID_HANDLE)
   {
      res.reject_reason = "iATR Handle ungültig";
      LOG_W("VolatilityFilter", symbol, res.reject_reason);
      return res;
   }

   // Letzte 21 ATR-Werte holen (shift=1: abgeschlossene Kerzen)
   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, 1, 21, buf) < 21)
   {
      res.reject_reason = "Nicht genug ATR-Daten: " + (string)GetLastError();
      LOG_W("VolatilityFilter", symbol, res.reject_reason);
      IndicatorRelease(handle);
      return res;
   }
   IndicatorRelease(handle);

   // Aktueller ATR = neueste abgeschlossene Kerze (Index 0 nach SetAsSeries)
   res.atr_current = buf[0];

   // Durchschnitts-ATR der letzten 20 Werte (Index 1–20)
   double sum = 0.0;
   for(int i = 1; i <= 20; i++)
      sum += buf[i];
   res.atr_avg = sum / 20.0;

   if(res.atr_avg <= 0.0)
   {
      res.reject_reason = "ATR-Durchschnitt = 0";
      LOG_W("VolatilityFilter", symbol, res.reject_reason);
      return res;
   }

   res.atr_ratio = res.atr_current / res.atr_avg;

   // Spread berechnen
   double point     = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int    digits    = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   double pip_size  = (digits >= 3) ? point * 10.0 : point;
   long   spread_pt = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   res.spread_pips  = (spread_pt * point) / pip_size;

   // Market Phase bestimmen
   bool phase_ok = true;

   if(res.atr_ratio > cfg.filters.max_atr_multiplier)
   {
      res.market_phase  = "high_volatility";
      res.reject_reason = StringFormat("ATR-Ratio %.2f > Max %.2f (high_volatility)",
                                       res.atr_ratio, cfg.filters.max_atr_multiplier);
      phase_ok = false;
   }
   else if(res.atr_ratio < cfg.filters.min_atr_multiplier)
   {
      res.market_phase  = "low_volatility";
      res.reject_reason = StringFormat("ATR-Ratio %.2f < Min %.2f (low_volatility)",
                                       res.atr_ratio, cfg.filters.min_atr_multiplier);
      phase_ok = false;
   }
   else if(res.atr_ratio <= 1.5)
      res.market_phase = "ranging";
   else
      res.market_phase = "trending";

   // Spread prüfen
   bool spread_ok = true;
   if(res.spread_pips > cfg.filters.max_spread_pips)
   {
      string spread_reason = StringFormat("Spread %.1f Pips > Max %.1f Pips",
                                          res.spread_pips, cfg.filters.max_spread_pips);
      if(res.reject_reason == "")
         res.reject_reason = spread_reason;
      else
         res.reject_reason += " | " + spread_reason;
      spread_ok = false;
   }

   res.isAcceptable = (phase_ok && spread_ok);

   // Logging
   string status_sym = res.isAcceptable ? "✓" : "✗";
   string log_msg = StringFormat(
      "ATR=%.5f | Ratio=%.2f | Spread=%.1f Pips | Phase=%s | %s",
      res.atr_current, res.atr_ratio, res.spread_pips, res.market_phase, status_sym);

   if(res.isAcceptable)
      LOG_I("VolatilityFilter", symbol, log_msg);
   else
      LOG_W("VolatilityFilter", symbol, log_msg + " | " + res.reject_reason);

   return res;
}

//+------------------------------------------------------------------+
//| Prüfen ob eine aktive Handelssession läuft (UTC-Zeit)            |
//+------------------------------------------------------------------+
bool IsSessionActive(AppConfig &cfg)
{
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);
   int hour = dt.hour;

   // London:   08:00–17:00 UTC
   bool london   = (hour >= 8  && hour < 17);
   // New York:  13:00–22:00 UTC
   bool new_york = (hour >= 13 && hour < 22);
   // Asian:     00:00–08:00 UTC
   bool asian    = (hour >= 0  && hour < 8);

   if(cfg.session.trade_london   && london)   return true;
   if(cfg.session.trade_new_york && new_york) return true;
   if(cfg.session.trade_asian    && asian)    return true;

   return false;
}

#endif // INVESTAPP_VOLATILITYFILTER_MQH
