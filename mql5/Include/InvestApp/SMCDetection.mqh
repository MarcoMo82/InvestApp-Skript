//+------------------------------------------------------------------+
//| SMCDetection.mqh – FVG- und Order-Block-Erkennung               |
//| Smart Money Concepts: Fair Value Gaps + Order Blocks            |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_SMCDETECTION_MQH
#define INVESTAPP_SMCDETECTION_MQH

struct FairValueGap {
   bool     is_bullish;
   double   top;
   double   bottom;
   double   mid;
   datetime bar_time;
   bool     valid;
};

struct OrderBlock {
   bool     is_bullish;
   double   top;
   double   bottom;
   datetime bar_time;
   bool     valid;
};

// Erkennt bis zu 3 FVGs auf M15, lookback 50 Bars
int DetectFVGs(const string symbol, ENUM_TIMEFRAMES tf, FairValueGap &fvgs[], double atr) {
   ArrayResize(fvgs, 0);
   int bars = 50;
   double high[], low[], close[];
   datetime times[];
   ArraySetAsSeries(high,  true);
   ArraySetAsSeries(low,   true);
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(times, true);
   if(CopyHigh(symbol,tf,0,bars,high)<bars)   return 0;
   if(CopyLow(symbol,tf,0,bars,low)<bars)     return 0;
   if(CopyClose(symbol,tf,0,bars,close)<bars) return 0;
   if(CopyTime(symbol,tf,0,bars,times)<bars)  return 0;
   double cur = SymbolInfoDouble(symbol, SYMBOL_BID);
   double min_gap = atr * 0.1;
   int count = 0;
   for(int i=1; i<bars-2 && count<3; i++) {
      // Bullish FVG: low[i] > high[i+2]
      if(low[i] > high[i+2] && (low[i]-high[i+2]) >= min_gap) {
         FairValueGap f;
         f.is_bullish = true;
         f.top        = low[i];
         f.bottom     = high[i+2];
         f.mid        = (f.top + f.bottom) / 2.0;
         f.bar_time   = times[i];
         f.valid      = (cur >= f.bottom && cur <= f.top * 1.01);
         ArrayResize(fvgs, count+1);
         fvgs[count++] = f;
      }
      // Bearish FVG: high[i] < low[i+2]
      else if(high[i] < low[i+2] && (low[i+2]-high[i]) >= min_gap) {
         FairValueGap f;
         f.is_bullish = false;
         f.top        = low[i+2];
         f.bottom     = high[i];
         f.mid        = (f.top + f.bottom) / 2.0;
         f.bar_time   = times[i];
         f.valid      = (cur >= f.bottom * 0.99 && cur <= f.top);
         ArrayResize(fvgs, count+1);
         fvgs[count++] = f;
      }
   }
   return count;
}

// Erkennt bis zu 4 Order Blocks auf M15, lookback 100 Bars
int DetectOrderBlocks(const string symbol, ENUM_TIMEFRAMES tf, OrderBlock &obs[], double atr) {
   ArrayResize(obs, 0);
   int bars = 100;
   double high[], low[], open[], close[];
   datetime times[];
   ArraySetAsSeries(high,  true);
   ArraySetAsSeries(low,   true);
   ArraySetAsSeries(open,  true);
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(times, true);
   if(CopyHigh(symbol,tf,0,bars,high)<bars)   return 0;
   if(CopyLow(symbol,tf,0,bars,low)<bars)     return 0;
   if(CopyOpen(symbol,tf,0,bars,open)<bars)   return 0;
   if(CopyClose(symbol,tf,0,bars,close)<bars) return 0;
   if(CopyTime(symbol,tf,0,bars,times)<bars)  return 0;
   double cur = SymbolInfoDouble(symbol, SYMBOL_BID);
   double impulse = atr * 1.5;
   int count = 0;
   for(int i=2; i<bars-1 && count<4; i++) {
      // Bullish OB: bearishe Kerze bei i, dann Aufwärts-Impuls
      bool bearish_i = close[i] < open[i];
      double up_move = close[i-1] - open[i];
      if(bearish_i && up_move >= impulse) {
         OrderBlock ob;
         ob.is_bullish = true;
         ob.top        = high[i];
         ob.bottom     = low[i];
         ob.bar_time   = times[i];
         ob.valid      = (cur >= ob.bottom && cur <= ob.top * 1.005);
         ArrayResize(obs, count+1);
         obs[count++] = ob;
      }
      // Bearish OB: bullische Kerze bei i, dann Abwärts-Impuls
      bool bullish_i = close[i] > open[i];
      double down_move = open[i] - close[i-1];
      if(bullish_i && down_move >= impulse) {
         OrderBlock ob;
         ob.is_bullish = false;
         ob.top        = high[i];
         ob.bottom     = low[i];
         ob.bar_time   = times[i];
         ob.valid      = (cur >= ob.bottom * 0.995 && cur <= ob.top);
         ArrayResize(obs, count+1);
         obs[count++] = ob;
      }
   }
   return count;
}

// Berechnet SMC-Confluence-Bonus (0.0 – 0.20)
double CalcSMCBonus(double entry_price, FairValueGap &fvgs[], int fvg_count,
                    OrderBlock &obs[], int ob_count, double atr) {
   bool near_fvg = false;
   bool near_ob  = false;
   for(int i=0; i<fvg_count; i++) {
      if(!fvgs[i].valid) continue;
      if(MathAbs(entry_price - fvgs[i].mid) <= atr * 0.5) { near_fvg = true; break; }
   }
   for(int i=0; i<ob_count; i++) {
      if(!obs[i].valid) continue;
      double ob_mid = (obs[i].top + obs[i].bottom) / 2.0;
      if(MathAbs(entry_price - ob_mid) <= atr * 0.3) { near_ob = true; break; }
   }
   if(near_fvg && near_ob) return 0.20;
   if(near_ob)             return 0.15;
   if(near_fvg)            return 0.10;
   return 0.0;
}

#endif // INVESTAPP_SMCDETECTION_MQH
