//+------------------------------------------------------------------+
//| SMCDetection.mqh – Fair Value Gaps & Order Blocks               |
//| Nachbau der Python-Logik aus level_agent.py / entry_agent.py   |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_SMCDETECTION_MQH
#define INVESTAPP_SMCDETECTION_MQH

//+------------------------------------------------------------------+
//| Struct: Fair Value Gap                                           |
//+------------------------------------------------------------------+
struct FairValueGap
{
   bool     is_bullish;
   double   top;       // Oberkante der Lücke
   double   bottom;    // Unterkante der Lücke
   double   mid;       // Mittelpunkt der Lücke
   datetime time;      // Zeit der Impulse-Bar (mittlere Kerze)
   bool     valid;     // false wenn Preis die Lücke bereits geschlossen hat
};

//+------------------------------------------------------------------+
//| Struct: Order Block                                              |
//+------------------------------------------------------------------+
struct OrderBlock
{
   bool     is_bullish;
   double   top;       // Hoch der OB-Kerze
   double   bottom;    // Tief der OB-Kerze
   datetime time;      // Zeit der OB-Kerze
   bool     valid;     // false wenn Preis den OB durchbrochen hat (Gegenseite)
};

//+------------------------------------------------------------------+
//| DetectFVGs – Findet Fair Value Gaps auf M15                     |
//|                                                                  |
//| Python-Logik (level_agent.py _find_fvgs):                       |
//|   Bullish FVG:  low[i] > high[i+2]  (Bar i=neu, i+2=alt)       |
//|   Bearish FVG:  high[i] < low[i+2]                              |
//|   Mindestgröße: gap_size >= atr * 0.1                           |
//|   Mitte bullish: (low[i] + high[i+2]) / 2                       |
//|   Mitte bearish: (high[i] + low[i+2]) / 2                       |
//|                                                                  |
//| Lookback: 50 Bars | Gibt max. 3 jüngste gültige FVGs zurück    |
//+------------------------------------------------------------------+
int DetectFVGs(const string symbol, ENUM_TIMEFRAMES tf,
               FairValueGap &fvgs[], double atr)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, tf, 0, 53, rates); // 50 + 3 Puffer
   if(copied < 4) return 0;

   double current_price = SymbolInfoDouble(symbol, SYMBOL_BID);
   double min_gap       = atr * 0.1;

   ArrayResize(fvgs, 0);
   int found    = 0;
   int lookback = MathMin(copied - 2, 50);

   // rates[0] = neueste Bar (ggf. noch nicht abgeschlossen → j ab 1)
   // rates[j]   = Bar i   (neueste der drei, low/high geprüft)
   // rates[j+1] = Bar i+1 (Impulse-Bar, mittlere Kerze)
   // rates[j+2] = Bar i+2 (älteste der drei)
   for(int j = 1; j < lookback && found < 3; j++)
   {
      // --- Bullischer FVG: low[i] > high[i+2] ---
      if(rates[j].low > rates[j+2].high)
      {
         double gap_size = rates[j].low - rates[j+2].high;
         if(gap_size >= min_gap)
         {
            FairValueGap fvg;
            fvg.is_bullish = true;
            fvg.bottom     = rates[j+2].high;                    // high[i+2]
            fvg.top        = rates[j].low;                       // low[i]
            fvg.mid        = (fvg.top + fvg.bottom) / 2.0;
            fvg.time       = rates[j+1].time;
            // Gefüllt wenn Preis unter die Untergrenze gefallen ist
            fvg.valid      = (current_price >= fvg.bottom);
            ArrayResize(fvgs, found + 1);
            fvgs[found]    = fvg;
            found++;
         }
      }
      // --- Bearischer FVG: high[i] < low[i+2] ---
      else if(rates[j].high < rates[j+2].low)
      {
         double gap_size = rates[j+2].low - rates[j].high;
         if(gap_size >= min_gap)
         {
            FairValueGap fvg;
            fvg.is_bullish = false;
            fvg.bottom     = rates[j].high;                      // high[i]
            fvg.top        = rates[j+2].low;                     // low[i+2]
            fvg.mid        = (fvg.top + fvg.bottom) / 2.0;
            fvg.time       = rates[j+1].time;
            // Gefüllt wenn Preis über die Obergrenze gestiegen ist
            fvg.valid      = (current_price <= fvg.top);
            ArrayResize(fvgs, found + 1);
            fvgs[found]    = fvg;
            found++;
         }
      }
   }

   return found;
}

//+------------------------------------------------------------------+
//| DetectOrderBlocks – Findet Order Blocks auf M15                 |
//|                                                                  |
//| Python-Logik (level_agent.py _find_order_blocks):               |
//|   Bullish OB: letzte bearishe Kerze vor starkem Aufwärts-Impuls |
//|               (Impuls-Body > atr * 1.5 bullisch)                |
//|   Bearish OB: letzte bullische Kerze vor starkem Abwärts-Impuls  |
//|               (Impuls-Body > atr * 1.5 bearisch)                |
//|   OB-Bereich: high/low der Ursprungskerze                       |
//|                                                                  |
//| Lookback: 100 Bars | Max. 2 jüngste gültige OBs pro Richtung   |
//+------------------------------------------------------------------+
int DetectOrderBlocks(const string symbol, ENUM_TIMEFRAMES tf,
                      OrderBlock &obs[], double atr)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, tf, 0, 103, rates); // 100 + 3 Puffer
   if(copied < 4) return 0;

   double current_price = SymbolInfoDouble(symbol, SYMBOL_BID);
   double impulse_min   = atr * 1.5;

   ArrayResize(obs, 0);
   int bull_count = 0;
   int bear_count = 0;
   int total      = 0;

   int lookback = MathMin(copied - 1, 100);

   // rates[j]   = Impulse-Bar (der starke Bewegungsbar)
   // rates[j+1] = Ursprungskerze (potenzieller OB, liegt chronologisch davor)
   // Iteriere von neu nach alt → neueste OBs werden zuerst gefunden
   for(int j = 1; j < lookback; j++)
   {
      if(bull_count >= 2 && bear_count >= 2) break;

      double body = MathAbs(rates[j].close - rates[j].open);
      if(body < impulse_min) continue;

      // --- Bullischer OB: starker Aufwärts-Impuls nach bearischer Kerze ---
      if(rates[j].close > rates[j].open &&          // Impuls bullisch
         rates[j+1].close < rates[j+1].open &&       // Vorkerze bearisch (der OB)
         bull_count < 2)
      {
         OrderBlock ob;
         ob.is_bullish = true;
         ob.top        = rates[j+1].high;
         ob.bottom     = rates[j+1].low;
         ob.time       = rates[j+1].time;
         // OB konsumiert wenn Preis unter die Untergrenze gefallen ist
         ob.valid      = (current_price >= ob.bottom);
         ArrayResize(obs, total + 1);
         obs[total]    = ob;
         total++;
         bull_count++;
      }
      // --- Bearischer OB: starker Abwärts-Impuls nach bullischer Kerze ---
      else if(rates[j].close < rates[j].open &&      // Impuls bearisch
              rates[j+1].close > rates[j+1].open &&   // Vorkerze bullisch (der OB)
              bear_count < 2)
      {
         OrderBlock ob;
         ob.is_bullish = false;
         ob.top        = rates[j+1].high;
         ob.bottom     = rates[j+1].low;
         ob.time       = rates[j+1].time;
         // OB konsumiert wenn Preis über die Obergrenze gestiegen ist
         ob.valid      = (current_price <= ob.top);
         ArrayResize(obs, total + 1);
         obs[total]    = ob;
         total++;
         bear_count++;
      }
   }

   return total;
}

//+------------------------------------------------------------------+
//| CalcSMCBonus – Confidence-Bonus für FVG / OB Confluence         |
//|                                                                  |
//| Python-Logik (entry_agent.py _compute_smc_meta):                |
//|   FVG in Reichweite (innerhalb FVG oder ≤ ATR×0.5): +0.10      |
//|   OB  in Reichweite (innerhalb OB  oder ≤ ATR×0.3): +0.15      |
//|   Beide gleichzeitig aktiv:                          +0.20      |
//|                                                                  |
//| Rückgabewert: Bonus auf 0.0–1.0 Skala                           |
//+------------------------------------------------------------------+
double CalcSMCBonus(double entry_price,
                    FairValueGap &fvgs[], int fvg_count,
                    OrderBlock   &obs[],  int ob_count,
                    double atr)
{
   bool fvg_hit = false;
   bool ob_hit  = false;

   // FVG-Check: Entry innerhalb der Lücke oder ≤ ATR×0.5 vom Mittelpunkt
   double fvg_tolerance = atr * 0.5;
   for(int i = 0; i < fvg_count; i++)
   {
      if(!fvgs[i].valid) continue;
      bool inside = (entry_price >= fvgs[i].bottom && entry_price <= fvgs[i].top);
      bool near   = (MathAbs(entry_price - fvgs[i].mid) <= fvg_tolerance);
      if(inside || near) { fvg_hit = true; break; }
   }

   // OB-Check: Entry innerhalb des OB-Bereichs oder ≤ ATR×0.3 von der Mitte
   double ob_tolerance = atr * 0.3;
   for(int i = 0; i < ob_count; i++)
   {
      if(!obs[i].valid) continue;
      double ob_mid = (obs[i].top + obs[i].bottom) / 2.0;
      bool inside   = (entry_price >= obs[i].bottom && entry_price <= obs[i].top);
      bool near     = (MathAbs(entry_price - ob_mid) <= ob_tolerance);
      if(inside || near) { ob_hit = true; break; }
   }

   if(fvg_hit && ob_hit) return 0.20;
   if(ob_hit)             return 0.15;
   if(fvg_hit)            return 0.10;
   return 0.0;
}

#endif // INVESTAPP_SMCDETECTION_MQH
