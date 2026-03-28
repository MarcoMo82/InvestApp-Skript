//+------------------------------------------------------------------+
//| EntrySignal.mqh – Candlestick + Indikator Signale               |
//| Stufe 2d: Breakout/Pullback-Entry + Volumen-Bestätigung         |
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
   double      confidence;        // 0.0–1.0
   double      entry_price;       // vorgeschlagener Entry (Ask/Bid)
   string      summary;           // z.B. "Long | PinBar | RSI=32 | Conf=0.78"
   int         score;
   int         max_score;
   bool        volume_confirmed;  // true wenn vol_cur > avg_vol * 1.5 (Breakout)
   double      fib_level;         // Fibonacci-Retracement-Level (Pullback, 0.382–0.618)
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
//| Hilfsfunktion: ATR (14, M15) – lokal um zirkuläre Includes      |
//| zu vermeiden                                                      |
//+------------------------------------------------------------------+
double _GetATREntry(string symbol)
{
   int handle = iATR(symbol, PERIOD_M15, 14);
   if(handle == INVALID_HANDLE) return 0.0;

   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, 1, 1, buf) <= 0)
   {
      IndicatorRelease(handle);
      return 0.0;
   }
   IndicatorRelease(handle);
   return buf[0];
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
//| Volumen-Bestätigung: aktuell vs. 20-Bar-Durchschnitt            |
//| Gibt true zurück wenn vol_cur > avg_vol * 1.5                   |
//+------------------------------------------------------------------+
bool _CheckVolume(string symbol)
{
   long vol_cur = iVolume(symbol, PERIOD_M15, 1);
   if(vol_cur <= 0) return false;

   long vol_sum = 0;
   for(int i = 1; i <= 20; i++)
   {
      long v = iVolume(symbol, PERIOD_M15, i);
      if(v > 0) vol_sum += v;
   }
   long vol_avg = vol_sum / 20;

   return (vol_avg > 0 && vol_cur > vol_avg * 1.5);
}

//+------------------------------------------------------------------+
//| Hauptfunktion: Signal berechnen                                  |
//+------------------------------------------------------------------+
SignalResult GetSignal(string symbol, TrendResult &trend, SymbolZones &zones, AppConfig &cfg)
{
   SignalResult result;
   result.signal           = SIGNAL_NONE;
   result.entry_type       = ENTRY_NONE;
   result.confidence       = 0.0;
   result.entry_price      = 0.0;
   result.summary          = "None";
   result.score            = 0;
   result.max_score        = 11;
   result.volume_confirmed = false;
   result.fib_level        = 0.0;

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

      if(direction == 1 && cross_up)    { score += 1; macd_pts = 1; }
      if(direction == -1 && cross_down) { score += 1; macd_pts = 1; }
   }

   // --- [3] Candlestick-Muster ---
   if(IsPinBar(symbol, direction))    { score += 3; pin_pts = 3; }
   if(IsEngulfing(symbol, direction)) { score += 2; eng_pts = 2; }

   // --- [4] EMA-Touch ---
   if(_IsEMATouch(symbol, direction)) { score += 1; ema_pts = 1; }

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

   // --- Confidence aus Score berechnen ---
   result.score     = score;
   result.max_score = 11;
   double raw_conf  = (double)score / (double)result.max_score;
   result.confidence = MathMax(0.0, MathMin(1.0, raw_conf));

   // --- [7] Breakout-Entry erkennen ---
   // Close bricht Resistance (Long) oder Support (Short) um > ATR * 0.3
   double atr_val = _GetATREntry(symbol);
   bool is_breakout = false;
   bool is_pullback = false;

   MqlRates cur_rates[];
   ArraySetAsSeries(cur_rates, true);
   if(atr_val > 0.0 && CopyRates(symbol, PERIOD_M15, 0, 3, cur_rates) >= 2)
   {
      double cur_close = cur_rates[1].close;

      // --- Breakout ---
      if(direction == 1 && zones.nearest_resistance > 0.0)
      {
         if(cur_close > zones.nearest_resistance + atr_val * 0.3)
            is_breakout = true;
      }
      else if(direction == -1 && zones.nearest_support > 0.0)
      {
         if(cur_close < zones.nearest_support - atr_val * 0.3)
            is_breakout = true;
      }

      // --- Pullback (nur wenn kein Breakout) ---
      if(!is_breakout)
      {
         // 20-Bar Swing High/Low auf M15
         MqlRates swing_rates[];
         ArraySetAsSeries(swing_rates, true);
         int swcnt = CopyRates(symbol, PERIOD_M15, 1, 20, swing_rates);
         if(swcnt >= 20)
         {
            double swing_high = swing_rates[0].high;
            double swing_low  = swing_rates[0].low;
            for(int si = 1; si < swcnt; si++)
            {
               if(swing_rates[si].high > swing_high) swing_high = swing_rates[si].high;
               if(swing_rates[si].low  < swing_low)  swing_low  = swing_rates[si].low;
            }

            double swing_range = swing_high - swing_low;
            if(swing_range > 0.0)
            {
               double ema21_val = GetEMA(symbol, PERIOD_M15, 21, 1);
               // Preis muss nahe EMA21 sein (innerhalb 0.2% Toleranz)
               bool near_ema = (ema21_val > 0.0 &&
                                MathAbs(cur_close - ema21_val) <= ema21_val * 0.002);

               // Fibonacci-Retracement berechnen
               double retrace = 0.0;
               if(direction == 1)
                  retrace = (swing_high - cur_close) / swing_range;
               else
                  retrace = (cur_close - swing_low) / swing_range;

               // Gültig bei Fibonacci 38.2%–61.8% UND nahe EMA21
               if(near_ema && retrace >= 0.382 && retrace <= 0.618)
               {
                  is_pullback = true;
                  result.fib_level = retrace;
               }
            }
         }
      }
   }

   // --- [8] Breakout/Pullback Confidence-Anpassung ---
   if(is_breakout)
   {
      result.confidence += 0.10;
      result.entry_type  = ENTRY_BREAKOUT;

      // Volumen-Bestätigung für Breakout prüfen
      bool vol_ok = _CheckVolume(symbol);
      result.volume_confirmed = vol_ok;
      if(!vol_ok)
      {
         result.confidence -= 0.15;
         LOG_W("EntrySignal", symbol,
               StringFormat("Breakout ohne Volumenbestätigung – Conf reduziert auf %.2f",
                            result.confidence));
      }
   }
   else if(is_pullback)
   {
      result.confidence += 0.08;
      result.entry_type  = ENTRY_PULLBACK;
   }
   else
   {
      // Candlestick-basierter Entry-Typ (Priorität: Pin > Engulfing > RSI > MACD > EMA)
      if(pin_pts >= 3)       result.entry_type = ENTRY_PIN_BAR;
      else if(eng_pts >= 2)  result.entry_type = ENTRY_ENGULFING;
      else if(rsi_pts >= 2)  result.entry_type = ENTRY_RSI_DIVERGENCE;
      else if(macd_pts >= 1) result.entry_type = ENTRY_MACD_CROSS;
      else if(ema_pts >= 1)  result.entry_type = ENTRY_EMA_TOUCH;
   }

   // Confidence auf [0.0, 1.0] klemmen
   result.confidence = MathMax(0.0, MathMin(1.0, result.confidence));

   // --- Schwellenwert-Check ---
   if(result.confidence < cfg.entry.signal_confidence_threshold)
   {
      result.summary = StringFormat("None | Conf=%.2f < Threshold=%.2f",
                                    result.confidence,
                                    cfg.entry.signal_confidence_threshold);
      return result;
   }

   // --- Richtung und Entry-Preis setzen ---
   result.signal = (direction == 1) ? SIGNAL_LONG : SIGNAL_SHORT;

   if(direction == 1)
      result.entry_price = SymbolInfoDouble(symbol, SYMBOL_ASK);
   else
      result.entry_price = SymbolInfoDouble(symbol, SYMBOL_BID);

   // --- Entry-Typ als String ---
   string type_str = "";
   switch(result.entry_type)
   {
      case ENTRY_PIN_BAR:         type_str = "PinBar";      break;
      case ENTRY_ENGULFING:       type_str = "Engulfing";   break;
      case ENTRY_RSI_DIVERGENCE:  type_str = "RSI-Div";     break;
      case ENTRY_MACD_CROSS:      type_str = "MACD-Cross";  break;
      case ENTRY_EMA_TOUCH:       type_str = "EMA-Touch";   break;
      case ENTRY_BREAKOUT:        type_str = "Breakout";    break;
      case ENTRY_PULLBACK:        type_str = StringFormat("Pullback(Fib=%.3f)", result.fib_level); break;
      default:                    type_str = "Mixed";        break;
   }

   string dir_str = (direction == 1) ? "Long" : "Short";
   string vol_str = (result.entry_type == ENTRY_BREAKOUT)
                    ? (result.volume_confirmed ? " VolOK" : " VolWeak")
                    : "";

   result.summary = StringFormat("%s | %s%s | RSI=%s | Conf=%.2f | Score=%d/%d",
                                 dir_str, type_str, vol_str, rsi_str,
                                 result.confidence, result.score, result.max_score);

   LOG_I("EntrySignal", symbol, result.summary);

   return result;
}

#endif // INVESTAPP_ENTRYSIGNAL_MQH
