//+------------------------------------------------------------------+
//|  InvestApp_Indexes.mq5                                            |
//|  Expert Advisor – Indexes-Bereich                                 |
//|  Symbols: DE40, US500, US30, UK100, JP225                        |
//|  Architektur: OnTimer(1s) + 30s Analyse-Throttling               |
//+------------------------------------------------------------------+
#property copyright "InvestApp"
#property version   "0.1"
#property strict

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>
#include <InvestApp/MacroFilter.mqh>
#include <InvestApp/TrendAnalysis.mqh>
#include <InvestApp/VolatilityFilter.mqh>
#include <InvestApp/LevelDetection.mqh>
#include <InvestApp/EntrySignal.mqh>
#include <InvestApp/TradeValidator.mqh>
#include <InvestApp/RiskManager.mqh>
#include <InvestApp/TradeManagement.mqh>

//--- Input-Parameter
input int    AnalysisIntervalSeconds = 30;    // Analyse-Intervall in Sekunden
input string ConfigPath = "";                  // Pfad zu config.json (leer = Common Files)
input bool   EnableTrading = true;             // Trading aktiv

//--- Globale Variablen
string    SYMBOLS[] = {"DE40", "US500", "US30", "UK100", "JP225"};
int       SYMBOL_COUNT = 5;
datetime  g_lastAnalysisTime = 0;
AppConfig g_config;

//+------------------------------------------------------------------+
//| Expert Advisor initialisieren                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   // Timer auf 1 Sekunde setzen
   if(!EventSetTimer(1))
   {
      Print("[InvestApp_Indexes] FEHLER: Timer konnte nicht gesetzt werden");
      return INIT_FAILED;
   }

   Print("[InvestApp_Indexes] EA gestartet | Symbole: ", SYMBOL_COUNT,
         " | Intervall: ", AnalysisIntervalSeconds, "s");

   if(!LoadConfig(g_config, ConfigPath))
      Print("[InvestApp_Indexes] WARNUNG: Config konnte nicht geladen werden, nutze Standardwerte");
   else
      Print("[InvestApp_Indexes] Config geladen | Version: ", g_config.version,
            " | Stand: ", g_config.last_updated);

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Timer-Handler – läuft jede Sekunde                               |
//+------------------------------------------------------------------+
void OnTimer()
{
   datetime now = TimeCurrent();

   // Throttling: vollständige Analyse nur alle AnalysisIntervalSeconds
   if((int)(now - g_lastAnalysisTime) < AnalysisIntervalSeconds)
      return;

   g_lastAnalysisTime = now;

   // Alle Symbole analysieren
   for(int i = 0; i < SYMBOL_COUNT; i++)
   {
      string symbol = SYMBOLS[i];
      AnalyzeSymbol(symbol);
   }

   // Trade-Begleitung für offene Positionen
   // TODO: TradeManagement.ManageTrades()

   // Status schreiben
   // TODO: ea_status.json aktualisieren
}

//+------------------------------------------------------------------+
//| Symbol analysieren und ggf. Order platzieren                     |
//+------------------------------------------------------------------+
void AnalyzeSymbol(string symbol)
{
   // [1] Makro-Filter
   // TODO: if(!MacroFilter.IsAllowed(symbol)) return;

   // [2] Trend-Analyse
   TrendResult trend = AnalyzeTrend(symbol, g_config);
   // Richtung kommt vom EntrySignal – hier noch kein Filter; nur loggen
   if(!IsTrendAligned(trend, /* signal_direction */ 0))
      LOG_D("InvestApp_Indexes", symbol, "Trend nicht ausgerichtet: " + trend.summary);

   if(trend.direction == TREND_NEUTRAL)
   {
      LOG_D("InvestApp_Indexes", symbol, "Kein klarer Trend: " + trend.summary);
      return;
   }

   // [3] Volatilität prüfen
   VolatilityResult vol = CheckVolatility(symbol, g_config);
   if(!vol.isAcceptable)
   {
      LOG_D("InvestApp_Indexes", symbol, "Volatilität: " + vol.reject_reason);
      return;
   }
   if(!IsSessionActive(g_config))
   {
      LOG_D("InvestApp_Indexes", symbol, "Session nicht aktiv");
      return;
   }

   // [4] Level-Erkennung (aus zones.json)
   // TODO: LevelData levels = LevelDetection.GetZones(symbol);

   // [5] Entry-Signal (trend als Parameter weitergeben sobald EntrySignal implementiert)
   // TODO: SignalResult signal = EntrySignal.GetSignal(symbol, trend, levels);
   // TODO: if(signal.type == SIGNAL_NONE) return;

   // [6] Validierung (direction kommt vom EntrySignal)
   // ValidationResult val = ValidateTrade(symbol, signal.direction, g_config);
   // if(!val.isValid) { LOG_W("InvestApp_Indexes", symbol, "Validierung: " + val.reject_reason); return; }

   // [7] Risiko berechnen
   // TODO: RiskResult risk = RiskManager.Calculate(symbol, signal);
   // TODO: if(!risk.isValid) return;

   // [8] Order platzieren
   // TODO: if(EnableTrading) OrderSend(...);

   Print("[InvestApp_Indexes] ", symbol, " – Analyse abgeschlossen");
}

//+------------------------------------------------------------------+
//| EA beenden                                                        |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("[InvestApp_Indexes] EA gestoppt | Grund: ", reason);
}

//+------------------------------------------------------------------+
//| Trade-Transaktionen überwachen                                   |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result)
{
   // TODO: Neue Positionen in TradeManagement registrieren
   // TODO: Geschlossene Positionen in trade_log.json schreiben
}
