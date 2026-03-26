//+------------------------------------------------------------------+
//| InvestApp_Test.mq5 – Minimaler Test-EA                           |
//| Zweck: Prüft ob EA-Grundfunktionen funktionieren                 |
//+------------------------------------------------------------------+
#property copyright "InvestApp"
#property version   "1.00"
#property strict

int g_counter = 0;

int OnInit()
{
   EventSetTimer(1);
   Print("=== InvestApp_Test: EA gestartet ===");
   Print("Symbol: ", Symbol(), " | AutoTrading: ", (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED));
   Print("Account: ", AccountInfoString(ACCOUNT_NAME), " | Balance: ", AccountInfoDouble(ACCOUNT_BALANCE));

   // Prüfe Common Files Pfad
   int fh = FileOpen("investapp_test.txt", FILE_WRITE|FILE_TXT|FILE_COMMON);
   if(fh != INVALID_HANDLE)
   {
      FileWriteString(fh, "EA läuft! " + TimeToString(TimeCurrent()));
      FileClose(fh);
      Print("Common Files: Schreiben erfolgreich → investapp_test.txt erstellt");
   }
   else
      Print("Common Files: FEHLER beim Schreiben! Code: ", GetLastError());

   // Prüfe pending_order.json
   if(FileIsExist("pending_order.json", FILE_COMMON))
      Print("pending_order.json: GEFUNDEN in Common Files");
   else
      Print("pending_order.json: NICHT gefunden in Common Files");

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); }
void OnTick() {}

void OnTimer()
{
   g_counter++;
   if(g_counter % 5 == 0)  // alle 5 Sekunden
   {
      Print("InvestApp_Test: Timer läuft (", g_counter, "s) | AutoTrading: ",
            (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED),
            " | EA-Trading: ", (bool)MQLInfoInteger(MQL_TRADE_ALLOWED));

      // Prüfe ob pending_order.json erschienen ist
      if(FileIsExist("pending_order.json", FILE_COMMON))
      {
         Print("pending_order.json GEFUNDEN – lese Inhalt:");
         int fh = FileOpen("pending_order.json", FILE_READ|FILE_TXT|FILE_COMMON);
         if(fh != INVALID_HANDLE)
         {
            string content = "";
            while(!FileIsEnding(fh)) content += FileReadString(fh);
            FileClose(fh);
            Print("Inhalt: ", content);
         }
      }
   }
}
