//+------------------------------------------------------------------+
//| TrendAnalysis.mqh – Multi-Timeframe Trend-Bias                  |
//| EMA 21/50/200 (M15) + ADX-Filter + HTF-Bestätigung (H1 EMA50)  |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_TRENDANALYSIS_MQH
#define INVESTAPP_TRENDANALYSIS_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>

//+------------------------------------------------------------------+
//| Enum + Struct                                                     |
//+------------------------------------------------------------------+
enum TREND_DIRECTION { TREND_LONG = 1, TREND_SHORT = -1, TREND_NEUTRAL = 0 };

struct TrendResult
{
   TREND_DIRECTION direction;     // übergeordneter Bias
   int             score;         // Rohscore: Summe der Einzelsignale (signed)
   int             max_score;     // maximal erreichbarer Absolutscore
   double          confidence;    // |score| / max_score (0.0–1.0)
   double          ema9;          // EMA9 aktueller Wert (Stufe 2c)
   double          ema21;         // EMA21 aktueller Wert (Einstiegs-TF)
   double          ema50;         // EMA50
   double          ema200;        // EMA200
   double          adx;           // ADX-Wert
   bool            adx_trending;  // ADX > threshold (aus config)
   string          ms_event;      // Marktstruktur-Ereignis: "BoS_Bull", "BoS_Bear", "CHoCH_Bull", "CHoCH_Bear", ""
   double          ms_bonus;      // Confidence-Bonus durch Marktstruktur (0.0, 0.10, 0.15)
   string          summary;       // z.B. "Long | EMA-Stack ✓ | ADX=28 | HTF Long"
};

//+------------------------------------------------------------------+
//| EMA berechnen (letzte abgeschlossene Kerze, shift=1)             |
//+------------------------------------------------------------------+
double GetEMA(string symbol, ENUM_TIMEFRAMES tf, int period, int shift = 1)
{
   int handle = iMA(symbol, tf, period, 0, MODE_EMA, PRICE_CLOSE);
   if(handle == INVALID_HANDLE)
   {
      LOG_E("TrendAnalysis", symbol,
            StringFormat("iMA(%d) Handle ungültig: %d", period, GetLastError()));
      return 0.0;
   }

   double buf[];
   ArraySetAsSeries(buf, true);

   if(CopyBuffer(handle, 0, shift, 1, buf) <= 0)
   {
      LOG_E("TrendAnalysis", symbol,
            StringFormat("CopyBuffer EMA(%d) fehlgeschlagen: %d", period, GetLastError()));
      IndicatorRelease(handle);
      return 0.0;
   }

   IndicatorRelease(handle);
   return buf[0];
}

//+------------------------------------------------------------------+
//| ADX berechnen (Hauptlinie, letzte abgeschlossene Kerze)          |
//+------------------------------------------------------------------+
double GetADX(string symbol, ENUM_TIMEFRAMES tf, int period, int shift = 1)
{
   int handle = iADX(symbol, tf, period);
   if(handle == INVALID_HANDLE)
   {
      LOG_E("TrendAnalysis", symbol,
            StringFormat("iADX(%d) Handle ungültig: %d", period, GetLastError()));
      return 0.0;
   }

   double buf[];
   ArraySetAsSeries(buf, true);

   // Buffer 0 = ADX Hauptlinie
   if(CopyBuffer(handle, 0, shift, 1, buf) <= 0)
   {
      LOG_E("TrendAnalysis", symbol,
            StringFormat("CopyBuffer ADX(%d) fehlgeschlagen: %d", period, GetLastError()));
      IndicatorRelease(handle);
      return 0.0;
   }

   IndicatorRelease(handle);
   return buf[0];
}

//+------------------------------------------------------------------+
//| Hauptfunktion – Trend analysieren                                |
//| Scoring (signed): Long-Signale +, Short-Signale –               |
//|   EMA-Stack M15:  vollständig ±2 | teilweise ±1                 |
//|   ADX-Filter:     ADX trending → ±1 (in Richtung EMA-Stack)     |
//|   HTF H1 EMA50:   Preis > EMA50 → +2 | Preis < EMA50 → -2      |
//|   max_score = 5                                                  |
//+------------------------------------------------------------------+
TrendResult AnalyzeTrend(string symbol, AppConfig &cfg)
{
   TrendResult res;
   res.direction    = TREND_NEUTRAL;
   res.score        = 0;
   res.max_score    = 6;   // 2 (EMA-Stack) + 1 (EMA9-Bonus) + 1 (ADX) + 2 (HTF)
   res.confidence   = 0.0;
   res.ema9         = 0.0;
   res.ema21        = 0.0;
   res.ema50        = 0.0;
   res.ema200       = 0.0;
   res.adx          = 0.0;
   res.adx_trending = false;
   res.ms_event     = "";
   res.ms_bonus     = 0.0;
   res.summary      = "Neutral";

   // --- [1] EMA-Stack auf M15 (shift=1: letzte abgeschlossene Kerze) ---
   res.ema9   = GetEMA(symbol, PERIOD_M15, 9);
   res.ema21  = GetEMA(symbol, PERIOD_M15, 21);
   res.ema50  = GetEMA(symbol, PERIOD_M15, 50);
   res.ema200 = GetEMA(symbol, PERIOD_M15, 200);

   if(res.ema21 <= 0.0 || res.ema50 <= 0.0 || res.ema200 <= 0.0)
   {
      LOG_W("TrendAnalysis", symbol, "EMA-Werte nicht verfügbar");
      return res;
   }

   int ema_score = 0;
   bool full_long  = (res.ema21 > res.ema50) && (res.ema50 > res.ema200);
   bool full_short = (res.ema21 < res.ema50) && (res.ema50 < res.ema200);

   if(full_long)
      ema_score = 2;
   else if(full_short)
      ema_score = -2;
   else
   {
      // Teilweise geordnet: 2 von 3 Bedingungen erfüllt
      int long_conds  = ((res.ema21 > res.ema50)  ? 1 : 0)
                      + ((res.ema50 > res.ema200)  ? 1 : 0);
      int short_conds = ((res.ema21 < res.ema50)  ? 1 : 0)
                      + ((res.ema50 < res.ema200)  ? 1 : 0);
      if(long_conds >= 2)       ema_score =  1;
      else if(short_conds >= 2) ema_score = -1;
   }
   res.score += ema_score;

   // --- [1b] EMA9 Stack-Bonus (Stufe 2c) ---
   // EMA9 über EMA21 → bullisch kurzfristig → +1 in Trendrichtung
   if(res.ema9 > 0.0)
   {
      if(res.ema9 > res.ema21 && ema_score > 0)  res.score += 1;
      if(res.ema9 < res.ema21 && ema_score < 0)  res.score -= 1;
   }

   // --- [2] ADX-Filter auf M15 (14 Perioden) ---
   res.adx          = GetADX(symbol, PERIOD_M15, 14);
   res.adx_trending = (res.adx > (double)cfg.filters.adx_min_threshold);

   if(res.adx_trending)
   {
      // ADX bestätigt die Trendrichtung des EMA-Stacks
      if(ema_score > 0)       res.score += 1;
      else if(ema_score < 0)  res.score -= 1;
      // Bei neutralem EMA-Stack: kein ADX-Bonus
   }

   // --- [3] Higher Timeframe Bestätigung: H1 EMA50 ---
   double price     = SymbolInfoDouble(symbol, SYMBOL_BID);
   double htf_ema50 = GetEMA(symbol, PERIOD_H1, 50);

   string htf_label = "Neutral";
   if(htf_ema50 > 0.0 && price > 0.0)
   {
      if(price > htf_ema50)
      {
         res.score += 2;
         htf_label  = "Long";
      }
      else if(price < htf_ema50)
      {
         res.score -= 2;
         htf_label  = "Short";
      }
   }

   // --- [4] Marktstruktur: BoS / CHoCH (Stufe 2c) ---
   // 30-Bar Lookback auf M15, Swing mit 2-Bar Padding
   {
      MqlRates ms_rates[];
      ArraySetAsSeries(ms_rates, true);
      if(CopyRates(symbol, PERIOD_M15, 1, 32, ms_rates) >= 30)
      {
         // Swing High/Low mit 2-Bar Padding
         double prev_swing_high = 0.0, prev_swing_low  = 0.0;
         double last_swing_high = 0.0, last_swing_low  = 0.0;

         for(int mi = 2; mi < 29; mi++)
         {
            // Swing High: höher als beide Nachbarn (2-Bar Padding)
            if(ms_rates[mi].high > ms_rates[mi-1].high &&
               ms_rates[mi].high > ms_rates[mi+1].high &&
               ms_rates[mi].high > ms_rates[mi-2].high &&
               ms_rates[mi].high > ms_rates[mi+2].high)
            {
               prev_swing_high = last_swing_high;
               last_swing_high = ms_rates[mi].high;
            }
            // Swing Low: tiefer als beide Nachbarn (2-Bar Padding)
            if(ms_rates[mi].low < ms_rates[mi-1].low &&
               ms_rates[mi].low < ms_rates[mi+1].low &&
               ms_rates[mi].low < ms_rates[mi-2].low &&
               ms_rates[mi].low < ms_rates[mi+2].low)
            {
               prev_swing_low = last_swing_low;
               last_swing_low = ms_rates[mi].low;
            }
         }

         double cur_close = ms_rates[0].close;

         // CHoCH (Change of Character) hat Priorität – zeigt Trendwechsel
         // Bullisch CHoCH: Preis bricht über letztes Swing High in Abwärtstrend
         if(ema_score <= 0 && last_swing_high > 0.0 && cur_close > last_swing_high)
         {
            res.ms_event = "CHoCH_Bull";
            res.ms_bonus = 0.15;
         }
         // Bearisch CHoCH: Preis bricht unter letztes Swing Low in Aufwärtstrend
         else if(ema_score >= 0 && last_swing_low > 0.0 && cur_close < last_swing_low)
         {
            res.ms_event = "CHoCH_Bear";
            res.ms_bonus = 0.15;
         }
         // BoS (Break of Structure) – Fortsetzung des bestehenden Trends
         // Bullisch BoS: Preis bricht über letztes Swing High in Aufwärtstrend
         else if(ema_score > 0 && last_swing_high > 0.0 && cur_close > last_swing_high)
         {
            res.ms_event = "BoS_Bull";
            res.ms_bonus = 0.10;
         }
         // Bearisch BoS: Preis bricht unter letztes Swing Low in Abwärtstrend
         else if(ema_score < 0 && last_swing_low > 0.0 && cur_close < last_swing_low)
         {
            res.ms_event = "BoS_Bear";
            res.ms_bonus = 0.10;
         }
      }
   }

   // --- Richtungsbestimmung ---
   res.confidence = (double)MathAbs(res.score) / (double)res.max_score;

   if(res.confidence < 0.4)
      res.direction = TREND_NEUTRAL;
   else if(res.score > 0)
      res.direction = TREND_LONG;
   else
      res.direction = TREND_SHORT;

   // --- Summary aufbauen ---
   string dir_str  = (res.direction == TREND_LONG)  ? "Long"
                   : (res.direction == TREND_SHORT) ? "Short"
                   :                                  "Neutral";
   string ema_mark = (MathAbs(ema_score) >= 2) ? "✓"
                   : (MathAbs(ema_score) == 1) ? "~"
                   :                             "✗";
   string adx_mark = res.adx_trending ? "✓" : "✗";

   string ms_str = (res.ms_event != "") ? " | " + res.ms_event : "";
   res.summary = StringFormat("%s | EMA-Stack %s | EMA9=%.5f | ADX=%.0f %s | HTF %s%s | Score=%d/%d | Conf=%.0f%%",
                              dir_str, ema_mark,
                              res.ema9,
                              res.adx, adx_mark,
                              htf_label, ms_str,
                              res.score, res.max_score,
                              res.confidence * 100.0);

   LOG_I("TrendAnalysis", symbol, res.summary);

   return res;
}

//+------------------------------------------------------------------+
//| Prüft ob Trend und Signal-Richtung übereinstimmen               |
//| signal_direction: 1=Long, -1=Short, 0=unbekannt (kein Filter)   |
//| Gibt false zurück wenn Trade gegen den Haupttrend laufen würde   |
//+------------------------------------------------------------------+
bool IsTrendAligned(TrendResult &trend, int signal_direction)
{
   if(signal_direction == 0)           return true;   // noch kein Signal → kein Filter
   if(trend.direction == TREND_NEUTRAL) return false;  // kein klarer Trend
   return ((int)trend.direction == signal_direction);
}

#endif // INVESTAPP_TRENDANALYSIS_MQH
