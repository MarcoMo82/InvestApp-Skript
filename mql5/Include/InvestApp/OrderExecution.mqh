//+------------------------------------------------------------------+
//| OrderExecution.mqh – OrderSend + Fehlerbehandlung                |
//+------------------------------------------------------------------+
#ifndef INVESTAPP_ORDEREXECUTION_MQH
#define INVESTAPP_ORDEREXECUTION_MQH

#include <InvestApp/Logger.mqh>
#include <InvestApp/ConfigReader.mqh>
#include <InvestApp/SessionManager.mqh>

//+------------------------------------------------------------------+
//| Ergebnis-Struct                                                   |
//+------------------------------------------------------------------+
struct OrderResult
{
   bool   success;
   ulong  ticket;
   double filled_price;
   double filled_lots;
   string error_msg;
   int    error_code;
};

//+------------------------------------------------------------------+
//| Retcode in lesbaren String übersetzen                            |
//+------------------------------------------------------------------+
string RetcodeToString(uint retcode)
{
   switch(retcode)
   {
      case TRADE_RETCODE_DONE:            return "DONE – Anfrage ausgeführt";
      case TRADE_RETCODE_DONE_PARTIAL:    return "DONE_PARTIAL – Teilausführung";
      case TRADE_RETCODE_ERROR:           return "ERROR – allgemeiner Fehler";
      case TRADE_RETCODE_TIMEOUT:         return "TIMEOUT – Timeout";
      case TRADE_RETCODE_INVALID:         return "INVALID – ungültige Anfrage";
      case TRADE_RETCODE_INVALID_VOLUME:  return "INVALID_VOLUME – ungültiges Volumen";
      case TRADE_RETCODE_INVALID_PRICE:   return "INVALID_PRICE – ungültiger Preis";
      case TRADE_RETCODE_INVALID_STOPS:   return "INVALID_STOPS – ungültige SL/TP";
      case TRADE_RETCODE_TRADE_DISABLED:  return "TRADE_DISABLED – Trading deaktiviert";
      case TRADE_RETCODE_MARKET_CLOSED:   return "MARKET_CLOSED – Markt geschlossen";
      case TRADE_RETCODE_NO_MONEY:        return "NO_MONEY – nicht genug Kapital";
      case TRADE_RETCODE_PRICE_CHANGED:   return "PRICE_CHANGED – Preis verändert";
      case TRADE_RETCODE_PRICE_OFF:       return "PRICE_OFF – kein Kurs";
      case TRADE_RETCODE_INVALID_EXPIRATION: return "INVALID_EXPIRATION – ungültige Ablaufzeit";
      case TRADE_RETCODE_ORDER_CHANGED:   return "ORDER_CHANGED – Order verändert";
      case TRADE_RETCODE_TOO_MANY_REQUESTS: return "TOO_MANY_REQUESTS – zu viele Anfragen";
      case TRADE_RETCODE_NO_CHANGES:      return "NO_CHANGES – keine Änderungen";
      case TRADE_RETCODE_SERVER_DISABLES_AT: return "SERVER_DISABLES_AT – Server sperrt AutoTrading";
      case TRADE_RETCODE_CLIENT_DISABLES_AT: return "CLIENT_DISABLES_AT – Client sperrt AutoTrading";
      case TRADE_RETCODE_LOCKED:          return "LOCKED – Order gesperrt";
      case TRADE_RETCODE_FROZEN:          return "FROZEN – Order eingefroren";
      case TRADE_RETCODE_INVALID_FILL:    return "INVALID_FILL – ungültiger Filling-Modus";
      case TRADE_RETCODE_CONNECTION:      return "CONNECTION – keine Verbindung";
      case TRADE_RETCODE_ONLY_REAL:       return "ONLY_REAL – nur für Real-Konten";
      case TRADE_RETCODE_LIMIT_ORDERS:    return "LIMIT_ORDERS – Order-Limit erreicht";
      case TRADE_RETCODE_LIMIT_VOLUME:    return "LIMIT_VOLUME – Volumen-Limit erreicht";
      case TRADE_RETCODE_INVALID_ORDER:   return "INVALID_ORDER – ungültige Order";
      case TRADE_RETCODE_POSITION_CLOSED: return "POSITION_CLOSED – Position bereits geschlossen";
      case TRADE_RETCODE_REQUOTE:         return "REQUOTE – Requote";
      case TRADE_RETCODE_REJECT:          return "REJECT – abgelehnt";
      default:
         return "UNBEKANNT (" + string(retcode) + ")";
   }
}

//+------------------------------------------------------------------+
//| Market Order platzieren                                          |
//| direction: 1=Long, -1=Short                                      |
//| atr_value: ATR zum Zeitpunkt des Signals (für RegisterPosition)  |
//+------------------------------------------------------------------+
OrderResult PlaceMarketOrder(string symbol, int direction, double lots,
                             double sl_price, double tp_price,
                             AppConfig &cfg, double atr_value = 0.0)
{
   OrderResult res;
   res.success      = false;
   res.ticket       = 0;
   res.filled_price = 0.0;
   res.filled_lots  = 0.0;
   res.error_msg    = "";
   res.error_code   = 0;

   // --- Vorbereitung ---
   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};

   request.action   = TRADE_ACTION_DEAL;
   request.symbol   = symbol;
   request.volume   = NormalizeDouble(lots, 2);
   request.type     = (direction > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   request.price    = (direction > 0)
                      ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                      : SymbolInfoDouble(symbol, SYMBOL_BID);
   request.deviation  = 10;
   request.magic      = 20260101;
   request.comment    = "InvestApp_v1";
   request.type_filling = ORDER_FILLING_IOC;

   // --- SL setzen ---
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   request.sl = NormalizeDouble(sl_price, digits);

   // --- TP setzen ---
   request.tp = cfg.trade_exit.use_fixed_tp
                ? NormalizeDouble(tp_price, digits)
                : 0.0;

   // --- Mindestabstand SL prüfen ---
   long stops_level = SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(stops_level > 0)
   {
      double point      = SymbolInfoDouble(symbol, SYMBOL_POINT);
      double min_dist   = stops_level * point;

      if(direction > 0)
      {
         double min_sl = request.price - min_dist;
         if(request.sl > min_sl)
         {
            LOG_W("OrderExecution", symbol,
                  StringFormat("SL %.5f zu nah – angepasst auf %.5f (StopsLevel=%d)",
                               request.sl, min_sl, (int)stops_level));
            request.sl = NormalizeDouble(min_sl, digits);
         }
      }
      else
      {
         double min_sl = request.price + min_dist;
         if(request.sl < min_sl)
         {
            LOG_W("OrderExecution", symbol,
                  StringFormat("SL %.5f zu nah – angepasst auf %.5f (StopsLevel=%d)",
                               request.sl, min_sl, (int)stops_level));
            request.sl = NormalizeDouble(min_sl, digits);
         }
      }
   }

   // --- OrderSend ausführen ---
   bool sent = OrderSend(request, result);

   if(sent && result.retcode == TRADE_RETCODE_DONE)
   {
      res.success      = true;
      res.ticket       = result.order;
      res.filled_price = result.price;
      res.filled_lots  = result.volume;

      LOG_I("OrderExecution", symbol,
            "Order platziert | Ticket=" + string(res.ticket) +
            " | " + (direction > 0 ? "BUY" : "SELL") +
            " " + DoubleToString(res.filled_lots, 2) +
            " @ " + DoubleToString(res.filled_price, digits) +
            " | SL=" + DoubleToString(request.sl, digits));

      // Position in State-Machine registrieren
      RegisterPosition(res.ticket, res.filled_price, atr_value);
   }
   else
   {
      res.error_code = (int)result.retcode;
      res.error_msg  = RetcodeToString(result.retcode);

      LOG_E("OrderExecution", symbol,
            "OrderSend fehlgeschlagen | " + res.error_msg +
            " | Retcode=" + string(result.retcode));
   }

   return res;
}

#endif // INVESTAPP_ORDEREXECUTION_MQH
