//+------------------------------------------------------------------+
//| TrendAnalysis.mqh – Multi-Timeframe Trend-Bias                  |
//| EMA 21/50/200 + ADX + HTF-Bias (H4/D1)                         |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_TRENDANALYSIS_MQH
#define INVESTAPP_TRENDANALYSIS_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>

//+------------------------------------------------------------------+
//| Ergebnis-Struct                                                   |
//+------------------------------------------------------------------+
struct TrendResult
{
   int    bias;           // 1=Long, -1=Short, 0=Neutral
   string bias_label;     // "Long", "Short", "Neutral"
   double ema_fast;       // EMA 21 (letzte abgeschlossene Kerze)
   double ema_mid;        // EMA 50
   double ema_slow;       // EMA 200
   bool   ema_aligned;    // alle EMAs in richtiger Reihenfolge
   double adx_value;      // ADX-Wert
   bool   trend_strong;   // ADX > Schwellenwert
   string htf_bias;       // "bullish", "bearish", "neutral" auf H4/D1
   int    score;          // 0–100 Trend-Stärke-Score
};

//+------------------------------------------------------------------+
//| EMA berechnen (letzte abgeschlossene Kerze)                      |
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
//| Higher Timeframe Bias (H4 + D1)                                  |
//| "bullish"  – EMA21 > EMA50 > EMA200 auf H4 UND D1               |
//| "bearish"  – EMA21 < EMA50 < EMA200 auf H4 UND D1               |
//| "neutral"  – gemischte Signale                                   |
//+------------------------------------------------------------------+
string GetHTFBias(string symbol)
{
   // H4
   double h4_fast = GetEMA(symbol, PERIOD_H4, 21);
   double h4_mid  = GetEMA(symbol, PERIOD_H4, 50);
   double h4_slow = GetEMA(symbol, PERIOD_H4, 200);

   // D1
   double d1_fast = GetEMA(symbol, PERIOD_D1, 21);
   double d1_mid  = GetEMA(symbol, PERIOD_D1, 50);
   double d1_slow = GetEMA(symbol, PERIOD_D1, 200);

   if(h4_fast <= 0.0 || h4_mid <= 0.0 || h4_slow <= 0.0 ||
      d1_fast <= 0.0 || d1_mid  <= 0.0 || d1_slow <= 0.0)
      return "neutral";

   bool h4_bullish = (h4_fast > h4_mid) && (h4_mid > h4_slow);
   bool h4_bearish = (h4_fast < h4_mid) && (h4_mid < h4_slow);
   bool d1_bullish = (d1_fast > d1_mid) && (d1_mid > d1_slow);
   bool d1_bearish = (d1_fast < d1_mid) && (d1_mid < d1_slow);

   if(h4_bullish && d1_bullish) return "bullish";
   if(h4_bearish && d1_bearish) return "bearish";
   return "neutral";
}

//+------------------------------------------------------------------+
//| Hauptfunktion – Trend auf M15 analysieren                        |
//+------------------------------------------------------------------+
TrendResult AnalyzeTrend(string symbol, AppConfig &cfg)
{
   TrendResult res;
   res.bias        = 0;
   res.bias_label  = "Neutral";
   res.ema_fast    = 0.0;
   res.ema_mid     = 0.0;
   res.ema_slow    = 0.0;
   res.ema_aligned = false;
   res.adx_value   = 0.0;
   res.trend_strong= false;
   res.htf_bias    = "neutral";
   res.score       = 0;

   // EMA 21 / 50 / 200 auf M15
   res.ema_fast = GetEMA(symbol, PERIOD_M15, 21);
   res.ema_mid  = GetEMA(symbol, PERIOD_M15, 50);
   res.ema_slow = GetEMA(symbol, PERIOD_M15, 200);

   if(res.ema_fast <= 0.0 || res.ema_mid <= 0.0 || res.ema_slow <= 0.0)
   {
      LOG_W("TrendAnalysis", symbol, "EMA-Werte nicht verfügbar");
      return res;
   }

   // EMA-Ausrichtung prüfen
   bool long_aligned  = (res.ema_fast > res.ema_mid) && (res.ema_mid > res.ema_slow);
   bool short_aligned = (res.ema_fast < res.ema_mid) && (res.ema_mid < res.ema_slow);
   res.ema_aligned    = long_aligned || short_aligned;

   // ADX (14 Perioden, M15)
   res.adx_value   = GetADX(symbol, PERIOD_M15, 14);
   res.trend_strong = (res.adx_value > cfg.filters.adx_min_threshold);

   // HTF Bias
   res.htf_bias = GetHTFBias(symbol);

   // Score berechnen (0–100)
   int score = 0;

   if(res.ema_aligned)
      score += 40;

   if(res.trend_strong)
      score += 30;

   // HTF stimmt mit EMA-Richtung überein
   bool htf_matches_long  = long_aligned  && (res.htf_bias == "bullish");
   bool htf_matches_short = short_aligned && (res.htf_bias == "bearish");
   if(htf_matches_long || htf_matches_short)
      score += 30;

   res.score = score;

   // Bias bestimmen
   if(score >= 60 && res.ema_fast > res.ema_slow)
   {
      res.bias       = 1;
      res.bias_label = "Long";
   }
   else if(score >= 60 && res.ema_fast < res.ema_slow)
   {
      res.bias       = -1;
      res.bias_label = "Short";
   }
   else
   {
      res.bias       = 0;
      res.bias_label = "Neutral";
   }

   // Logging
   string adx_ok = res.trend_strong ? "✓" : "✗";
   LOG_I("TrendAnalysis", symbol,
         StringFormat("Bias=%s | EMA21=%.5f %s EMA50=%.5f %s EMA200=%.5f | ADX=%.1f %s | HTF=%s | Score=%d",
                      res.bias_label,
                      res.ema_fast,
                      (res.ema_fast > res.ema_mid ? ">" : (res.ema_fast < res.ema_mid ? "<" : "=")),
                      res.ema_mid,
                      (res.ema_mid > res.ema_slow ? ">" : (res.ema_mid < res.ema_slow ? "<" : "=")),
                      res.ema_slow,
                      res.adx_value, adx_ok,
                      res.htf_bias,
                      res.score));

   return res;
}

#endif // INVESTAPP_TRENDANALYSIS_MQH
