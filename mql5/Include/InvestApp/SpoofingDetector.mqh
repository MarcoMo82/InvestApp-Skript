//+------------------------------------------------------------------+
//| SpoofingDetector.mqh – Spoofing-Erkennung via Level-2-Orderbuch |
//| Erkennt Order-Imbalance, schnelle Stornierungen, Thin-Book-Trap |
//| Gibt SpoofingRisk zurück: SPOOF_NONE / LOW / MEDIUM / HIGH      |
//|                                                                  |
//| Voraussetzung: Broker muss MarketBook (Level-2) liefern.        |
//| Graceful Degradation wenn Level-2 nicht verfügbar.              |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_SPOOFINGDETECTOR_MQH
#define INVESTAPP_SPOOFINGDETECTOR_MQH

#include <InvestApp/Logger.mqh>

//--- Erkennungs-Schwellenwerte (konfigurierbar)
#define SPOOF_IMBALANCE_THRESHOLD  3.0   // Bid/Ask-Volumen-Ratio ab dem Alarm ausgelöst wird
#define SPOOF_CHANGE_THRESHOLD     0.5   // 50% Änderung des Gesamtvolumens zwischen Ticks → Alarm
#define SPOOF_LOOKBACK_TICKS       3     // Anzahl der Ticks die für Volumen-History gespeichert werden
#define SPOOF_THIN_BOOK_RATIO      0.15  // Unter 15% Near-Spread-Anteil am Gesamtvolumen → Thin-Book
#define SPOOF_MAX_TRACKED_SYMBOLS  30    // Maximale Anzahl gleichzeitig überwachter Symbole

//+------------------------------------------------------------------+
//| Spoofing-Risiko-Enum                                             |
//+------------------------------------------------------------------+
enum ENUM_SPOOF_RISK
{
   SPOOF_NONE   = 0,  // Kein Spoofing-Verdacht
   SPOOF_LOW    = 1,  // Geringes Risiko – Signal möglich, Confidence unverändert
   SPOOF_MEDIUM = 2,  // Mittleres Risiko – Confidence reduzieren
   SPOOF_HIGH   = 3   // Hohes Risiko – Signal blockieren
};

//+------------------------------------------------------------------+
//| Interner Zustand pro Symbol (Tick-History)                       |
//+------------------------------------------------------------------+
struct SpoofingState
{
   string   symbol;
   double   vol_history[SPOOF_LOOKBACK_TICKS]; // Gesamtvolumen der letzten N Ticks
   int      history_pos;                        // Schreibposition im Ringpuffer
   int      history_count;                      // Anzahl gespeicherter Werte (0–SPOOF_LOOKBACK_TICKS)
};

//--- Statischer Zustand für alle überwachten Symbole
static SpoofingState s_spoof_states[SPOOF_MAX_TRACKED_SYMBOLS];
static int           s_spoof_count = 0;

//+------------------------------------------------------------------+
//| Interne Hilfsfunktion: State für Symbol suchen oder anlegen      |
//+------------------------------------------------------------------+
int _GetOrCreateSpoofState(string symbol)
{
   // Vorhandenen State suchen
   for(int i = 0; i < s_spoof_count; i++)
      if(s_spoof_states[i].symbol == symbol)
         return i;

   // Neuen State anlegen (falls Kapazität vorhanden)
   if(s_spoof_count >= SPOOF_MAX_TRACKED_SYMBOLS)
   {
      LOG_W("SpoofingDetector", symbol,
            "Max. Symbolkapazität erreicht – State kann nicht angelegt werden");
      return -1;
   }

   int idx = s_spoof_count++;
   s_spoof_states[idx].symbol        = symbol;
   s_spoof_states[idx].history_pos   = 0;
   s_spoof_states[idx].history_count = 0;
   ArrayInitialize(s_spoof_states[idx].vol_history, 0.0);
   return idx;
}

//+------------------------------------------------------------------+
//| Interne Hilfsfunktion: Volumen in History-Ringpuffer speichern   |
//+------------------------------------------------------------------+
void _RecordVolume(int state_idx, double total_volume)
{
   int pos = s_spoof_states[state_idx].history_pos;
   s_spoof_states[state_idx].vol_history[pos] = total_volume;
   s_spoof_states[state_idx].history_pos =
      (pos + 1) % SPOOF_LOOKBACK_TICKS;
   if(s_spoof_states[state_idx].history_count < SPOOF_LOOKBACK_TICKS)
      s_spoof_states[state_idx].history_count++;
}

//+------------------------------------------------------------------+
//| Interne Hilfsfunktion: Maximale Volumenänderung über History     |
//| Gibt den größten prozentualen Sprung zurück (0.0 – 1.0+)        |
//+------------------------------------------------------------------+
double _MaxVolumeChange(int state_idx, double current_volume)
{
   double max_change = 0.0;
   int count = s_spoof_states[state_idx].history_count;
   if(count == 0) return 0.0;

   for(int i = 0; i < count; i++)
   {
      double hist_vol = s_spoof_states[state_idx].vol_history[i];
      if(hist_vol <= 0.0) continue;

      double change = MathAbs(current_volume - hist_vol) / hist_vol;
      if(change > max_change)
         max_change = change;
   }
   return max_change;
}

//+------------------------------------------------------------------+
//| Prüft ob Level-2-Orderbuchdaten verfügbar sind                  |
//| Gibt false zurück wenn Broker kein Level-2 liefert              |
//+------------------------------------------------------------------+
bool IsMarketBookAvailable(string symbol)
{
   MqlBookInfo book[];
   if(!MarketBookGet(symbol, book))
      return false;
   return (ArraySize(book) > 0);
}

//+------------------------------------------------------------------+
//| Haupt-Erkennungsfunktion – Spoofing im Orderbuch prüfen         |
//|                                                                  |
//| Erkennt drei Muster:                                            |
//|   [1] Order-Imbalance: Bid/Ask-Ratio > SPOOF_IMBALANCE_THRESHOLD|
//|   [2] Schnelle Stornierungen: Volumen-Δ > SPOOF_CHANGE_THRESHOLD|
//|   [3] Thin-Book-Trap: Wenig Volumen am Spread, große Walls weit |
//|                                                                  |
//| Graceful Degradation: Gibt SPOOF_NONE zurück wenn Level-2 leer  |
//+------------------------------------------------------------------+
ENUM_SPOOF_RISK CheckSpoofing(string symbol)
{
   // Level-2-Daten abrufen
   MqlBookInfo book[];
   if(!MarketBookGet(symbol, book))
   {
      LOG_D("SpoofingDetector", symbol, "Level-2 nicht verfügbar für " + symbol);
      return SPOOF_NONE;
   }

   int book_size = ArraySize(book);
   if(book_size == 0)
   {
      LOG_D("SpoofingDetector", symbol, "Level-2 nicht verfügbar für " + symbol);
      return SPOOF_NONE;
   }

   // [Vorbereitung] Bid/Ask-Volumen berechnen
   double bid_volume      = 0.0;
   double ask_volume      = 0.0;
   double near_bid_vol    = 0.0;  // Erste 3 Bid-Levels (am Spread)
   double near_ask_vol    = 0.0;  // Erste 3 Ask-Levels (am Spread)
   int    bid_near_count  = 0;
   int    ask_near_count  = 0;

   for(int i = 0; i < book_size; i++)
   {
      double vol = (book[i].volume_real > 0.0)
                  ? book[i].volume_real
                  : (double)book[i].volume;

      if(book[i].type == BOOK_TYPE_BUY)
      {
         bid_volume += vol;
         // Die ersten 3 Bid-Einträge sind am nächsten am Spread
         if(bid_near_count < 3) { near_bid_vol += vol; bid_near_count++; }
      }
      else if(book[i].type == BOOK_TYPE_SELL)
      {
         ask_volume += vol;
         if(ask_near_count < 3) { near_ask_vol += vol; ask_near_count++; }
      }
   }

   double total_volume = bid_volume + ask_volume;
   if(total_volume <= 0.0)
   {
      LOG_D("SpoofingDetector", symbol, "Orderbuch leer – kein Volumen erkannt");
      return SPOOF_NONE;
   }

   // [1] Order-Imbalance: Bid/Ask-Ratio
   double min_side = MathMin(bid_volume, ask_volume);
   double max_side = MathMax(bid_volume, ask_volume);
   double imbalance_ratio = (min_side > 0.0) ? (max_side / min_side) : 999.0;

   // [2] Schnelle Stornierungen: Volumen-Δ zur History
   int state_idx = _GetOrCreateSpoofState(symbol);
   double max_change = 0.0;
   if(state_idx >= 0)
   {
      max_change = _MaxVolumeChange(state_idx, total_volume);
      _RecordVolume(state_idx, total_volume);
   }

   // [3] Thin-Book-Trap: Near-Spread-Anteil am Gesamtvolumen
   double near_total = near_bid_vol + near_ask_vol;
   double near_ratio = (total_volume > 0.0) ? (near_total / total_volume) : 1.0;
   bool   thin_book  = (near_ratio < SPOOF_THIN_BOOK_RATIO);

   // --- Risiko-Bewertung ---
   int risk_score = 0;

   if(imbalance_ratio > SPOOF_IMBALANCE_THRESHOLD)   risk_score++;
   if(max_change > SPOOF_CHANGE_THRESHOLD)            risk_score++;
   if(thin_book)                                      risk_score++;

   ENUM_SPOOF_RISK result = SPOOF_NONE;
   if(risk_score == 1) result = SPOOF_LOW;
   if(risk_score == 2) result = SPOOF_MEDIUM;
   if(risk_score >= 3) result = SPOOF_HIGH;

   // --- Logging bei Verdacht ---
   if(result >= SPOOF_MEDIUM)
   {
      string dominant = (bid_volume > ask_volume) ? "BID" : "ASK";
      LOG_W("SpoofingDetector", symbol,
            StringFormat("Spoofing-Alarm %s | Imbalance=%.1fx (%s dominant) | "
                         "Volumen-Δ=%.0f%% | Thin-Book=%s | Score=%d/3",
                         EnumToString(result),
                         imbalance_ratio,
                         dominant,
                         max_change * 100.0,
                         thin_book ? "JA" : "NEIN",
                         risk_score));
   }
   else if(result == SPOOF_LOW)
   {
      LOG_D("SpoofingDetector", symbol,
            StringFormat("Spoofing LOW | Imbalance=%.1fx | Volumen-Δ=%.0f%% | Thin-Book=%s",
                         imbalance_ratio,
                         max_change * 100.0,
                         thin_book ? "JA" : "NEIN"));
   }

   return result;
}

//+------------------------------------------------------------------+
//| Hilfsfunktion: Risk-Level als lesbare Zeichenkette               |
//+------------------------------------------------------------------+
string SpoofRiskToString(ENUM_SPOOF_RISK risk)
{
   switch(risk)
   {
      case SPOOF_NONE:   return "NONE";
      case SPOOF_LOW:    return "LOW";
      case SPOOF_MEDIUM: return "MEDIUM";
      case SPOOF_HIGH:   return "HIGH";
      default:           return "UNBEKANNT";
   }
}

#endif // INVESTAPP_SPOOFINGDETECTOR_MQH
