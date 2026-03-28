//+------------------------------------------------------------------+
//| SMCDetection.mqh – Smart Money Concepts: FVG + Order Blocks     |
//| Stufe 2b: Fair Value Gaps (FVG) und Order Blocks (OB)           |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_SMCDETECTION_MQH
#define INVESTAPP_SMCDETECTION_MQH

#include <InvestApp/Logger.mqh>

//+------------------------------------------------------------------+
//| Structs                                                           |
//+------------------------------------------------------------------+
struct FairValueGap
{
   bool     is_bullish;  // true = bullisches FVG, false = bearisches FVG
   double   top;         // obere Grenze der Lücke
   double   bottom;      // untere Grenze der Lücke
   double   mid;         // Mittelpunkt
   datetime bar_time;    // Zeitstempel der mittleren Kerze
   bool     valid;       // true wenn FVG aktiv (nicht bereits gefüllt)
};

struct OrderBlock
{
   bool     is_bullish;  // true = bullisches OB (Kerze vor starkem Aufwärtszug)
   double   top;         // obere Grenze des OB
   double   bottom;      // untere Grenze des OB
   datetime bar_time;    // Zeitstempel der OB-Kerze
   bool     valid;
};

//+------------------------------------------------------------------+
//| Fair Value Gaps erkennen                                         |
//| Lookback: 50 Bars | Mindestlücke: ATR × 0.1                    |
//| Speichert max. 3 neueste FVGs                                    |
//+------------------------------------------------------------------+
int DetectFVGs(string symbol, ENUM_TIMEFRAMES tf,
               FairValueGap &fvgs[], double atr)
{
   ArrayResize(fvgs, 0);
   if(atr <= 0.0) return 0;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, tf, 1, 52, rates);
   if(copied < 3) return 0;

   double min_gap = atr * 0.1;
   int    count   = 0;

   for(int i = 1; i < copied - 1 && count < 3; i++)
   {
      double low_i0  = rates[i - 1].low;   // neuere Kerze
      double high_i0 = rates[i - 1].high;
      double high_i2 = rates[i + 1].high;  // ältere Kerze
      double low_i2  = rates[i + 1].low;

      FairValueGap fvg;
      fvg.valid    = true;
      fvg.bar_time = rates[i].time;

      // Bullisches FVG: low[neuere] > high[ältere]
      if(low_i0 > high_i2 && (low_i0 - high_i2) >= min_gap)
      {
         fvg.is_bullish = true;
         fvg.top        = low_i0;
         fvg.bottom     = high_i2;
         fvg.mid        = (fvg.top + fvg.bottom) / 2.0;
         ArrayResize(fvgs, count + 1);
         fvgs[count++] = fvg;
      }
      // Bearisches FVG: high[neuere] < low[ältere]
      else if(high_i0 < low_i2 && (low_i2 - high_i0) >= min_gap)
      {
         fvg.is_bullish = false;
         fvg.top        = low_i2;
         fvg.bottom     = high_i0;
         fvg.mid        = (fvg.top + fvg.bottom) / 2.0;
         ArrayResize(fvgs, count + 1);
         fvgs[count++] = fvg;
      }
   }

   return count;
}

//+------------------------------------------------------------------+
//| Order Blocks erkennen                                            |
//| Lookback: 100 Bars | Impuls: ATR × 1.5                         |
//| Speichert max. 4 neueste OBs                                     |
//+------------------------------------------------------------------+
int DetectOrderBlocks(string symbol, ENUM_TIMEFRAMES tf,
                      OrderBlock &obs[], double atr)
{
   ArrayResize(obs, 0);
   if(atr <= 0.0) return 0;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, tf, 1, 102, rates);
   if(copied < 3) return 0;

   double min_impulse = atr * 1.5;
   int    count       = 0;

   for(int i = 1; i < copied - 1 && count < 4; i++)
   {
      double move = MathAbs(rates[i - 1].close - rates[i].close);
      if(move < min_impulse) continue;

      OrderBlock ob;
      ob.valid    = true;
      ob.bar_time = rates[i].time;
      ob.top      = MathMax(rates[i].open, rates[i].close);
      ob.bottom   = MathMin(rates[i].open, rates[i].close);

      // Bullisches OB: bearische Kerze [i] vor starkem Aufwärtszug [i-1]
      if(rates[i].close < rates[i].open &&
         rates[i - 1].close > rates[i - 1].open &&
         rates[i - 1].close > rates[i].high)
      {
         ob.is_bullish = true;
         ArrayResize(obs, count + 1);
         obs[count++] = ob;
      }
      // Bearisches OB: bullische Kerze [i] vor starkem Abwärtszug [i-1]
      else if(rates[i].close > rates[i].open &&
              rates[i - 1].close < rates[i - 1].open &&
              rates[i - 1].close < rates[i].low)
      {
         ob.is_bullish = false;
         ArrayResize(obs, count + 1);
         obs[count++] = ob;
      }
   }

   return count;
}

//+------------------------------------------------------------------+
//| SMC Confluence Bonus berechnen                                   |
//| Entry nahe FVG-Mitte:       +0.10                               |
//| Entry nahe OB-Mitte:        +0.15                               |
//| Beide gleichzeitig:         +0.20                               |
//| Nähe-Schwelle:              ATR × 0.5                           |
//+------------------------------------------------------------------+
double CalcSMCBonus(double entry_price,
                    FairValueGap &fvgs[], int fvg_count,
                    OrderBlock   &obs[],  int ob_count,
                    double atr)
{
   if(atr <= 0.0) return 0.0;
   double threshold = atr * 0.5;

   bool near_fvg = false;
   bool near_ob  = false;

   for(int i = 0; i < fvg_count; i++)
   {
      if(!fvgs[i].valid) continue;
      if(MathAbs(entry_price - fvgs[i].mid) <= threshold)
      {
         near_fvg = true;
         break;
      }
   }

   for(int i = 0; i < ob_count; i++)
   {
      if(!obs[i].valid) continue;
      double ob_mid = (obs[i].top + obs[i].bottom) / 2.0;
      if(MathAbs(entry_price - ob_mid) <= threshold)
      {
         near_ob = true;
         break;
      }
   }

   if(near_fvg && near_ob) return 0.20;
   if(near_ob)             return 0.15;
   if(near_fvg)            return 0.10;
   return 0.0;
}

#endif // INVESTAPP_SMCDETECTION_MQH
