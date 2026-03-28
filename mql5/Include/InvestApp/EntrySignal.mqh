//+------------------------------------------------------------------+
//| EntrySignal.mqh – Candlestick + Indikator Signale               |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_ENTRYSIGNAL_MQH
#define INVESTAPP_ENTRYSIGNAL_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>
#include <InvestApp/TrendAnalysis.mqh>
#include <InvestApp/LevelDetection.mqh>

//+------------------------------------------------------------------+
//| Enums + Struct                                                    |
//+------------------------------------------------------------------+
enum SIGNAL_TYPE { SIGNAL_NONE = 0, SIGNAL_LONG = 1, SIGNAL_SHORT = -1 };
enum ENTRY_TYPE  { ENTRY_NONE = 0, ENTRY_PIN_BAR = 1, ENTRY_ENGULFING = 2,
                   ENTRY_RSI_DIVERGENCE = 3, ENTRY_MACD_CROSS = 4, ENTRY_EMA_TOUCH = 5,
                   ENTRY_BREAKOUT = 6, ENTRY_PULLBACK = 7 };

struct SignalResult
{
   SIGNAL_TYPE signal;
   ENTRY_TYPE  entry_type;
   double      confidence;    // 0.0–1.0
   double      entry_price;   // vorgeschlagener Entry (Ask/Bid)
   string      summary;       // z.B. "Long | PinBar | RSI=32 | Conf=0.78"
   int         score;
   int         max_score;
};

//+------------------------------------------------------------------+
//| Hilfsfunktion: Kerzen-Daten holen                                |
//+------------------------------------------------------------------+
bool _GetCandles(string symbol, ENUM_TIMEFRAMES tf, int count, MqlRates &rates[])
{
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, tf, 0, count + 2, rates);
   return (copied >= count + 1);
}

//+------------------------------------------------------------------+
//| Pin-Bar erkennen (shift=1: letzte abgeschlossene Kerze)          |
//| direction: 1=Long Pin Bar, -1=Short Pin Bar                      |
//+------------------------------------------------------------------+
bool IsPinBar(string symbol, int direction, int shift = 1)
{
   MqlRates rates[];
   if(!_GetCandles(symbol, PERIOD_M15, shift + 1, rates)) return false;

   double open  = rates[shift].open;
   double high  = rates[shift].high;
   double low   = rates[shift].low;
   double close = rates[shift].close;

   double range = high - low;
   if(range <= 0.0) return false;

   double body      = MathAbs(close - open);
   double upper_wick = high - MathMax(open, close);
   double lower_wick = MathMin(open, close) - low;

   if(direction == 1)
   {
      // Long Pin Bar: langer unterer Docht, kleiner oberer Docht,
      // Schlusskurs im oberen Drittel der Range
      if(body <= 0.0) return false;
      bool long_lower  = (lower_wick >= 2.0 * body);
      bool small_upper = (upper_wick <= 0.3 * range);
      bool close_high  = (close >= low + range * 2.0 / 3.0);
      return (long_lower && small_upper && close_high);
   }
   else if(direction == -1)
   {
      // Short Pin Bar: langer oberer Docht, kleiner unterer Docht,
      // Schlusskurs im unteren Drittel der Range
      if(body <= 0.0) return false;
      bool long_upper  = (upper_wick >= 2.0 * body);
      bool small_lower = (lower_wick <= 0.3 * range);
      bool close_low   = (close <= low + range * 1.0 / 3.0);
      return (long_upper && small_lower && close_low);
   }

   return false;
}

//+------------------------------------------------------------------+
//| Engulfing-Muster erkennen (shift=1: letzte abgeschlossene Kerze) |
//+------------------------------------------------------------------+
bool IsEngulfing(string symbol, int direction, int shift = 1)
{
   MqlRates rates[];
   if(!_GetCandles(symbol, PERIOD_M15, shift + 2, rates)) return false;

   double cur_open  = rates[shift].open;
   double cur_close = rates[shift].close;
   double prev_open  = rates[shift + 1].open;
   double prev_close = rates[shift + 1].close;

   double cur_body_high  = MathMax(cur_open,  cur_close);
   double cur_body_low   = MathMin(cur_open,  cur_close);
   double prev_body_high = MathMax(prev_open, prev_close);
   double prev_body_low  = MathMin(prev_open, prev_close);

   if(direction == 1)
   {
      // Long: aktuelle Kerze bullisch UND Körper umschließt vorherige Kerze
      bool cur_bullish = (cur_close > cur_open);
      bool engulfs     = (cur_body_high > prev_body_high && cur_body_low < prev_body_low);
      return (cur_bullish && engulfs);
   }
   else if(direction == -1)
   {
      // Short: aktuelle Kerze bearisch UND Körper umschließt vorherige Kerze
      bool cur_bearish = (cur_close < cur_open);
      bool engulfs     = (cur_body_high > prev_body_high && cur_body_low < prev_body_low);
      return (cur_bearish && engulfs);
   }

   return false;
}

//+------------------------------------------------------------------+
//| RSI-Wert holen                                                   |
//+------------------------------------------------------------------+
double _GetRSI(string symbol, int period, int shift)
{
   int handle = iRSI(symbol, PERIOD_M15, period, PRICE_CLOSE);
   if(handle == INVALID_HANDLE) return -1.0;

   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, shift, 1, buf) <= 0)
   {
      IndicatorRelease(handle);
      return -1.0;
   }
   IndicatorRelease(handle);
   return buf[0];
}

//+------------------------------------------------------------------+
//| MACD-Werte holen (Main + Signal)                                 |
//| buf_idx: 0=MACD-Linie, 1=Signal-Linie                           |
//+------------------------------------------------------------------+
bool _GetMACD(string symbol, int shift, double &macd_val, double &signal_val)
{
   int handle = iMACD(symbol, PERIOD_M15, 12, 26, 9, PRICE_CLOSE);
   if(handle == INVALID_HANDLE) return false;

   double macd_buf[], sig_buf[];
   ArraySetAsSeries(macd_buf, true);
   ArraySetAsSeries(sig_buf, true);

   bool ok = (CopyBuffer(handle, 0, shift, 1, macd_buf) > 0 &&
              CopyBuffer(handle, 1, shift, 1, sig_buf)  > 0);
   IndicatorRelease(handle);

   if(!ok) return false;
   macd_val   = macd_buf[0];
   signal_val = sig_buf[0];
   return true;
}

//+------------------------------------------------------------------+
//| ATR-Hilfsfunktion (lokal, um RiskManager-Abhängigkeit zu        |
//| vermeiden)                                                       |
//+------------------------------------------------------------------+
double _GetATRLocal(string symbol, ENUM_TIMEFRAMES tf, int period, int shift = 1)
{
   int handle = iATR(symbol, tf, period);
   if(handle == INVALID_HANDLE) return 0.0;
   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, shift, 1, buf) <= 0)
   {
      IndicatorRelease(handle);
      return 0.0;
   }
   IndicatorRelease(handle);
   return buf[0];
}

//+------------------------------------------------------------------+
//| EMA-Touch prüfen: Preis berührt EMA21 in letzten 2 Kerzen       |
//+------------------------------------------------------------------+
bool _IsEMATouch(string symbol, int direction)
{
   double ema1 = GetEMA(symbol, PERIOD_M15, 21, 1);
   double ema2 = GetEMA(symbol, PERIOD_M15, 21, 2);
   if(ema1 <= 0.0 || ema2 <= 0.0) return false;

   MqlRates rates[];
   if(!_GetCandles(symbol, PERIOD_M15, 3, rates)) return false;

   if(direction == 1)
   {
      // Preis berührt EMA21 von oben (Low nahe/unter EMA) und dreht nach oben
      bool touch1 = (rates[1].low <= ema1 * 1.001 && rates[1].close > ema1);
      bool touch2 = (rates[2].low <= ema2 * 1.001 && rates[2].close > ema2);
      return (touch1 || touch2);
   }
   else if(direction == -1)
   {
      // Preis berührt EMA21 von unten und dreht nach unten
      bool touch1 = (rates[1].high >= ema1 * 0.999 && rates[1].close < ema1);
      bool touch2 = (rates[2].high >= ema2 * 0.999 && rates[2].close < ema2);
      return (touch1 || touch2);
   }
   return false;
}

//+------------------------------------------------------------------+
//| Hauptfunktion: Signal berechnen                                  |
//+------------------------------------------------------------------+
SignalResult GetSignal(string symbol, TrendResult &trend, SymbolZones &zones, AppConfig &cfg)
{
   SignalResult result;
   result.signal      = SIGNAL_NONE;
   result.entry_type  = ENTRY_NONE;
   result.confidence  = 0.0;
   result.entry_price = 0.0;
   result.summary     = "None";
   result.score       = 0;
   result.max_score   = 11;  // 2(RSI) + 1(MACD) + 3(PinBar) + 2(Engulfing) + 1(EMA) + 2(Trend) + 2(Level) = 13 max,
                             // minus Level-Abzug möglich; normalisiert auf 11

   // Richtungskandidat aus Trend ableiten (wird im Scoring verfeinert)
   int direction = (int)trend.direction;
   if(direction == 0)
   {
      result.summary = "None | Kein klarer Trend";
      return result;
   }

   int score = 0;

   // Punkte-Tracker für Entry-Typ-Bestimmung
   int rsi_pts   = 0;
   int macd_pts  = 0;
   int pin_pts   = 0;
   int eng_pts   = 0;
   int ema_pts   = 0;

   // --- [1] RSI-Check (14 Perioden, M15) ---
   double rsi = _GetRSI(symbol, 14, 1);
   string rsi_str = (rsi >= 0.0) ? DoubleToString(rsi, 1) : "n/a";

   if(rsi >= 0.0)
   {
      if(direction == 1 && rsi < (double)cfg.filters.rsi_oversold)
      {
         score   += 2;
         rsi_pts  = 2;
      }
      else if(direction == -1 && rsi > (double)cfg.filters.rsi_overbought)
      {
         score   += 2;
         rsi_pts  = 2;
      }
   }

   // --- [2] MACD-Check (12/26/9, M15) ---
   double macd_cur = 0.0, sig_cur = 0.0;
   double macd_prev = 0.0, sig_prev = 0.0;
   bool macd_ok_cur  = _GetMACD(symbol, 1, macd_cur,  sig_cur);
   bool macd_ok_prev = _GetMACD(symbol, 2, macd_prev, sig_prev);

   if(macd_ok_cur && macd_ok_prev)
   {
      bool cross_up   = (macd_prev <= sig_prev && macd_cur  > sig_cur);
      bool cross_down = (macd_prev >= sig_prev && macd_cur  < sig_cur);

      if(direction == 1 && cross_up)  { score += 1; macd_pts = 1; }
      if(direction == -1 && cross_down) { score += 1; macd_pts = 1; }
   }

   // --- [3] Candlestick-Muster ---
   if(IsPinBar(symbol, direction))      { score += 3; pin_pts = 3; }
   if(IsEngulfing(symbol, direction))   { score += 2; eng_pts = 2; }

   // --- [4] EMA-Touch ---
   if(_IsEMATouch(symbol, direction))   { score += 1; ema_pts = 1; }

   // --- [5] Trend-Alignment ---
   if((int)trend.direction == direction)
   {
      score += 2;
   }
   else
   {
      // Gegenläufig zum Trend → Signal verwerfen
      result.summary = "None | Gegen Trend";
      return result;
   }

   // --- [6] Level-Nähe ---
   bool near_level = false;
   if(zones.isValid || zones.resistance_count > 0 || zones.support_count > 0)
   {
      near_level = IsNearLevel(symbol, zones, direction, 5.0, 50.0);
      if(near_level)
         score += 2;
      else
         score -= 1;
   }

   // --- [7] Breakout-Entry Erkennung ---
   bool   breakout_detected = false;
   double breakout_level    = 0.0;
   double breakout_dist     = 0.0;
   double atr_val = _GetATRLocal(symbol, PERIOD_M15, 14, 1);

   if(atr_val > 0.0)
   {
      MqlRates bk_rates[];
      if(_GetCandles(symbol, PERIOD_M15, 3, bk_rates))
      {
         double cur_close = bk_rates[1].close;
         double pip       = _LDGetPipSize(symbol);

         if(direction == 1 && zones.resistance_count > 0)
         {
            for(int i = 0; i < zones.resistance_count; i++)
            {
               double lvl = zones.resistance[i];
               if(cur_close > lvl && (cur_close - lvl) > atr_val * 0.3)
               {
                  breakout_detected = true;
                  breakout_level    = lvl;
                  breakout_dist     = (pip > 0.0) ? (cur_close - lvl) / pip : 0.0;
                  break;
               }
            }
         }
         else if(direction == -1 && zones.support_count > 0)
         {
            for(int i = 0; i < zones.support_count; i++)
            {
               double lvl = zones.support[i];
               if(cur_close < lvl && (lvl - cur_close) > atr_val * 0.3)
               {
                  breakout_detected = true;
                  breakout_level    = lvl;
                  breakout_dist     = (pip > 0.0) ? (lvl - cur_close) / pip : 0.0;
                  break;
               }
            }
         }
      }
   }

   // --- [8] Volumen-Bestätigung (für Breakout) ---
   bool   vol_confirmed = false;
   double vol_ratio     = 0.0;
   if(breakout_detected)
   {
      long vol_buf[];
      ArraySetAsSeries(vol_buf, true);
      if(CopyTickVolume(symbol, PERIOD_M15, 1, 21, vol_buf) >= 21)
      {
         long vol_cur = vol_buf[0];
         long vol_sum = 0;
         for(int vi = 1; vi <= 20; vi++)
            vol_sum += vol_buf[vi];
         double avg_vol = (vol_sum > 0) ? (double)vol_sum / 20.0 : 0.0;
         if(avg_vol > 0.0)
         {
            vol_ratio     = (double)vol_cur / avg_vol;
            vol_confirmed = (vol_ratio >= 1.5);
         }
      }
   }

   // --- [9] Pullback-Entry mit Fibonacci ---
   bool   pullback_detected = false;
   double fib_38_val        = 0.0;
   double fib_62_val        = 0.0;
   double ema21_val         = 0.0;

   if(atr_val > 0.0)
   {
      ema21_val = GetEMA(symbol, PERIOD_M15, 21, 1);
      if(ema21_val > 0.0)
      {
         MqlRates pb_rates[];
         if(_GetCandles(symbol, PERIOD_M15, 21, pb_rates))
         {
            double cur_close = pb_rates[1].close;
            // Swing High/Low der letzten 20 Bars (shift 1..20)
            double swing_high = pb_rates[1].high;
            double swing_low  = pb_rates[1].low;
            for(int si = 2; si <= 20; si++)
            {
               if(pb_rates[si].high > swing_high) swing_high = pb_rates[si].high;
               if(pb_rates[si].low  < swing_low)  swing_low  = pb_rates[si].low;
            }

            double swing_range = swing_high - swing_low;
            if(swing_range > 0.0)
            {
               fib_38_val = swing_high - swing_range * 0.382;
               fib_62_val = swing_high - swing_range * 0.618;

               bool in_fib_zone = (cur_close >= fib_62_val && cur_close <= fib_38_val);
               bool near_ema    = (MathAbs(cur_close - ema21_val) <= atr_val * 0.3);

               if(in_fib_zone && near_ema)
                  pullback_detected = true;
            }
         }
      }
   }

   // --- Confidence berechnen ---
   result.score     = score;
   result.max_score = 11;
   double raw_conf  = (double)score / (double)result.max_score;
   result.confidence = MathMax(0.0, MathMin(1.0, raw_conf));

   // Breakout-Boost anwenden
   if(breakout_detected)
   {
      result.confidence = MathMin(1.0, result.confidence + 0.10);
      if(vol_confirmed)
      {
         LOG_I("EntrySignal", symbol,
               StringFormat("Volumen-Bestätigung ok | %.2f× Durchschnitt", vol_ratio));
      }
      else
      {
         result.confidence = MathMax(0.0, result.confidence - 0.15);
         LOG_W("EntrySignal", symbol,
               "Breakout ohne Volumen-Bestätigung | Confidence reduziert");
      }
   }

   // Pullback-Boost anwenden
   if(pullback_detected)
      result.confidence = MathMin(1.0, result.confidence + 0.08);

   if(result.confidence < cfg.entry.signal_confidence_threshold)
   {
      result.summary = StringFormat("None | Conf=%.2f < Threshold=%.2f",
                                    result.confidence,
                                    cfg.entry.signal_confidence_threshold);
      return result;
   }

   // --- Richtung und Entry-Typ festlegen ---
   result.signal = (direction == 1) ? SIGNAL_LONG : SIGNAL_SHORT;

   // Entry-Typ: Breakout/Pullback haben Vorrang, dann höchster Einzelscore
   if(breakout_detected)                         result.entry_type = ENTRY_BREAKOUT;
   else if(pullback_detected)                    result.entry_type = ENTRY_PULLBACK;
   else if(pin_pts >= 3)                         result.entry_type = ENTRY_PIN_BAR;
   else if(eng_pts >= 2)                         result.entry_type = ENTRY_ENGULFING;
   else if(rsi_pts >= 2)                         result.entry_type = ENTRY_RSI_DIVERGENCE;
   else if(macd_pts >= 1)                        result.entry_type = ENTRY_MACD_CROSS;
   else if(ema_pts >= 1)                         result.entry_type = ENTRY_EMA_TOUCH;

   // --- Entry-Preis ---
   if(direction == 1)
      result.entry_price = SymbolInfoDouble(symbol, SYMBOL_ASK);
   else
      result.entry_price = SymbolInfoDouble(symbol, SYMBOL_BID);

   // --- Entry-Typ als String ---
   string type_str = "";
   switch(result.entry_type)
   {
      case ENTRY_PIN_BAR:         type_str = "PinBar";         break;
      case ENTRY_ENGULFING:       type_str = "Engulfing";      break;
      case ENTRY_RSI_DIVERGENCE:  type_str = "RSI-Div";        break;
      case ENTRY_MACD_CROSS:      type_str = "MACD-Cross";     break;
      case ENTRY_EMA_TOUCH:       type_str = "EMA-Touch";      break;
      case ENTRY_BREAKOUT:        type_str = "Breakout";       break;
      case ENTRY_PULLBACK:        type_str = "Pullback";       break;
      default:                    type_str = "Mixed";           break;
   }

   string dir_str = (direction == 1) ? "Long" : "Short";

   // Breakout/Pullback-spezifische Logs
   if(breakout_detected)
   {
      LOG_I("EntrySignal", symbol,
            StringFormat("Breakout-Entry erkannt | Level=%.5f Abstand=%.1f Pips",
                         breakout_level, breakout_dist));
   }
   if(pullback_detected)
   {
      LOG_I("EntrySignal", symbol,
            StringFormat("Pullback-Entry erkannt | Fib38=%.5f Fib62=%.5f EMA21=%.5f",
                         fib_38_val, fib_62_val, ema21_val));
   }

   result.summary = StringFormat("%s | %s | RSI=%s | Conf=%.2f | Score=%d/%d",
                                 dir_str, type_str, rsi_str,
                                 result.confidence, result.score, result.max_score);

   LOG_I("EntrySignal", symbol, result.summary);

   return result;
}

#endif // INVESTAPP_ENTRYSIGNAL_MQH
