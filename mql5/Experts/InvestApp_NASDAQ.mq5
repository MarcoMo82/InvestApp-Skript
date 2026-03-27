//+------------------------------------------------------------------+
//|  InvestApp_NASDAQ.mq5                                             |
//|  Expert Advisor – NASDAQ-Bereich                                  |
//|  Symbols: dynamisch aus Market Watch (Aktien CFD + NASDAQ-Index) |
//|           Override via config.json → ea_symbols.nasdaq           |
//|  Architektur: OnTimer(1s) + 30s Analyse-Throttling               |
//+------------------------------------------------------------------+
#property copyright "InvestApp"
#property version   "1.00"
#property strict

#define EA_NAME "NASDAQ"

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
#include <InvestApp/OrderExecution.mqh>
#include <InvestApp/SymbolManager.mqh>

//--- Input-Parameter
input int    AnalysisIntervalSeconds = 30;    // Analyse-Intervall in Sekunden
input string ConfigPath = "";                  // Pfad zu config.json (leer = Common Files)
input bool   EnableTrading = true;             // Trading aktiv

//--- Globale Variablen
string    SYMBOLS[];
int       SYMBOL_COUNT = 0;
datetime  g_lastAnalysisTime   = 0;
datetime  g_lastMarketDataWrite = 0;
AppConfig g_config;
double    g_last_atr = 0.0;

//+------------------------------------------------------------------+
//| Prüft ob Symbol in der EA-Symbolliste ist                        |
//+------------------------------------------------------------------+
bool IsOurSymbol(string symbol)
{
   for(int i = 0; i < SYMBOL_COUNT; i++)
      if(SYMBOLS[i] == symbol) return true;
   return false;
}

//+------------------------------------------------------------------+
//| Expert Advisor initialisieren                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   // Timer auf 1 Sekunde setzen
   if(!EventSetTimer(1))
   {
      Print("[InvestApp_NASDAQ] FEHLER: Timer konnte nicht gesetzt werden");
      return INIT_FAILED;
   }

   Print("[InvestApp_NASDAQ] EA gestartet | Intervall: ", AnalysisIntervalSeconds, "s");

   if(!LoadConfig(g_config, ConfigPath))
      Print("[InvestApp_NASDAQ] WARNUNG: Config konnte nicht geladen werden, nutze Standardwerte");
   else
      Print("[InvestApp_NASDAQ] Config geladen | Version: ", g_config.version,
            " | Stand: ", g_config.last_updated);

   // Symbole dynamisch laden (Market Watch oder config.json Override)
   SYMBOL_COUNT = LoadEASymbols(SYMBOLS, "nasdaq", ConfigPath);
   if(SYMBOL_COUNT == 0)
   {
      Print("[InvestApp_NASDAQ] FEHLER: Keine NASDAQ-Symbole gefunden – Market Watch und config.json prüfen");
      return INIT_FAILED;
   }
   LOG_I(EA_NAME, "", "Symbole geladen: " + IntegerToString(SYMBOL_COUNT) + " Symbole aus Market Watch");
   for(int i = 0; i < SYMBOL_COUNT; i++)
      LOG_D(EA_NAME, SYMBOLS[i], "Symbol aktiv");

   // Startup: Bestehende offene Positionen in State Machine laden
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket))
      {
         if(PositionGetInteger(POSITION_MAGIC) == 20260101)
         {
            string sym = PositionGetString(POSITION_SYMBOL);
            if(IsOurSymbol(sym))
            {
               double entry = PositionGetDouble(POSITION_PRICE_OPEN);
               double atr   = GetATR(sym, PERIOD_M15, 14, 1);
               RegisterPosition(ticket, entry, atr);
               LOG_I(EA_NAME, sym, "Startup: Bestehende Position geladen | Ticket=" + IntegerToString(ticket));
            }
         }
      }
   }

   // Tages-Equity-Startwert setzen (für Daily-Drawdown-Schutz)
   UpdateDailyEquityPeak();

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Timer-Handler – läuft jede Sekunde                               |
//+------------------------------------------------------------------+
void OnTimer()
{
   Print("[DEBUG] OnTimer fired | Symbol=", _Symbol, " Bid=", SymbolInfoDouble(_Symbol, SYMBOL_BID));

   datetime now = TimeCurrent();

   // Hauptanalyse – Throttling auf AnalysisIntervalSeconds
   if((int)(now - g_lastAnalysisTime) >= AnalysisIntervalSeconds)
   {
      g_lastAnalysisTime = now;
      for(int i = 0; i < SYMBOL_COUNT; i++)
         AnalyzeSymbol(SYMBOLS[i]);
   }

   // market_data.json alle 15 Minuten für Python Level Agent schreiben
   if((int)(TimeCurrent() - g_lastMarketDataWrite) >= 900)
   {
      WriteMarketData(SYMBOLS, SYMBOL_COUNT);
      g_lastMarketDataWrite = TimeCurrent();
   }

   // Trade-Management (Breakeven → Struktur-Trailing) – alle 30s
   static datetime s_lastTradeManage = 0;
   if((int)(TimeCurrent() - s_lastTradeManage) >= 30)
   {
      CleanupClosedPositions();
      ManageTrades(SYMBOLS, SYMBOL_COUNT, g_config);
      s_lastTradeManage = TimeCurrent();
   }

   // Rollover-Management – alle 60s
   static datetime s_lastRolloverCheck = 0;
   if((int)(TimeCurrent() - s_lastRolloverCheck) >= 60)
   {
      ManageRollover(SYMBOLS, SYMBOL_COUNT, g_config);
      s_lastRolloverCheck = TimeCurrent();
   }

   // ea_status.json alle 60s schreiben
   static datetime s_lastStatus = 0;
   if((int)(TimeCurrent() - s_lastStatus) >= 60)
   {
      string status = "{\"ea\": \"" + EA_NAME + "\", \"last_heartbeat\": \"" +
                      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) +
                      "\", \"open_positions\": " + string(PositionsTotal()) +
                      ", \"account_equity\": " + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) +
                      ", \"enabled\": " + string(EnableTrading) + "}";
      int f = FileOpen("ea_status_" + EA_NAME + ".json", FILE_WRITE|FILE_COMMON|FILE_TXT|FILE_ANSI);
      if(f != INVALID_HANDLE) { FileWriteString(f, status); FileClose(f); }
      s_lastStatus = TimeCurrent();
   }
}

//+------------------------------------------------------------------+
//| Symbol analysieren und ggf. Order platzieren                     |
//+------------------------------------------------------------------+
void AnalyzeSymbol(string symbol)
{
   // [1] Makro-Filter
   MacroResult macro = CheckMacro(symbol, g_config);
   if(!macro.isAllowed)
   {
      LOG_W("InvestApp_NASDAQ", symbol, "Order blocked: MacroFilter | " + macro.reject_reason);
      return;
   }

   // [2] Trend-Analyse
   TrendResult trend = AnalyzeTrend(symbol, g_config);
   if(trend.direction == TREND_NEUTRAL)
   {
      LOG_W("InvestApp_NASDAQ", symbol, "Order blocked: Kein klarer Trend | " + trend.summary);
      return;
   }

   // [3] Volatilität prüfen
   VolatilityResult vol = CheckVolatility(symbol, g_config);
   if(!vol.isAcceptable)
   {
      LOG_W("InvestApp_NASDAQ", symbol, "Order blocked: Volatilität | " + vol.reject_reason);
      return;
   }
   if(!IsSessionActive(g_config))
   {
      LOG_I("InvestApp_NASDAQ", symbol, "Order blocked: Session nicht aktiv");
      return;
   }

   // [4] Level-Erkennung (aus zones.json)
   SymbolZones zones;
   if(!LoadZones(symbol, zones))
      LOG_W("InvestApp_NASDAQ", symbol, "zones.json nicht geladen – Level-Filter deaktiviert, Trade möglich ohne Zone");

   // [5] Entry-Signal
   SignalResult signal = GetSignal(symbol, trend, zones, g_config);
   if(signal.signal == SIGNAL_NONE)
   {
      LOG_W("InvestApp_NASDAQ", symbol, "Order blocked: Kein Signal | " + signal.summary);
      return;
   }

   // [6] Validierung
   ValidationResult val = ValidateTrade(symbol, (int)signal.signal, g_config);
   if(!val.isValid)
   {
      LOG_W("InvestApp_NASDAQ", symbol, "Validierung: " + val.reject_reason);
      return;
   }

   // [7] Risiko berechnen
   RiskResult risk = CalculateRisk(symbol, (int)signal.signal, signal.entry_price, g_config);
   if(!risk.isValid)
   {
      LOG_W("InvestApp_NASDAQ", symbol, "Risiko: " + risk.reject_reason);
      return;
   }
   g_last_atr = risk.atr_value;

   LOG_I("InvestApp_NASDAQ", symbol,
         "Signal bereit | " + signal.summary + " | Lots=" + DoubleToString(risk.lots, 2));

   // [8] Order platzieren
   if(EnableTrading)
   {
      // Config alle 15 Min neu laden falls veraltet
      if(IsConfigStale())
      {
         LoadConfig(g_config);
         LOG_I("EA", symbol, "Config neu geladen");
      }

      OrderResult order = PlaceMarketOrder(
         symbol,
         (int)signal.signal,
         risk.lots,
         risk.sl_price,
         risk.tp_price,
         g_config,
         risk.atr_value
      );

      if(order.success)
      {
         RegisterPosition(order.ticket, order.filled_price, risk.atr_value);
         LOG_I("EA", symbol, "✓ Order erfolgreich | Ticket=" + string(order.ticket));
      }
   }
   else
   {
      LOG_I("EA", symbol, "SIMULATION | Signal wäre: " + signal.summary +
            " | Lots=" + DoubleToString(risk.lots, 2) +
            " | SL=" + DoubleToString(risk.sl_price, 5) +
            " | ATR=" + DoubleToString(risk.atr_value, 5));
   }
}

//+------------------------------------------------------------------+
//| EA beenden                                                        |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("[InvestApp_NASDAQ] EA gestoppt | Grund: ", reason);
}

//+------------------------------------------------------------------+
//| Trade-Transaktionen überwachen                                   |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result)
{
   // Neue Position registrieren (Entry-Deal)
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD
      && (trans.deal_type == DEAL_TYPE_BUY || trans.deal_type == DEAL_TYPE_SELL)
      && trans.position > 0)
   {
      if(HistoryDealSelect(trans.deal))
      {
         ENUM_DEAL_ENTRY deal_entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
         if(deal_entry == DEAL_ENTRY_IN && PositionSelectByTicket(trans.position))
         {
            double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
            RegisterPosition(trans.position, open_price, g_last_atr);
         }
      }
   }
}
