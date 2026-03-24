# Technisches Analyse-Handbuch für KI-Agenten

**InvestApp – Operative Referenz**
Stand: März 2026 | Zielgruppe: Trend-Agent, Volatility-Agent, Level-Agent, Entry-Agent, Risk-Agent

---

## Inhaltsverzeichnis

1. [Marktstruktur](#1-marktstruktur)
2. [Trendanalyse](#2-trendanalyse)
3. [Support & Resistance / Schlüsselzonen](#3-support--resistance--schlüsselzonen)
4. [Candlestick-Muster](#4-candlestick-muster)
5. [Chart-Muster](#5-chart-muster)
6. [Technische Indikatoren](#6-technische-indikatoren)
7. [Entry-Setups](#7-entry-setups)
8. [Risikomanagement](#8-risikomanagement)
9. [Zeitrahmen-Analyse (Multi-Timeframe)](#9-zeitrahmen-analyse-multi-timeframe)
10. [Marktphasen & Volatilität](#10-marktphasen--volatilität)
11. [Yahoo Finance — Datenverfügbarkeit](#11-yahoo-finance--datenverfügbarkeit)
12. [Forex-Handelssessions & Überlappungen](#12-forex-handelssessions--überlappungen)
13. [Wirtschaftskalender & High-Impact Events](#13-wirtschaftskalender--high-impact-events)
14. [Währungskorrelationen](#14-währungskorrelationen)
15. [Safe-Haven-Währungen & Marktsentiment](#15-safe-haven-währungen--marktsentiment)
16. [Carry Trades](#16-carry-trades)
17. [Forex-Risikomanagement & Spread-Management](#17-forex-risikomanagement--spread-management)
18. [Performance-Benchmarks](#18-performance-benchmarks)
19. [SMC-Confluence im Forex-Kontext](#19-smc-confluence-im-forex-kontext)

---

## 1. Marktstruktur

### Grundprinzip

Marktstruktur ist die fundamentale Sprache des Marktes. Jede Kursbewegung hinterlässt eine messbare strukturelle Spur aus Hochs (Swings Highs) und Tiefs (Swing Lows). KI-Agenten müssen diese Struktur vor jeder anderen Analyse bestimmen.

**Swing High (SH):** Eine Kerze, deren Hoch höher liegt als die Hochs der unmittelbar links und rechts liegenden Kerzen (mindestens 2–3 Kerzen auf jeder Seite als Bestätigung).

**Swing Low (SL):** Eine Kerze, deren Tief tiefer liegt als die Tiefs der unmittelbar links und rechts liegenden Kerzen.

---

### 1.1 Aufwärtstrend — Higher Highs / Higher Lows (HH/HL)

Ein Aufwärtstrend ist definiert durch eine Sequenz aus:
- **Higher High (HH):** Jedes neue Hoch übertrifft das vorherige Hoch
- **Higher Low (HL):** Jedes neue Tief liegt höher als das vorherige Tief

**Erkennungsregel (Agent):**
```
Wenn SH[n] > SH[n-1] UND SL[n] > SL[n-1] → Uptrend bestätigt
Mindestens 2 konsekutive HH/HL-Paare für valide Trendbestätigung
```

**Praktisches Beispiel:**
- Tief 1: 100 → Hoch 1: 110 → Tief 2: 105 (HL) → Hoch 2: 118 (HH) → Uptrend aktiv
- Long-Signale bevorzugen, Short-Setups vermeiden

**Trendstärke:** Je steiler die Winkel der HH und HL, desto dynamischer der Trend. Flache HLs deuten auf nachlassende Kaufbereitschaft hin.

---

### 1.2 Abwärtstrend — Lower Highs / Lower Lows (LH/LL)

Ein Abwärtstrend ist definiert durch:
- **Lower High (LH):** Jedes neue Hoch liegt unter dem vorherigen Hoch
- **Lower Low (LL):** Jedes neue Tief unterschreitet das vorherige Tief

**Erkennungsregel (Agent):**
```
Wenn SH[n] < SH[n-1] UND SL[n] < SL[n-1] → Downtrend bestätigt
Mindestens 2 konsekutive LH/LL-Paare für valide Trendbestätigung
```

**Praktisches Beispiel:**
- Hoch 1: 120 → Tief 1: 108 → Hoch 2: 115 (LH) → Tief 2: 100 (LL) → Downtrend aktiv
- Short-Signale bevorzugen, Long-Setups vermeiden

---

### 1.3 Seitwärtsmarkt erkennen

Ein Seitwärtsmarkt (Konsolidierung, Range) liegt vor, wenn:
- Hochs schwanken um einen konstanten Wert (±1–2 % Toleranz)
- Tiefs schwanken um einen konstanten Wert
- Kein neues HH/HL oder LH/LL wird geformt

**Erkennungsregel (Agent):**
```
Wenn (SH[n] ≈ SH[n-1] ± X%) UND (SL[n] ≈ SL[n-1] ± X%) → Seitwärtsbewegung
X% = ATR/Kurs × 100 (dynamische Toleranz)
```

**Bedeutung:** In Seitwärtsphasen sind Trendstrategien ineffektiv. Der Level-Agent markiert Ober- und Unterkante als Schlüsselzonen. Ausbrüche aus diesen Zonen liefern potenzielle Entry-Signale.

**Seitwärtsmarkt-Warnung:** Kein Trend-Signal ausgeben, wenn Marktstruktur unklar ist.

---

### 1.4 Strukturbruch (Break of Structure — BoS)

Ein Break of Structure (BoS) tritt auf, wenn der Kurs ein Strukturlevel **in Trendrichtung** durchbricht und schließt. BoS bestätigt die Trendfortsetzung.

**Bullischer BoS:**
- Preis schließt oberhalb des letzten validen Swing Highs
- Bestätigt: Uptrend läuft weiter, HH wurde geformt

**Bärischer BoS:**
- Preis schließt unterhalb des letzten validen Swing Lows
- Bestätigt: Downtrend läuft weiter, LL wurde geformt

**Regel:** BoS braucht einen **Close** über/unter dem Level — Wick-Durchbrüche allein gelten nicht als bestätigter BoS.

**Agenten-Output nach BoS:**
```
{
  "bos_typ": "bullish" | "bearish",
  "level": <Preis des gebrochenen SH/SL>,
  "bestätigt": true,
  "trendstatus": "fortsetzung"
}
```

---

### 1.5 Change of Character (CHoCH)

CHoCH ist das stärkste Trendumkehrsignal in der Marktstruktur. Es tritt auf, wenn der Preis **gegen den bestehenden Trend** ein Strukturlevel durchbricht.

**Bullischer CHoCH (Trendwende von bearisch zu bullisch):**
- Markt bildet LH/LL-Sequenz (Downtrend)
- Preis schließt **über** das letzte Lower High
- Signal: Mögliche Umkehr zu Uptrend

**Bärischer CHoCH (Trendwende von bullisch zu bearisch):**
- Markt bildet HH/HL-Sequenz (Uptrend)
- Preis schließt **unter** das letzte Higher Low
- Signal: Mögliche Umkehr zu Downtrend

**Wichtig:** CHoCH = Warnsignal, keine Garantie. Immer mit zusätzlicher Bestätigung kombinieren:
- Volumenanstieg beim CHoCH-Bruch
- Kerzenumkehrmuster am Breakout-Level
- Confluence mit FVG oder Order Block

**Unterschied BoS vs. CHoCH:**

| Merkmal | BoS | CHoCH |
|---|---|---|
| Richtung | In Trendrichtung | Gegen Trendrichtung |
| Bedeutung | Trendfortsetzung | Potenzielle Umkehr |
| Zuverlässigkeit | Hoch (Bestätigung) | Mittel (Warnsignal) |
| Folge-Analyse | Trend bleibt aktiv | Neue Strukturanalyse |

---

## 2. Trendanalyse

### 2.1 Trend im Mehrzeitrahmen

Die Trendanalyse läuft strikt **Top-Down**: Höherer Zeitrahmen definiert den übergeordneten Bias, niedrigere Zeitrahmen liefern Einstiegspräzision.

**Für InvestApp:**

| Zeitrahmen | Zweck | Agent |
|---|---|---|
| 15-Minuten-Chart | Haupttrend, struktureller Bias | Trend-Agent |
| 5-Minuten-Chart | Einstiegsstruktur, Präzision | Entry-Agent |
| Tick / 1-Minuten | Einstiegstiming, Kerzenbestätigung | Entry-Agent (Feintuning) |

**Regel:** Long-Setups nur, wenn 15m Uptrend aktiv ist. Short-Setups nur bei 15m Downtrend. Bei Widerspruch zwischen 15m und 5m → kein Signal.

---

### 2.2 Trendstärke bewerten

**Steigung des Trends:**
- Steiler Winkel (> 45°) = starker, dynamischer Trend
- Flacher Winkel (< 20°) = schwacher oder auslaufender Trend

**Abstands-Analyse zwischen Swing Points:**
- Größer werdende Abstände (Amplituden) = Trendbeschleunigung
- Kleiner werdende Abstände = Erschöpfung, Trendende möglich

**Retracement-Tiefe:**
- Starker Trend: Rücksetzer bis max. 38,2 % (Fibonacci-Basis)
- Normaler Trend: Rücksetzer bis 50 %
- Schwacher Trend: Rücksetzer bis 61,8 % oder tiefer

**Volumenprofil:** In starken Trends nimmt das Volumen in Trendrichtung zu und bei Rücksetzern ab. Umkehr dieses Musters = Warnsignal.

**Agenten-Score (Trendstärke 1–10):**
```
Score 8–10: Klarer Trend, alle Indikatoren aligned → Signal freigegeben
Score 5–7:  Mittlerer Trend, Vorsicht → Signal nur mit starker Confluence
Score 1–4:  Schwacher/kein Trend → Signal verworfen
```

---

### 2.3 Trendlinien zeichnen und validieren

**Aufwärtstrendlinie:**
- Verbindet mindestens 2 aufeinanderfolgende Swing Lows (Higher Lows)
- Je mehr Berührungspunkte, desto valider
- Gültig ab 3 Berührungen

**Abwärtstrendlinie:**
- Verbindet mindestens 2 aufeinanderfolgende Swing Highs (Lower Highs)
- Gültig ab 3 Berührungen

**Validierungsregeln:**
1. Keine Kerze darf die Linie mit dem **Close** durchbrochen haben (Wick-Berührung erlaubt)
2. Trendlinie muss mindestens 5 Kerzen (auf dem jeweiligen TF) alt sein
3. Neigung zwischen 20° und 70° (zu flach = keine Aussagekraft, zu steil = kurzlebig)

**Trendlinienbruch:** Wenn der Kurs die Trendlinie mit einem Close durchbricht → potenzielle Trendwende, CHoCH auf Trendlinie prüfen.

---

### 2.4 Moving Averages — EMA 9, 21, 50, 200

Exponentielle Moving Averages (EMA) gewichten jüngere Kurse stärker als ältere und reagieren damit schneller auf Preisveränderungen als Simple Moving Averages (SMA).

**Formel:**
```
EMA(t) = Kurs(t) × Multiplier + EMA(t-1) × (1 - Multiplier)
Multiplier = 2 / (Periode + 1)

EMA 9:   Multiplier = 2/10  = 0,200
EMA 21:  Multiplier = 2/22  = 0,0909
EMA 50:  Multiplier = 2/51  = 0,0392
EMA 200: Multiplier = 2/201 = 0,00995
```

**Bedeutung und Signale:**

| EMA | Funktion | Verwendung |
|---|---|---|
| EMA 9 | Kurzfristiger Impuls | Entry-Timing, Trendrichtung im 5m |
| EMA 21 | Kurzfristiger Trend | Pullback-Ziel, dynamische S/R |
| EMA 50 | Mittelfristiger Trend | Bestätigung Trendrichtung im 15m |
| EMA 200 | Langfristiger Trend | Übergeordneter Bias, Schlüssellevel |

**EMA-Signale:**

- **Kurs > EMA 200:** Bullischer Bias (übergeordnet)
- **Kurs < EMA 200:** Bärischer Bias (übergeordnet)
- **EMA 9 kreuzt EMA 21 von unten:** Kurzfristiges Kaufsignal
- **EMA 9 kreuzt EMA 21 von oben:** Kurzfristiges Verkaufssignal
- **EMA 50 kreuzt EMA 200 (Golden Cross):** Starkes Langfrist-Kaufsignal
- **EMA 50 kreuzt EMA 200 nach unten (Death Cross):** Starkes Langfrist-Verkaufssignal

**Dynamic Support/Resistance:** Bei Aufwärtstrend fungiert EMA 21 und EMA 50 als dynamischer Support. Rücksetzer an diese Levels + Candlestick-Bestätigung = klassisches Pullback-Entry.

**EMA-Reihenfolge (Uptrend):** EMA 9 > EMA 21 > EMA 50 > EMA 200 → vollständig aligned

---

## 3. Support & Resistance / Schlüsselzonen

### 3.1 Identifikation von Zonen

Support- und Resistance-Zonen sind **Preisbereiche** (keine exakten Linien), an denen der Kurs historisch signifikant reagiert hat.

**Identifikationsregeln:**
1. Mindestens 2 signifikante Berührungen/Reaktionen am Level
2. Stärkere Reaktion (lange Wicks, Umkehrkerzen) = höhere Bedeutung
3. Zonen statt Linien: ±0,1–0,3 % um den Kernpreis als Zone definieren
4. Höhere Timeframe-Levels haben Vorrang

**Stärke-Bewertung:**
- 2 Berührungen: Schwache Zone (50 % Reaktionswahrscheinlichkeit)
- 3–4 Berührungen: Mittlere Zone (65–70 %)
- 5+ Berührungen: Starke Zone (75–85 %)

**Regel:** Je öfter ein Level getestet wird, desto wahrscheinlicher wird es **gebrochen** (Liquidität wird abgebaut). Alte, oft getestete Zonen mit Vorsicht einsetzen.

---

### 3.2 Tageshoch / Tagestief

Das Tageshoch (Daily High) und Tagestief (Daily Low) sind täglich neu definierte, hochrelevante Marktstruktur-Levels.

**Bedeutung:**
- Dienen als Liquiditätszonen (Stop-Loss-Cluster vieler Trader darüber/darunter)
- Durchbruch mit Volumen → starkes Momentum-Signal
- Ablehnung am Tageshoch/-tief → potenzielle Umkehrstelle

**Agenten-Regel:**
```
Täglich zu Sessionbeginn berechnen:
- prev_high = Tageshoch des Vortages
- prev_low = Tagestief des Vortages
- Aktuelle Distance zu prev_high / prev_low → Level-Agent Output
```

**Praktische Nutzung:**
- Bei Kurs nahe Vortages-Hoch mit bärischen Kerzen → potenzieller Short
- Bei Kurs nahe Vortages-Tief mit bullischen Kerzen → potenzieller Long
- Ausbruch über Vortages-Hoch + Retest → Breakout-Entry (Long)

---

### 3.3 Wochenhoch / Wochentief

Wochenhoch und -tief haben noch größere institutionelle Bedeutung als Tageslevel.

**Entstehung:** Institutionelle Trader platzieren Stop-Orders über/unter Wochenhochs/-tiefs. Der Markt "sweept" diese Levels, bevor er in die eigentliche Richtung läuft.

**Nutzung:**
- Sweep des Wochenhochs + Rejection-Kerze → Short-Setup
- Sweep des Wochentiefs + Hammer/Engulfing → Long-Setup
- Ausbruch über Wochenhoch mit Volumenbestätigung → starkes Momentum-Signal

---

### 3.4 Psychologische Preislevels

Runde Zahlen und Zwischenstufen wirken als natürliche Unterstützung und Widerstand.

**Hierarchie:**
- Ganzzahlen: 1.0000, 1.1000, 100,00 $ → stärkste Ebene
- Halbe Levels: 1.0500, 1.1500, 50,00 $ → mittlere Stärke
- Viertel-Levels: 1.0250, 1.0750, 25,00 $ → schwächere Ebene

**Agenten-Regel:** Psychologische Levels immer in die Level-Map aufnehmen. Bei Confluence mit technischem S/R: Zonengewichtung erhöhen.

---

### 3.5 Fair Value Gaps (FVG)

Ein Fair Value Gap (FVG) ist eine Preisimbalanz, die durch eine aggressive Drei-Kerzen-Struktur entsteht, bei der der Markt so schnell bewegt, dass kein effizienter Handel stattfinden konnte.

**Identifikation:**

**Bullisches FVG:**
```
Kerze 1: Beliebige Richtung
Kerze 2: Bullische Impulkerze (großer Body, hohe Range)
Kerze 3: Beliebig

Bedingung: Low von Kerze 3 > High von Kerze 1
→ Lücke zwischen High[1] und Low[3] = Bullisches FVG
```

**Bärisches FVG:**
```
Bedingung: High von Kerze 3 < Low von Kerze 1
→ Lücke zwischen Low[1] und High[3] = Bärisches FVG
```

**Bedeutung und Nutzung:**
- Der Markt kehrt mit hoher Wahrscheinlichkeit in FVGs zurück, um die Imbalanz auszugleichen
- Einstieg: Kurs tritt in FVG ein + Umkehrkerze → Entry
- FVG-Mittelpunkt (50 % des Gaps) ist der bevorzugte Entry-Bereich
- FVGs verlieren nach vollständiger Füllung ihre Bedeutung

**FVG-Qualität:**
- Größeres Gap = stärkere Imbalanz = höhere Rückkehrwahrscheinlichkeit
- FVG auf 15m > FVG auf 5m (höhere TF bevorzugen)
- FVG im Trend = Continuation-Setup, FVG gegen Trend = ignorieren

---

### 3.6 Order Blocks

Order Blocks sind Preiszonen, in denen institutionelle Trader große Positionsaufträge platziert haben, erkennbar an einer starken anschließenden Kursbewegung.

**Bullischer Order Block:**
- Letzte bearische Kerze (rote Kerze) **vor** einem starken bullischen Move
- Dieser Kerzenbereich (High und Low der letzten roten Kerze) = Zone
- Der Markt kehrt oft in diesen Bereich zurück → Kaufzone

**Bärischer Order Block:**
- Letzte bullische Kerze (grüne Kerze) **vor** einem starken bearischen Move
- Dieser Kerzenbereich = Zone
- Der Markt kehrt oft zurück → Verkaufszone

**Validierungsregeln:**
1. Mindestens 3 × ATR Bewegung nach dem Order Block (starker Impuls erforderlich)
2. Order Block sollte noch nicht vollständig "durchgehandelt" worden sein
3. Confluence mit FVG = sehr starke Zone
4. Höherer Timeframe Order Block > niedrigerer Timeframe

**Praktisches Vorgehen:**
```
1. Identifiziere starken Impuls (≥ 3×ATR in einer oder wenigen Kerzen)
2. Gehe zur letzten gegenläufigen Kerze davor
3. Markiere High und Low dieser Kerze als Order Block Zone
4. Warte auf Rückkehr in diese Zone
5. Bestätigungskerze + FVG = Entry-Signal
```

---

### 3.7 Reaktionswahrscheinlichkeit bewerten

Für jeden Level berechnet der Level-Agent einen Reaktionsscore (0–100 %):

| Faktor | Gewichtung | Beschreibung |
|---|---|---|
| Anzahl Berührungen | 20 % | Mehr Berührungen = Höherer Score |
| Timeframe | 25 % | 15m > 5m > 1m |
| Candlestick-Reaktion | 20 % | Starke Umkehrkerzen erhöhen Score |
| Confluence (FVG/OB) | 20 % | Überlappung mit anderen Konzepten |
| Psychologisches Level | 10 % | Runde Zahlen |
| Volumen bei Reaktion | 5 % | Höheres Volumen = stärke Reaktion |

```
Score ≥ 75 %: Stark → Entry-Agent erhält Freigabe
Score 50–74 %: Mittel → Nur mit Bestätigungskerze
Score < 50 %: Schwach → Ignorieren
```

---

## 4. Candlestick-Muster

### 4.1 Einzelne Kerzen

**Doji**
- Open ≈ Close (Body nahe null, < 0,1 % der Kerzenrange)
- Indikation: Unentschlossenheit, Kräftegleichgewicht
- Bedeutung: Neutral — nur im Kontext relevant
- An Resistance: Mögliche Umkehr → Vorsicht
- An Support: Mögliche Stabilisierung
- **Varianten:** Gravestone Doji (langer Oberschatten) = bearisch, Dragonfly Doji (langer Unterschatten) = bullisch

**Hammer / Inverted Hammer**
- Hammer: Kleiner Body oben, langer Unterschatten (≥ 2× Body), kein/kurzer Oberschatten
- Bester Kontext: Am Ende eines Downtrends oder an Support-Zone
- Bullisches Signal: Käufer haben Verkaufsdruck absorbiert
- **Hanging Man:** Gleiche Form wie Hammer, aber im Uptrend → bärisches Signal
- Regel: Body-Farbe sekundär; Position im Chart entscheidet

**Shooting Star**
- Kleiner Body unten, langer Oberschatten (≥ 2× Body), kein/kurzer Unterschatten
- Am Ende eines Uptrends oder an Resistance → bärisches Umkehrsignal
- Zeigt: Käufer wurden zurückgewiesen

**Marubozu**
- Kein Schatten (oder minimal), sehr großer Body
- **Bullischer Marubozu:** Open = Low, Close = High → starkes Kaufinteresse
- **Bärischer Marubozu:** Open = High, Close = Low → starkes Verkaufsinteresse
- Bedeutung: Starkes Momentum in eine Richtung, keine Unentschlossenheit

**Spinning Top**
- Kleiner Body (beliebige Farbe), ähnlich lange Ober- und Unterschatten
- Unentschlossenheit ähnlich wie Doji, aber mit etwas mehr Körper
- Allein bedeutungslos — Kontext entscheidet

---

### 4.2 Kombinationen

**Bullisches Engulfing**
```
Kerze 1: Bearisch (rote Kerze)
Kerze 2: Bullisch, Body umschließt vollständig den Body von Kerze 1
         (Open[2] < Close[1] UND Close[2] > Open[1])
```
- Kontext: Am Downtrend-Ende oder an Support
- Signal: Starke Trendumkehr, Käufer übernehmen Kontrolle
- Qualität steigt mit: größerem Body[2], höherem Volumen, Position an Schlüsselzone

**Bearisches Engulfing**
```
Kerze 1: Bullisch (grüne Kerze)
Kerze 2: Bearisch, Body umschließt vollständig den Body von Kerze 1
```
- Kontext: Am Uptrend-Ende oder an Resistance
- Signal: Starke Trendumkehr, Verkäufer übernehmen Kontrolle

**Morning Star (Bullisch)**
```
Kerze 1: Große bearische Kerze (starker Downtrend)
Kerze 2: Kleiner Body (Doji oder Spinning Top), gap down möglich
Kerze 3: Große bullische Kerze, schließt mind. 50 % in Kerze 1 zurück
```
- Kontext: Am Boden eines Downtrends, idealerweise an Support/FVG
- Signal: Bullische Umkehr

**Evening Star (Bärisch)**
```
Kerze 1: Große bullische Kerze
Kerze 2: Kleiner Body oben (Doji/Spinning Top)
Kerze 3: Große bearische Kerze, schließt mind. 50 % in Kerze 1 zurück
```
- Kontext: Beim Hoch eines Uptrends, an Resistance
- Signal: Bärische Umkehr

**Harami**
- Bullisches Harami: Große bearische Kerze, gefolgt von kleiner bullischer Kerze (komplett innerhalb des ersten Bodys)
- Bärisches Harami: Große bullische Kerze, gefolgt von kleiner bearischer Kerze
- Schwächeres Signal als Engulfing — Bestätigung durch Folgekerze erforderlich

**Tweezer Top / Bottom**
- Tweezer Top: Zwei aufeinanderfolgende Kerzen mit exakt (±Pip) gleichem Hoch → Resistance bestätigt
- Tweezer Bottom: Zwei Kerzen mit gleichem Tief → Support bestätigt
- Signal: Doppelte Ablehnung an einem Level = erhöhte Umkehrwahrscheinlichkeit

---

### 4.3 Bedeutung im Kontext von S/R

**Regel für alle Candlestick-Muster:**
Ein Candlestick-Muster allein hat wenig Aussagekraft. Seine Bedeutung wird durch den **Kontext** (Position im Chart) multipliziert.

**Hohe Konfidenz:** Muster + Level + Trendkontext aligned:
- Bullisches Engulfing an Support-Zone im 15m-Uptrend → Score +25 %
- Shooting Star an Resistance + EMA 50 im Downtrend → Score +25 %

**Niedrige Konfidenz:** Muster ohne strukturellen Kontext:
- Doji mitten im Trend → ignorieren
- Engulfing gegen übergeordneten Trend → ignorieren

---

## 5. Chart-Muster

### 5.1 Fortsetzungsmuster

**Flag (Flagge)**
- Entstehung: Starker Impuls (Fahnenstange) + kurze, kanalförmige Konsolidierung leicht gegen Trendrichtung
- **Bullische Flagge:** Starker Kursanstieg + leicht fallender Konsolidierungskanal
- **Bärische Flagge:** Starker Kursfall + leicht steigender Konsolidierungskanal
- Volumen: Hoch beim Impuls, abnehmend während Flagge, ansteigend beim Ausbruch

**Kursziel-Berechnung:**
```
Kursziel = Ausbruchspunkt + Länge der Fahnenstange
Beispiel: Fahnenstange = 50 Punkte, Ausbruch bei 100 → Ziel 150
```

**Pennant (Wimpel)**
- Ähnlich Flag, aber Konsolidierung als symmetrisches Dreieck (konvergierende Linien)
- Ausbruch in Trendrichtung = Fortsetzungssignal
- Kursziel: Gleiche Methode wie Flag

**Triangle (Dreieck)**

*Ascending Triangle (Aufsteigendes Dreieck):*
- Obere Linie horizontal (Resistance), untere Linie steigt (HL)
- Bedeutung: Käufer akkumulieren, werden Resistance durchbrechen
- Ausbruch meist nach oben

*Descending Triangle (Absteigendes Dreieck):*
- Untere Linie horizontal (Support), obere Linie fällt (LH)
- Bedeutung: Verkäufer akkumulieren, werden Support durchbrechen
- Ausbruch meist nach unten

*Symmetrical Triangle (Symmetrisches Dreieck):*
- Beide Linien konvergieren (fallende Hochs, steigende Tiefs)
- Neutral: Ausbruch kann in beide Richtungen erfolgen
- Abwarten bis Ausbruch mit Volumenbestätigung

**Kursziel Dreieck:**
```
Kursziel = Ausbruchspunkt + Höhe der Dreiecksbasis
```

**Wedge (Keil)**
- Rising Wedge (aufsteigender Keil): Beide Linien steigen, obere flacher → bärisches Umkehrmuster
- Falling Wedge (fallender Keil): Beide Linien fallen, untere steiler → bullisches Umkehrmuster
- Achtung: Wedges können Fortsetzungs- ODER Umkehrmuster sein

**Rectangle (Rechteck)**
- Konsolidierung zwischen zwei horizontalen Levels (Support und Resistance)
- Entry: Ausbruch aus dem Rechteck (oben oder unten)
- Kursziel = Ausbruchspunkt + Höhe des Rechtecks

---

### 5.2 Umkehrmuster

**Head and Shoulders (H&S)**
```
Aufbau:
1. Linke Schulter: Hoch, dann Rücksetzer
2. Kopf (Head): Höheres Hoch, dann Rücksetzer zur Neckline
3. Rechte Schulter: Niedrigeres Hoch (≈ Höhe linke Schulter)
4. Ausbruch: Kurs schließt unter Neckline → Verkaufssignal
```
- Zuverlässigkeit: 83 % Erfolgsrate (gilt als verlässlichstes Umkehrmuster)
- **Kursziel:**
```
Kursziel = Neckline - (Kopf-Hoch - Neckline)
Beispiel: Kopf bei 120, Neckline bei 100 → Ziel: 100 - 20 = 80
```

**Inverse Head and Shoulders (Inv. H&S)**
- Spiegelung: Linke Schulter, tieferer Kopf, rechte Schulter
- Ausbruch über Neckline = Kaufsignal
- Kursziel: Neckline + (Neckline - Kopf-Tief)

**Double Top**
```
Aufbau: Zwei annähernd gleiche Hochs (±1 %) + Rücksetzer dazwischen
Bestätigung: Schließen unter das Zwischentief (Neckline)
Kursziel = Neckline - (Double Top Hoch - Neckline)
```
- Signal: Bärische Umkehr nach Aufwärtstrend

**Double Bottom**
```
Aufbau: Zwei annähernd gleiche Tiefs + Erholung dazwischen
Bestätigung: Schließen über das Zwischenhoch (Neckline)
Kursziel = Neckline + (Neckline - Double Bottom Tief)
```
- Signal: Bullische Umkehr nach Abwärtstrend

**Triple Top / Triple Bottom**
- Drei annähernd gleiche Hochs/Tiefs
- Stärker als Double Top/Bottom (mehr Tests = stärkere Zone)
- Gleiche Kursziel-Methodik wie Double Top/Bottom

---

## 6. Technische Indikatoren

### 6.1 ATR (Average True Range)

**Zweck:** Misst die durchschnittliche Kerzenspanne (Volatilität) über einen Zeitraum — keine Trendrichtung, nur Größe der Bewegung.

**Berechnung:**
```
True Range (TR) = Max von:
  1. High[t] - Low[t]              (aktuelle Kerzenrange)
  2. |High[t] - Close[t-1]|        (Gap nach oben)
  3. |Low[t] - Close[t-1]|         (Gap nach unten)

ATR(n) = Gleitender Durchschnitt der letzten n TRs
Standard: n = 14 Perioden

Wilder's Smoothing (bevorzugt):
ATR[t] = (ATR[t-1] × (n-1) + TR[t]) / n
```

**Python-Berechnung:**
```python
def calculate_atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr
```

**Interpretation:**
- Hoher ATR = Hohe Volatilität → Größerer SL nötig, kleinere Positionen
- Niedriger ATR = Geringe Volatilität → Engerer SL möglich, größere Positionen
- ATR-Anstieg: Trend beschleunigt oder Ausbruch
- ATR-Rückgang: Konsolidierung / Squeeze

**Verwendung für Stop Loss:**
```
Long SL = Entry - (ATR × Multiplier)
Short SL = Entry + (ATR × Multiplier)

Empfohlene Multiplier:
- Aggressiv: 1,5×
- Normal: 2,0× (Standard InvestApp)
- Konservativ: 3,0×
```

**Beispiel:** ATR = 15 Punkte, Entry Long bei 1500, Multiplier 2,0×
→ SL = 1500 - (15 × 2) = 1500 - 30 = 1470

---

### 6.2 RSI (Relative Strength Index)

**Berechnung:**
```
RSI = 100 - (100 / (1 + RS))
RS = Durchschnitt der Gewinne / Durchschnitt der Verluste (über n Perioden)
Standard: n = 14

Gewinne = Close - Close[t-1] (wenn positiv, sonst 0)
Verluste = Close[t-1] - Close (wenn positiv, sonst 0)
```

**Standardwerte:**
- Überkauft: RSI > 70
- Neutral: 30–70
- Überverkauft: RSI < 30

**Signaltypen:**

*Überkauft/Überverkauft:*
- RSI > 70 an Resistance → bärisches Warnsignal (kein Short allein daraus)
- RSI < 30 an Support → bullisches Warnsignal (kein Long allein daraus)
- In starken Trends kann RSI lange > 70 oder < 30 bleiben → allein nicht shortten/longen

*Bullische Divergenz:*
```
Kurs: Lower Low (neues Tief)
RSI:  Higher Low (kein neues Tief)
→ Momentum schwächt sich ab, mögliche Umkehr nach oben
```

*Bärische Divergenz:*
```
Kurs: Higher High (neues Hoch)
RSI:  Lower High (kein neues Hoch)
→ Momentum schwächt sich ab, mögliche Umkehr nach unten
```

*RSI Mittellinie (50):*
- RSI > 50 und steigend: Bullischer Trend bestätigt
- RSI < 50 und fallend: Bärischer Trend bestätigt
- RSI-Kreuzung der 50er-Linie: Trendwechsel-Frühindikator

**Agenten-Nutzung:**
```
RSI-Signal wird NUR als Bestätigung genutzt, nicht als primäres Signal.
Primär: Marktstruktur + Level
Sekundär: RSI-Divergenz als Bestätigung
```

---

### 6.3 MACD (Moving Average Convergence Divergence)

**Berechnung:**
```
MACD-Linie    = EMA(12) - EMA(26)
Signal-Linie  = EMA(9) der MACD-Linie
Histogramm    = MACD-Linie - Signal-Linie
```

**Signaltypen:**

*Crossovers:*
- MACD-Linie kreuzt Signal-Linie von unten → Kaufsignal
- MACD-Linie kreuzt Signal-Linie von oben → Verkaufssignal
- Qualität steigt, wenn Kreuzung unterhalb/oberhalb der Nulllinie

*Nulllinien-Kreuzung:*
- MACD kreuzt Nulllinie nach oben → Bullische Trendbestätigung
- MACD kreuzt Nulllinie nach unten → Bärische Trendbestätigung

*Histogramm:*
- Wachsendes Histogramm (positiv) = zunehmende bullische Stärke
- Schrumpfendes Histogramm = nachlassender Impuls (Warnsignal)
- Histogramm dreht negativ = möglicher Trendwechsel

*MACD-Divergenz:*
- Bullische Divergenz: Kurs Lower Low, MACD Higher Low
- Bärische Divergenz: Kurs Higher High, MACD Lower High
- Zuverlässiger als RSI-Divergenz bei Trendsignalen

**Agenten-Regel:** MACD-Crossover im Einklang mit 15m-Trendrichtung = Bestätigung. Gegen Trendrichtung = ignorieren.

---

### 6.4 Bollinger Bands

**Berechnung:**
```
Mittellinie (MB)  = SMA(20)
Oberes Band (UB)  = SMA(20) + (2 × Standardabweichung[20])
Unteres Band (LB) = SMA(20) - (2 × Standardabweichung[20])

Bandbreite = (UB - LB) / MB × 100 (%)
```

**Signaltypen:**

*Squeeze (Kompression):*
- Bandbreite sehr eng (unter dem 6-Monats-Tief der Bandbreite)
- Bedeutet: Sehr geringe Volatilität, Energie akkumuliert sich
- Kein Richtungshinweis — abwarten bis Ausbruch
- Nutzung: Volatility-Agent markiert Squeeze, wartet auf Expansion

*Expansion:*
- Bänder spreizen sich rapide → Ausbruch/starkes Momentum
- Preis schließt außerhalb des Bandes = starkes Momentum
- Warnung: Kann auch Überdehnung signalisieren (Reversion möglich)

*Bollinger-Bounce:*
- In Seitwärtsmärkten prellt Preis zwischen oberem und unterem Band
- Kauf am unteren Band, Verkauf am oberen Band
- Funktioniert NICHT in starken Trendphasen

*Band-Walk:*
- In starken Trends "läuft" der Kurs am oberen/unteren Band entlang
- Kurs bleibt konsistent über dem oberen Band = extrem starker Uptrend
- Nicht gegen Band-Walks traden

**%B-Indikator:**
```
%B = (Kurs - LB) / (UB - LB)
%B > 1: Kurs über oberem Band
%B = 1: Kurs am oberen Band
%B = 0.5: Kurs an Mittellinie
%B = 0: Kurs am unteren Band
%B < 0: Kurs unter unterem Band
```

---

### 6.5 Volume

**Bedeutung:** Volumen bestätigt oder widerlegt Preisbewegungen.

**Regeln:**

| Situation | Volumen | Bedeutung |
|---|---|---|
| Kursanstieg | Hoch | Starker Uptrend, bestätigt |
| Kursanstieg | Niedrig | Schwacher Anstieg, nicht nachhaltig |
| Kursrückgang | Hoch | Starker Downtrend, bestätigt |
| Kursrückgang | Niedrig | Schwacher Rückgang, mögl. Rebound |
| Ausbruch aus Zone | Hoch | Valider Ausbruch |
| Ausbruch aus Zone | Niedrig | Fehlausbruch möglich |
| Konsolidierung | Fallend | Normal, akkumuliert Energie |

**Volume Profile:**
- High Volume Nodes (HVN): Preisbereiche mit viel Handelsvolumen → starke S/R-Zones
- Low Volume Nodes (LVN): Preisbereiche mit wenig Volumen → Kurs bewegt sich schnell durch

**Agenten-Nutzung:**
```
Volumen-Multiplier (relativ zum 20-Perioden-Durchschnitt):
>200 %: Sehr hohes Volumen → starkes Signal
150–200 %: Hohes Volumen → Bestätigung
100–149 %: Normales Volumen → neutral
<100 %: Schwaches Volumen → Signal abwerten
```

---

## 7. Entry-Setups

### 7.1 Breakout-Entry

**Definition:** Einstieg beim Durchbruch einer validen Schlüsselzone mit Momentum.

**Vorgehen:**
1. Identifiziere valide Resistance/Support-Zone (Score ≥ 75 %)
2. Warte auf Schließen **außerhalb** der Zone (nicht Wick)
3. Bestätigung durch Volumen (> 150 % Durchschnitt)
4. Entry: Beim nächsten Open nach Bestätigungskerze ODER bei Retest

**Fehlausbrüche vermeiden:**
- Nie auf den Ausbruch der ersten Kerze traden (warten auf Close)
- Volumenbestätigung ist Pflicht
- Kleines Zeitfenster: Wenn nach 3–5 Kerzen kein Folgemomentum → Breakout ungültig
- Vorweggenommene Breakouts vermeiden (erst nach Close)

**Retest-Entry nach Breakout:**
```
1. Ausbruch über Resistance (schließt darüber)
2. Alte Resistance wird zu neuem Support
3. Kurs zieht zurück an diesen neuen Support
4. Bullische Bestätigungskerze an neuem Support
5. Entry mit engem SL unter neuem Support
```

---

### 7.2 Pullback/Retest-Entry

**Definition:** Einstieg nach einem Rücksetzer an einem validen Level oder gleitenden Durchschnitt.

**Vorgehen:**
1. Haupttrend ist etabliert (15m)
2. Preis setzt zurück zu: EMA 21/50, S/R-Zone, FVG, oder Trendlinie
3. Warte auf Bestätigungskerze (Hammer, Engulfing, Doji-Rejection)
4. Entry nach Bestätigungskerze

**Qualitätskriterien:**
- Rücksetzer nicht tiefer als 61,8 % des letzten Impulses
- Volumen beim Rücksetzer abnehmend (gesunde Korrektur)
- Bestätigungskerze mit Schluss über dem Level

**Stop Loss:** Unter das Tief des Rücksetzers (oder 1–2 × ATR unter Einstieg)

---

### 7.3 Rejection-Entry

**Definition:** Einstieg bei signifikanter Ablehnung (Rejection) an einer Schlüsselzone.

**Erkennungszeichen:**
- Langer Wick (≥ 2× Body) in Richtung der Zone
- Body schließt deutlich zurück (Rejection sichtbar)
- Klassische Kerzen: Hammer, Shooting Star, Engulfing, Doji

**Vorgehen:**
1. Kurs erreicht valide S/R-Zone
2. Ausbildung Rejection-Kerze (Close am oder nahe dem Zonenniveau)
3. Folgekerze bestätigt Richtung
4. Entry nach Bestätigungskerze

**Beispiel Short-Rejection:**
```
Kurs erreicht Resistance bei 1500
→ Lange obere Wick (bis 1510), Close bei 1495
→ Bearische Folgekerze
→ Short-Entry bei 1490, SL über 1510 (Wick-Hoch + Puffer)
```

---

### 7.4 Entry-Timing

**Wann warten:**
- Marktstruktur unklar / Seitwärtsmarkt ohne valide Grenzen
- Volatility-Agent signalisiert Freigabe NICHT (zu gering oder zu hoch)
- Macro-Agent: Hohe News-Risiken aktiv
- Kurs zwischen Zonen (kein klarer Kontext)
- Weniger als 30 Minuten bis zu einem High-Impact-News-Event

**Wann einsteigen:**
- Alle Agenten-Signale aligned (Trendrichtung, Level, Volatilität freigegeben)
- Confidence Score ≥ 80 %
- Entry-Timing: Bestätigungskerze vollständig ausgebildet (Close abwarten)
- Idealerweise während London oder New York Session (siehe Kapitel 10)

---

## 8. Risikomanagement

### 8.1 Stop Loss setzen

**Technischer Stop Loss (unter Struktur):**
```
Long:  SL = Letztes validiertes Swing Low - Puffer (0,1–0,3 % oder 1×ATR)
Short: SL = Letztes validiertes Swing High + Puffer
```

**ATR-basierter Stop Loss:**
```
Long SL  = Entry - (ATR(14) × 2,0)
Short SL = Entry + (ATR(14) × 2,0)
```

**Priorisierung:**
1. Technischer SL (unter Swing Low/High) hat Vorrang
2. ATR-SL als Minimum-SL wenn technisches Level zu weit entfernt
3. Wenn ATR-SL näher als technisches SL: Technisches SL verwenden

**Stop Loss Regeln:**
- Kein Trade mit SL > 3 % des Kontostands (absolutes Limit)
- SL darf nach Entry nicht vergrößert werden (Disziplin)
- SL kann nachgezogen werden (Trailing), aber nie ausgeweitet

---

### 8.2 Take Profit setzen

**Zonen-basierter Take Profit:**
- Nächste valide Resistance/Support-Zone in Trendrichtung
- Partial Exit (50 %) an erstem TP, Rest mit Trailing Stop

**CRV-Berechnung:**
```
CRV = (Take Profit - Entry) / (Entry - Stop Loss)

Minimum CRV für InvestApp: 1:2
Optimal: 1:3 oder besser

Beispiel Long:
Entry: 1500, SL: 1480, TP: 1560
CRV = (1560 - 1500) / (1500 - 1480) = 60 / 20 = 3,0
→ CRV 1:3 ✓
```

**Ablehnung wenn:** CRV < 1:2 → Trade verwerfen, egal wie gut das Setup aussieht

---

### 8.3 Positionsgröße berechnen

**1 %-Regel (Standard InvestApp):**
```
Risikokapital pro Trade = Kontostand × 0,01 (1 %)

Positionsgröße (Stücke/Contracts) = Risikokapital / (SL-Punkte × Punktwert)

Beispiel:
Konto: 50.000 €
Risikokapital: 50.000 × 0,01 = 500 €
SL-Distanz: 20 Punkte
Punktwert (z.B. Index-CFD): 1 € pro Punkt

Positionsgröße = 500 / (20 × 1) = 25 Contracts
```

**ATR-basierte Positionsgröße:**
```
Positionsgröße = Risikokapital / (ATR × Multiplier × Punktwert)

Beispiel:
Risikokapital: 500 €
ATR(14): 15 Punkte
Multiplier: 2,0×
Punktwert: 1 €

Positionsgröße = 500 / (15 × 2,0 × 1) = 500 / 30 ≈ 16 Contracts
```

**Wichtig:** Höhere Volatilität → kleiner ATR-adjustierter Positionsgröße → konsistentes Risiko

**Maximale Gesamtexposure:** Gleichzeitig maximal 3 % des Kontos in offenen Positionen riskieren.

---

### 8.4 Trailing Stop

**Methoden:**

*Strukturbasierter Trailing Stop:*
```
Bei Uptrend: SL nachziehen auf jeweils letztes validiertes Higher Low
→ Erst trailing, wenn sich neues HL ausgebildet hat
```

*ATR-basierter Trailing Stop:*
```
Trailing SL = Aktuelles High - (ATR × 2,0)  [für Long]
→ Täglich oder nach jeder neuen Kerze neu berechnen
```

*EMA-Trailing:*
```
SL = EMA(21) - Puffer (für Long)
→ Nachziehen sobald EMA steigt
```

**Trailing-Regel:** Trailing Stop nur in eine Richtung (niemals zurückziehen). Erst trailing wenn Trade profitabel ist (mind. 1:1 CRV erreicht).

---

## 9. Zeitrahmen-Analyse (Multi-Timeframe)

### 9.1 Top-Down-Analyse: 15m → 5m → Tick

**Schritt 1 — 15-Minuten-Chart (Trend-Agent):**
- Haupttrendrichtung bestimmen (HH/HL oder LH/LL)
- Trendstärke bewerten (Score 1–10)
- Schlüsselzonen markieren (S/R, FVG, Order Blocks)
- EMA 50 und 200 Bias bestimmen

**Schritt 2 — 5-Minuten-Chart (Entry-Agent, Feinstruktur):**
- Übergeordneter Bias aus 15m bleibt dominant
- Interne Struktur für Entry-Präzision analysieren
- Einstiegszone identifizieren (Pullback-Level)
- Entry-Muster erkennen (Rejection, Engulfing)

**Schritt 3 — Tick / 1-Minuten (Entry-Agent, Timing):**
- Finales Entry-Timing
- Bestätigungskerze abwarten
- SL-Platzierung auf Tick-Ebene optimieren

**Entscheidungsbaum:**
```
15m Uptrend?
  ├── Ja → Long-Bias aktiv
  │    └── 5m zeigt Pullback an Level?
  │         ├── Ja → 1m Bestätigungskerze?
  │         │    ├── Ja → ENTRY LONG ✓
  │         │    └── Nein → Warten
  │         └── Nein → Warten
  └── Nein → Kein Long-Signal
```

---

### 9.2 Welcher Timeframe wofür genutzt wird

| Zeitrahmen | Primäre Nutzung | Agent |
|---|---|---|
| 15m | Trendrichtung, Marktstruktur, Schlüsselzonen | Trend-Agent |
| 5m | Entry-Struktur, Pattern-Erkennung | Entry-Agent |
| 1m / Tick | Entry-Timing, SL-Präzision | Entry-Agent |
| Daily (1d) | Übergeordnete Bias, Wochenziele | Macro-Agent |

---

### 9.3 Konfluenz zwischen Timeframes

**Definition:** Wenn mehrere Zeitrahmen dasselbe Level oder dieselbe Richtung bestätigen, steigt die Zuverlässigkeit des Signals.

**Konfluenz-Matrix:**

| 15m | 5m | 1m | Score |
|---|---|---|---|
| Uptrend | Bullisch | Bullische Kerze | +30 % |
| Uptrend | Neutral | Bullische Kerze | +15 % |
| Neutral | Bullisch | Bullische Kerze | +10 % |
| Uptrend | Bearisch | – | -20 % |

**Konfluenz-Beispiel:**
```
15m: EMA 50 als Support, FVG vorhanden, Uptrend
5m:  Pullback genau in FVG + EMA 21
1m:  Bullisches Engulfing, Bestätigung

→ Triple-Timeframe-Confluence: Confidence Score +35 %
→ Sehr starkes Setup
```

---

## 10. Marktphasen & Volatilität

### 10.1 Session-Qualität

**Handelszeiten (UTC/MEZ):**

| Session | UTC | MEZ (Winter) | MESZ (Sommer) |
|---|---|---|---|
| Tokio | 00:00–09:00 | 01:00–10:00 | 02:00–11:00 |
| London | 08:00–17:00 | 09:00–18:00 | 10:00–19:00 |
| New York | 13:00–22:00 | 14:00–23:00 | 15:00–00:00 |
| London-NY-Overlap | 13:00–17:00 | 14:00–18:00 | 15:00–19:00 |

**Session-Bewertung:**

*London Session (08:00–17:00 UTC):*
- Höchste Liquidität, oft setzt hier die Tagesrichtung
- London High und Low werden oft als tägliche Liquiditätsgrenzen
- Starke Bewegungen in den ersten 2 Stunden (09:00–11:00 UTC)
- Verhalten: London setzt oft erstes High/Low des Tages → NY swept es oft

*New York Session (13:00–22:00 UTC):*
- Zweithöchste Liquidität, besonders 13:30 UTC (US-Marktöffnung)
- Starke Bewegungen bei 13:30 UTC (Economic Reports)
- NY Open oft Sweep von London High oder Low

*London-NY-Overlap (13:00–17:00 UTC):*
- Höchste kombinierte Liquidität des Tages
- Beste Bedingungen für Breakout- und Momentum-Strategien
- Idealfenster für InvestApp-Signale

*Tokio Session:*
- Geringe Liquidität für EUR/USD und US-Indizes
- Oft Konsolidierung, keine aktiven Signale empfohlen

**Volatility-Agent Regel:**
```
Session-Qualität-Score:
London-NY-Overlap: 100 (Freigabe)
London Open:        85 (Freigabe)
NY Open:            90 (Freigabe)
London Mid:         70 (Freigabe mit Einschränkungen)
NY Mid:             70 (Freigabe mit Einschränkungen)
Tokio:              30 (kein Signal)
Pre-Market:         20 (kein Signal)
```

---

### 10.2 ATR-Filter

**Markt zu ruhig (Unter-Volatilität):**
```
Bedingung: ATR(14) < 50 % des 20-Perioden-ATR-Durchschnitts
→ Signal: "Markt zu ruhig"
→ Konsequenz: Volatility-Agent verweigert Freigabe
→ Grund: SL muss zu eng gesetzt werden, Slippage-Risiko hoch
```

**Markt zu chaotisch (Über-Volatilität):**
```
Bedingung: ATR(14) > 200 % des 20-Perioden-ATR-Durchschnitts
→ Signal: "Markt zu volatil / chaotisch"
→ Konsequenz: Volatility-Agent verweigert Freigabe (außer bei spezifischer Freigabe)
→ Grund: Hohe Slippage, Levels werden übersprungen, SL zu weit
```

**Normalzustand (Freigabe):**
```
Bedingung: 50 % < ATR(14) < 200 % des ATR-Durchschnitts
→ Volatility-Agent gibt Freigabe
```

**Python-Implementierung:**
```python
def volatility_check(atr_current, atr_avg_20):
    ratio = atr_current / atr_avg_20
    if ratio < 0.50:
        return "TOO_QUIET", False
    elif ratio > 2.00:
        return "TOO_VOLATILE", False
    else:
        return "NORMAL", True
```

---

### 10.3 Compression vs. Expansion

**Compression (Kompression):**
- Bollinger-Band-Squeeze aktiv
- ATR auf Mehrwochen-Tief
- Kerzenranges klein und ähnlich groß
- Volumen abnehmend oder konstant niedrig
- **Bedeutung:** Energie akkumuliert sich, großer Move steht bevor
- **Agenten-Verhalten:** Kein Entry, warten auf Expansion mit Richtungsbestätigung

**Expansion:**
- Bollinger Bänder öffnen sich rapide
- ATR steigt stark an
- Kerzenranges deutlich größer als im Durchschnitt
- Volumen steigt
- **Bedeutung:** Trend läuft oder Ausbruch findet statt
- **Agenten-Verhalten:** Entry-Setups im Trend erlaubt (mit Level-Bestätigung)

**Marktphasen-Zyklus:**
```
Accumulation (Compression) → Breakout → Trend (Expansion) → Distribution → Reversal → Accumulation...
```

---

## 11. Yahoo Finance — Datenverfügbarkeit

### 11.1 Überblick yfinance Python-Library

`yfinance` ist die Standard-Python-Library für den Zugriff auf Yahoo Finance-Daten. Sie eignet sich für historische Kursdaten, Fundamentaldaten und Marktinformationen.

**Installation:**
```bash
pip install yfinance pandas numpy
```

**Grundlegende Nutzung:**
```python
import yfinance as yf
import pandas as pd

# Einzelner Ticker
ticker = yf.Ticker("AAPL")

# Download über yf.download (für mehrere Ticker und Zeiträume)
data = yf.download("AAPL", start="2024-01-01", end="2024-12-31", interval="15m")
```

---

### 11.2 Verfügbare Daten-Typen

**Historische OHLCV-Daten:**
```python
# Tages-Daten (unbegrenzt historisch)
df = yf.download("AAPL", period="2y", interval="1d")
# Spalten: Open, High, Low, Close, Adj Close, Volume

# 15-Minuten-Daten (max. 60 Tage)
df = yf.download("AAPL", period="60d", interval="15m")

# 5-Minuten-Daten (max. 60 Tage)
df = yf.download("AAPL", period="60d", interval="5m")

# 1-Minuten-Daten (max. 7 Tage)
df = yf.download("AAPL", period="7d", interval="1m")
```

**Ticker-spezifische Informationen:**
```python
ticker = yf.Ticker("AAPL")

# Fundamentaldaten
info = ticker.info          # KGV, Marktkapitalisierung, 52W-High/Low, etc.

# Finanzdaten
financials = ticker.financials          # Gewinn- und Verlustrechnung
balance_sheet = ticker.balance_sheet   # Bilanz
cash_flow = ticker.cashflow             # Cashflow-Rechnung

# Dividenden und Splits
dividends = ticker.dividends
splits = ticker.splits

# Optionen
options_dates = ticker.options  # verfügbare Verfallsdaten
```

---

### 11.3 Verfügbare Intervalle (Übersicht)

| Interval | Max. Historisch | Kommentar |
|---|---|---|
| 1m | 7 Tage | Sehr kurz, Tick-Näherung |
| 2m | 60 Tage | Selten genutzt |
| 5m | 60 Tage | Entry-Analyse |
| 15m | 60 Tage | Haupt-Trendanalyse |
| 30m | 60 Tage | Mittelfristig |
| 60m / 1h | 730 Tage | Mittelfristig |
| 1d | Unbegrenzt | Tagesanalyse, Hauptreferenz |
| 5d | Unbegrenzt | Wochenkerzen |
| 1wk | Unbegrenzt | Wochenanalyse |
| 1mo | Unbegrenzt | Monatsanalyse |
| 3mo | Unbegrenzt | Quartalsanalyse |

---

### 11.4 OHLCV-Daten abrufen und Indikatoren berechnen

**Tageshoch/Tief berechnen:**
```python
import yfinance as yf
import pandas as pd

def get_daily_levels(symbol: str) -> dict:
    """Holt das Tageshoch, -tief und Vortageslevel."""
    df = yf.download(symbol, period="5d", interval="1d")

    today_high = df["High"].iloc[-1]
    today_low = df["Low"].iloc[-1]
    prev_high = df["High"].iloc[-2]
    prev_low = df["Low"].iloc[-2]

    return {
        "symbol": symbol,
        "today_high": float(today_high),
        "today_low": float(today_low),
        "prev_day_high": float(prev_high),
        "prev_day_low": float(prev_low),
        "weekly_high": float(df["High"].tail(5).max()),
        "weekly_low": float(df["Low"].tail(5).min())
    }
```

**ATR berechnen:**
```python
def calculate_atr(symbol: str, interval: str = "15m", period: int = 14) -> float:
    df = yf.download(symbol, period="30d", interval=interval)

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()

    return float(atr.iloc[-1])
```

**RSI berechnen:**
```python
def calculate_rsi(symbol: str, interval: str = "15m", period: int = 14) -> float:
    df = yf.download(symbol, period="30d", interval=interval)
    close = df["Close"]

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return float(rsi.iloc[-1])
```

**EMA berechnen:**
```python
def calculate_emas(symbol: str, interval: str = "15m") -> dict:
    df = yf.download(symbol, period="60d", interval=interval)
    close = df["Close"]

    return {
        "ema_9":   float(close.ewm(span=9,   adjust=False).mean().iloc[-1]),
        "ema_21":  float(close.ewm(span=21,  adjust=False).mean().iloc[-1]),
        "ema_50":  float(close.ewm(span=50,  adjust=False).mean().iloc[-1]),
        "ema_200": float(close.ewm(span=200, adjust=False).mean().iloc[-1])
    }
```

---

### 11.5 Limitierungen und wichtige Hinweise

**Zeitliche Limitierungen:**

| Problem | Details |
|---|---|
| Intraday-Limit | Daten < 1d nur für max. 60 Tage verfügbar |
| 1m-Limit | Nur 7 Tage für 1-Minuten-Daten |
| Kein Tick-Daten | Keine echten Tick-Daten via yfinance |
| Datenverzögerung | Ca. 15 Minuten Verzögerung bei kostenlosem API-Zugang |
| Keine Echtzeit-Kurse | Nur verzögerte Quotes (kein Live-Streaming) |

**Datenlücken:**
- Wochenenden und Feiertage (marktgeschlossen) fehlen im Datensatz
- Prä-Markt und After-Hours-Daten sind begrenzt verfügbar
- Yfinance-Daten können gelegentlich unvollständig sein (Fehlerbehandlung empfohlen)

**Stabilitätshinweise:**
- Yahoo Finance ändert seine API regelmäßig → yfinance-Updates prüfen
- Rate Limiting: Nicht zu viele Requests in kurzer Zeit
- Empfehlung: Caching von Daten um Requests zu minimieren

**Empfohlene Fehlerbehandlung:**
```python
def safe_download(symbol: str, **kwargs) -> pd.DataFrame | None:
    try:
        df = yf.download(symbol, **kwargs, progress=False)
        if df.empty:
            raise ValueError(f"Keine Daten für {symbol}")
        return df
    except Exception as e:
        print(f"Fehler beim Download von {symbol}: {e}")
        return None
```

**Alternative Datenquellen für Echtzeit:**
- Interactive Brokers API (für Live-Trading)
- Alpha Vantage (kostenloser API-Key für Echtzeit mit Delay)
- Polygon.io (kostenpflichtig, professionell)

---

## Anhang: Agenten-Schnellreferenz

### Mindest-Checkliste vor Signal-Ausgabe

```
✓ Marktstruktur bestimmt (HH/HL oder LH/LL oder Seitwärts)
✓ Haupttrendrichtung (15m) klar
✓ Volatility-Freigabe: Ja
✓ Macro-Freigabe: Ja (keine blockierenden News)
✓ Schlüsselzone identifiziert (Score ≥ 75 %)
✓ Entry-Typ definiert (Breakout / Pullback / Rejection)
✓ Bestätigungskerze vorhanden
✓ SL platziert (technisch oder ATR-basiert)
✓ TP berechnet (min. CRV 1:2)
✓ Positionsgröße berechnet (max. 1 % Risiko)
✓ Confidence Score ≥ 80 %
```

### Minimaler Output pro Signal

```json
{
  "symbol": "AAPL",
  "richtung": "long" | "short",
  "trendstatus": "uptrend" | "downtrend" | "seitwärts",
  "makrostatus": "freigegeben" | "blockiert",
  "entry_preis": 150.00,
  "stop_loss": 145.00,
  "take_profit": 160.00,
  "crv": 2.0,
  "positionsgroesse": 10,
  "confidence_score": 82,
  "begruendung": "Bullisches Engulfing an EMA 50 + FVG im 15m-Uptrend",
  "status": "freigegeben" | "verworfen"
}
```

---

*Dieses Handbuch ist die operative Grundlage für alle KI-Agenten der InvestApp-Pipeline. Es ist als lebendiges Dokument zu verstehen und wird bei Bedarf aktualisiert.*

---

## Abschnitt A: Fundamentalanalyse

Fundamentalanalyse bewertet den **inneren Wert** eines Unternehmens auf Basis von Finanzdaten, Geschäftsmodell und Marktstellung. Sie ergänzt die technische Analyse um eine langfristige Perspektive und hilft, Über- oder Unterbewertungen zu erkennen.

---

### Warren Buffett – Value Investing

#### Grundphilosophie

Warren Buffett, Schüler von Benjamin Graham, vertritt das **Value Investing**: Aktien werden wie Unternehmensbeteiligungen betrachtet, nicht als Kurssymbole. Ziel ist es, Unternehmen mit dauerhaftem Wettbewerbsvorteil (Moat) unter ihrem inneren Wert zu kaufen und langfristig zu halten.

#### Intrinsischer Wert (Intrinsic Value)

Der intrinsische Wert ist der Barwert aller zukünftigen Cashflows, die ein Unternehmen generiert. Er wird nicht exakt berechnet, sondern geschätzt – daher ist die **Margin of Safety** entscheidend.

**Faustregel:** Kaufe nur, wenn der Marktpreis mindestens 20–30 % unter dem geschätzten inneren Wert liegt.

#### Margin of Safety

Das Sicherheitspuffer-Prinzip: Selbst wenn die eigene Bewertung leicht falsch ist, schützt die Marge vor großen Verlusten. Je höher die Unsicherheit beim Unternehmen, desto größer die geforderte Margin of Safety.

#### Burggraben (Economic Moat)

Ein Moat ist ein dauerhafter Wettbewerbsvorteil, der Konkurrenten auf Abstand hält:

| Moat-Typ | Beispiel |
|---|---|
| Kostenführerschaft | Amazon, Costco |
| Netzwerkeffekte | Visa, Facebook |
| Immaterielle Assets (Marke, Patent) | Coca-Cola, Apple |
| Wechselkosten | Microsoft, SAP |
| Regulatorischer Vorteil | lokale Versorger |

**Ohne Moat:** Kein langfristiger Vorteil, Gewinne erodieren durch Wettbewerb.

#### DCF-Bewertung (Discounted Cash Flow)

Methode zur Schätzung des intrinsischen Werts:

```
Intrinsischer Wert = Σ (FCF_t / (1 + r)^t) + Terminalwert
```

- **FCF** = Free Cash Flow des Unternehmens
- **r** = Diskontierungszinssatz (WACC oder geforderte Rendite, z. B. 10 %)
- **Terminalwert** = Wert nach dem Prognosehorizont (oft ewige Rente)

**Buffetts vereinfachter Ansatz:** Nimm den aktuellen Owner Earnings (Nettogewinn + Abschreibungen − Investitionen) und multipliziere mit einem angemessenen KGV oder Kapitalisierungsfaktor.

#### Wichtige Kennzahlen nach Buffett

| Kennzahl | Kürzel | Beschreibung | Buffetts Richtwert |
|---|---|---|---|
| Kurs-Gewinn-Verhältnis | KGV | Marktpreis / Gewinn je Aktie | < 15 für Value |
| Kurs-Buchwert-Verhältnis | KBV | Marktpreis / Buchwert je Aktie | < 1,5 bevorzugt |
| Return on Equity | ROE | Jahresgewinn / Eigenkapital | > 15 % p.a. |
| Free Cash Flow Margin | FCF% | FCF / Umsatz | > 10 % |
| Schulden/Eigenkapital | D/E | Verschuldungsgrad | < 0,5 |
| EPS-Wachstum | — | Gewinnwachstum je Aktie (5–10 J.) | > 10 % p.a. |

#### Wann kaufen / wann verkaufen?

**Kaufen wenn:**
- Marktpreis < intrinsischer Wert − Margin of Safety
- ROE konstant > 15 % über mehrere Jahre
- Moat klar erkennbar und stabil
- Management integer und aktionärsfreundlich
- Einfaches, verständliches Geschäftsmodell

**Verkaufen wenn:**
- Kurs übersteigt deutlich den intrinsischen Wert
- Fundamentale Verschlechterung (Moat bricht weg)
- Bessere Gelegenheit identifiziert
- Ursprüngliche Kaufthese ist widerlegt

---

### Peter Lynch – "Invest in What You Know"

#### Grundphilosophie

Peter Lynch, ehemaliger Fondsmanager des Fidelity Magellan Fund (1977–1990, Rendite ~29 % p.a.), glaubt daran, dass Privatanleger einen Informationsvorsprung gegenüber Institutionellen haben: Sie erleben neue Produkte und Trends im Alltag früher.

**Kernprinzip:** Beobachte, was du kaufst, nutzt und schätzt – darin liegen oft die besten Investitionen.

#### PEG-Ratio

Die wichtigste Bewertungskennzahl nach Lynch:

```
PEG = KGV / jährliches Gewinnwachstum (%)
```

| PEG-Wert | Bewertung |
|---|---|
| < 1,0 | günstig bewertet, potenziell attraktiv |
| = 1,0 | fair bewertet |
| > 1,5 | teuer, Vorsicht |
| > 2,0 | erheblich überbewertet |

**Beispiel:** KGV = 20, Gewinnwachstum = 25 % → PEG = 20/25 = 0,8 → attraktiv

#### Sechs Aktienkategorien nach Lynch

| Kategorie | Wachstum | Merkmale | Strategie |
|---|---|---|---|
| **Slow Growers** | 2–4 % p.a. | reife Branchen, hohe Dividenden | Dividendenstrategie, kein großes KGV |
| **Stalwarts** | 10–12 % p.a. | große, stabile Unternehmen | 30–50 % Kurspotenzial anstreben, dann verkaufen |
| **Fast Growers** | > 20 % p.a. | kleine, dynamische Wachstumsfirmen | Kernbereich für Lynch, PEG < 1 achten |
| **Cyclicals** | variabel | abhängig vom Konjunkturzyklus | Timing kritisch: Früh im Zyklus kaufen |
| **Turnarounds** | n.a. | Krisenunternehmen in Erholung | Hohes Risiko, hohe Rendite bei Erfolg |
| **Asset Plays** | n.a. | versteckte Vermögenswerte (Immob., Marken) | KBV, Substanzwert analysieren |

#### Ten Bagger Philosophie

Lynch prägte den Begriff „Ten Bagger" (Aktie, die sich verzehnfacht). Merkmale:

- Kleines, übersehenes Unternehmen
- Skalierbares Geschäftsmodell
- Geringe Analystenabdeckung
- Noch in frühem Wachstumsstadium
- Starke Nachfrage im Alltag erkennbar

**Geduld ist Pflicht:** Ten Bagger entstehen über 5–10 Jahre, nicht über Nacht.

#### Lynches Verkaufsregeln

- **Verkaufe Stalwarts**, wenn sie 30–50 % gestiegen sind
- **Verkaufe Fast Growers**, wenn das Gewinnwachstum nachlässt oder der PEG > 1,5
- **Halte Turnarounds**, bis die Wende abgeschlossen ist
- **Verkaufe nicht**, weil der Kurs gefallen ist – prüfe, ob die These noch stimmt
- **Verkaufe**, wenn du ein besseres Investment findest

---

### Howard Marks – Marktzyklen und Second-Level Thinking

#### Grundphilosophie

Howard Marks, Mitgründer von Oaktree Capital, ist bekannt für seine tiefgründigen Memos über Marktpsychologie und Risikosteuerung. Sein Fokus liegt nicht auf dem „Was?", sondern auf dem „Wann?" und „Wie viel Risiko?"

#### Second-Level Thinking

**First-Level Thinking:** „Das Unternehmen wächst stark → Aktie kaufen."

**Second-Level Thinking:** „Das Unternehmen wächst stark, aber alle erwarten das bereits. Ist der Preis schon zu hoch? Was passiert, wenn das Wachstum auch nur leicht enttäuscht?"

Marks fordert: Denke immer eine Ebene tiefer als der Konsens. Nur wer anders und richtiger denkt als die Masse, erzielt überdurchschnittliche Renditen.

#### Die Pendel-Metapher

Märkte pendeln zwischen zwei Extremen – und verweilen selten in der Mitte:

```
Euphorie / Gier ←————————→ Panik / Angst
Überbewertung  ←————————→ Unterbewertung
Risikobereitschaft ←——→ Risikoaversion
```

**Marks' Regel:** Wenn das Pendel an einem Extrem ist, positioniere dich für die Rückkehr zur Mitte.

#### Die drei Marktzyklen

**1. Emotionszyklus:**
- Euphorie → Übertreibung → Crash → Depression → Erholung
- Merkmale der Spitze: "Diesmal ist es anders", hohe Leverage, niedrige Risikowahrnehmung

**2. Kreditmarktzyklus:**
- Kreditvergabe wird leichter → mehr Risiken eingegangen → erste Ausfälle → Kreditklemme → Bereinigung
- Indikator: Kreditkonditionen, Spreads (High Yield vs. Investment Grade)

**3. Gewinnzyklus:**
- Unternehmensgewinne folgen dem Konjunkturzyklus mit Lag
- In der Spätphase: Gewinne hoch, aber Wachstum verlangsamt sich → Bewertungsrisiko

#### Risikowahrnehmung nach Marks

Paradox: **Wenn das Risiko am niedrigsten wahrgenommen wird, ist es oft am höchsten** – weil alle sorglos handeln und Preise übertrieben sind.

**Investitionsverhalten je nach Zyklusphase:**

| Phase | Marktstimmung | Marks' Empfehlung |
|---|---|---|
| Früh im Zyklus | Pessimismus, günstige Preise | Offensiv investieren, Qualität kaufen |
| Mitte | Normalität, faire Preise | Selektiv vorgehen |
| Spät im Zyklus | Euphorie, teure Bewertungen | Defensiv, Cash aufbauen, Risiko reduzieren |
| Krise | Panik, Ausverkauf | Mutig kaufen (wenn Liquidität vorhanden) |

#### Positionierung im Zyklus

Marks fragt immer: **„Wo stehen wir im Zyklus?"**

Checkliste zur Zyklusbewertung:
- [ ] Sind Kredite leicht verfügbar? → Spätzyklus-Signal
- [ ] Reden Laien über ihre Gewinne? → Überhitzung
- [ ] Werden riskante Assets wie sichere behandelt? → Übertreibung
- [ ] Sind Bewertungen historisch hoch? → Vorsicht
- [ ] Herrscht allgemeiner Pessimismus? → Kaufgelegenheit

---

### yfinance – Fundamentaldaten mit Python abrufen

`yfinance` ist die primäre Datenbasis der InvestApp für Fundamentaldaten.

#### Installation

```bash
pip install yfinance
```

#### Grundlegende Kennzahlen abrufen

```python
import yfinance as yf

ticker = yf.Ticker("AAPL")

# Alle verfügbaren Infos (KGV, KBV, EPS, Dividende, etc.)
info = ticker.info

# Wichtige Fundamentalkennzahlen
kgv = info.get("trailingPE")          # Kurs-Gewinn-Verhältnis (trailing)
kgv_forward = info.get("forwardPE")   # KGV auf Basis Gewinnschätzung
kbv = info.get("priceToBook")         # Kurs-Buchwert-Verhältnis
eps = info.get("trailingEps")         # Gewinn je Aktie (letztes Jahr)
eps_forward = info.get("forwardEps")  # Geschätzter EPS
roe = info.get("returnOnEquity")      # ROE (als Dezimalzahl, z.B. 0.15 = 15%)
fcf = info.get("freeCashflow")        # Free Cash Flow (absolut)
dividende = info.get("dividendYield") # Dividendenrendite (Dezimalzahl)
marktkapitalisierung = info.get("marketCap")

print(f"KGV: {kgv:.2f}")
print(f"KBV: {kbv:.2f}")
print(f"EPS: {eps:.2f}")
print(f"ROE: {roe*100:.1f}%")
print(f"FCF: {fcf:,.0f} USD")
print(f"Dividende: {dividende*100:.2f}%")
```

#### PEG-Ratio berechnen

```python
import yfinance as yf

def berechne_peg(symbol: str) -> float | None:
    ticker = yf.Ticker(symbol)
    info = ticker.info

    kgv = info.get("trailingPE")
    # Gewinnwachstum: yfinance liefert earningsGrowth als Dezimalzahl
    gewinnwachstum = info.get("earningsGrowth")  # z.B. 0.25 = 25%

    if kgv and gewinnwachstum and gewinnwachstum > 0:
        peg = kgv / (gewinnwachstum * 100)
        return round(peg, 2)
    return None

peg = berechne_peg("AAPL")
print(f"PEG-Ratio: {peg}")
```

#### Free Cash Flow aus Cashflow-Statement

```python
import yfinance as yf

ticker = yf.Ticker("MSFT")

# Cashflow-Statement (jährlich)
cashflow = ticker.cashflow
print(cashflow)

# Free Cash Flow manuell berechnen
operating_cf = cashflow.loc["Operating Cash Flow"].iloc[0]
capex = cashflow.loc["Capital Expenditure"].iloc[0]  # negativ
fcf = operating_cf + capex  # capex ist negativ, daher Addition
print(f"Free Cash Flow: {fcf:,.0f} USD")
```

#### Bilanz und Verschuldung

```python
import yfinance as yf

ticker = yf.Ticker("TSLA")
bilanz = ticker.balance_sheet

eigenkapital = bilanz.loc["Stockholders Equity"].iloc[0]
gesamtschulden = bilanz.loc["Total Debt"].iloc[0]
verschuldungsgrad = gesamtschulden / eigenkapital
print(f"Verschuldungsgrad (D/E): {verschuldungsgrad:.2f}")
```

#### Mehrere Aktien vergleichen

```python
import yfinance as yf
import pandas as pd

symbole = ["AAPL", "MSFT", "GOOGL", "AMZN"]
daten = []

for symbol in symbole:
    info = yf.Ticker(symbol).info
    daten.append({
        "Symbol": symbol,
        "KGV": info.get("trailingPE"),
        "KBV": info.get("priceToBook"),
        "ROE %": round(info.get("returnOnEquity", 0) * 100, 1),
        "FCF (Mrd)": round(info.get("freeCashflow", 0) / 1e9, 2),
        "Dividende %": round(info.get("dividendYield", 0) * 100, 2),
    })

df = pd.DataFrame(daten).set_index("Symbol")
print(df.to_string())
```

---

## Abschnitt B: Momentum- und Trendhandel nach Mario Lüddemann

### Grundphilosophie

Mario Lüddemann ist einer der bekanntesten deutschen Trader und Buchautoren im Bereich technischer Analyse und Momentumtrading. Seine Strategie basiert auf dem Prinzip: **Folge der Stärke, meide die Schwäche.**

**Kernüberzeugungen:**
- Stärke zieht Stärke an – starke Aktien tendieren dazu, weiter zu steigen
- Verluste begrenzen ist wichtiger als Gewinne maximieren
- Disziplin und Regelwerk schlagen jede Intuition
- Der Markt hat immer recht – nie gegen den Trend handeln

### Relative Stärke

Die relative Stärke misst, wie gut sich eine Aktie im Vergleich zum Gesamtmarkt (z.B. S&P 500 oder DAX) entwickelt.

**Berechnungsprinzip:**
```
Relative Stärke = Performance Aktie / Performance Index (gleicher Zeitraum)
```

**Interpretation:**
- RS > 1,0 → Aktie ist stärker als der Index → bullishes Signal
- RS < 1,0 → Aktie ist schwächer → meiden oder Short-Kandidat
- RS-Ranking: Bestes 20 % des Universums = Kaufliste

**In der InvestApp:**
```python
import yfinance as yf
import pandas as pd

def berechne_relative_staerke(symbol: str, benchmark: str = "^GSPC", periode: int = 90) -> float:
    """Relative Stärke einer Aktie gegenüber dem Benchmark."""
    aktie = yf.Ticker(symbol).history(period=f"{periode}d")["Close"]
    index = yf.Ticker(benchmark).history(period=f"{periode}d")["Close"]

    rendite_aktie = (aktie.iloc[-1] / aktie.iloc[0]) - 1
    rendite_index = (index.iloc[-1] / index.iloc[0]) - 1

    if rendite_index != 0:
        return round(rendite_aktie / rendite_index, 2)
    return 0.0
```

### Volumen als Bestätigungssignal

Lüddemann misst dem Volumen hohe Bedeutung bei. Kursbewegunungen ohne Volumen sind nicht vertrauenswürdig.

**Regeln:**
- Ausbruch mit **überdurchschnittlichem Volumen** (> 1,5× Durchschnitt) → bestätigt
- Ausbruch mit normalem Volumen → Fakeout-Risiko hoch
- Hohe Volumenspitzen an Wendepunkten → mögliche Trendwende

**Volumen-Analyse:**
```python
import yfinance as yf

def pruefe_volumen_bestaetigung(symbol: str, faktor: float = 1.5) -> dict:
    df = yf.Ticker(symbol).history(period="60d")
    durchschnitt = df["Volume"].rolling(20).mean()
    aktuell = df["Volume"].iloc[-1]
    bestaetigt = aktuell > faktor * durchschnitt.iloc[-1]

    return {
        "symbol": symbol,
        "volumen_aktuell": int(aktuell),
        "volumen_durchschnitt_20": int(durchschnitt.iloc[-1]),
        "faktor": round(aktuell / durchschnitt.iloc[-1], 2),
        "bestaetigt": bestaetigt
    }
```

### Ausbrüche aus Konsolidierungszonen

#### Konsolidierungszone erkennen

Eine Konsolidierungszone entsteht, wenn der Kurs sich über mehrere Kerzen/Tage innerhalb einer engen Range bewegt (Widerstand und Unterstützung nahe beieinander).

**Merkmale:**
- Sinkende Volatilität (ATR nimmt ab)
- Volumen geht zurück
- EMA flacht ab
- Kurs pendelt zwischen klarem High und Low

#### Ausbruchs-Setup

```
Bedingung für Long-Ausbruch:
1. Kurs schließt über dem Konsolidierungs-High
2. Volumen > 1,5× Durchschnitt
3. Relative Stärke > 1,0 (Aktie stärker als Markt)
4. Kein negativer Makro-Kontext

Entry: Über dem Ausbruchs-Candle-High
SL: Unter dem Konsolidierungs-Low
TP: Mindestens 2× Risikoabstand (CRV ≥ 2:1)
```

#### Gap-Trading

Lüddemann handelt gezielt Gaps (Kurslücken), besonders nach Earnings oder News:

- **Gap up mit starkem Volumen** → Einstieg im ersten Pullback (Fill-Test des Gap-Rands)
- **Gap down mit Volumen** → Short-Setup analog
- **Kleines Gap ohne Volumen** → ignorieren, wird meist geschlossen

**Wichtig:** Nur Gaps im Trendrichtung traden. Ein Gap gegen den Trend ist ein Warnsignal, kein Setup.

#### Continuation Setups (Trendfortsetzung)

In einem intakten Aufwärtstrend nach Rücksetzer einsteigen:

```
Continuation Setup – Kriterien:
1. Trend klar nach oben (höhere Hochs, höhere Tiefs)
2. Rücksetzer auf EMA 20 oder EMA 50 (Pullback)
3. Volumen während Rücksetzer sinkt (gesunde Konsolidierung)
4. Bestätigungskerze (z.B. Hammer, Bullish Engulfing) am Level
5. Volumen beim Rebound steigt wieder

Entry: Über dem Hoch der Bestätigungskerze
SL: Unter dem Rücksetzungs-Tief
TP: Vorheriges Hoch oder Fibonacci-Extension (1,618)
```

### Positionsgröße

Lüddemann arbeitet mit festem Risiko pro Trade:

```
Risiko pro Trade = Kontogröße × Risikoprozent (z.B. 1 %)

Positionsgröße (Stück) = Risiko pro Trade / (Entry - SL)
```

**Beispiel:**
- Konto: 10.000 €, Risiko: 1 % → 100 € Risiko
- Entry: 50 €, SL: 48 € → Abstand = 2 €
- Positionsgröße: 100 / 2 = **50 Stück**

```python
def berechne_positionsgroesse(kontogroesse: float, risiko_prozent: float,
                               entry: float, stop_loss: float) -> int:
    risiko_euro = kontogroesse * (risiko_prozent / 100)
    abstand = abs(entry - stop_loss)
    if abstand == 0:
        return 0
    return int(risiko_euro / abstand)
```

### Trailing Stops – Gewinne laufen lassen

Lüddemann betont: **Verluste hart begrenzen, Gewinne laufen lassen.**

**Trailing Stop Methoden:**

1. **ATR-basiert:** SL = Kurs − (Faktor × ATR), Faktor typisch 2–3
2. **EMA-Trailing:** SL zieht mit dem EMA 20 nach (Schlusskurs unter EMA → Ausstieg)
3. **Manuelles Nachziehen:** Bei jedem neuen Hoch den SL auf das letzte Tief setzen

```python
import yfinance as yf
import pandas as pd

def berechne_atr_trailing_stop(symbol: str, faktor: float = 2.5, periode: int = 14) -> dict:
    df = yf.Ticker(symbol).history(period="60d")
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # ATR berechnen
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(periode).mean().iloc[-1]
    aktueller_kurs = close.iloc[-1]
    trailing_stop = aktueller_kurs - (faktor * atr)

    return {
        "symbol": symbol,
        "kurs": round(aktueller_kurs, 4),
        "atr": round(atr, 4),
        "trailing_stop": round(trailing_stop, 4)
    }
```

### Psychologie: Disziplin und typische Fehler

#### Lüddemanns Psychologie-Prinzipien

1. **Regelwerk ist nicht verhandelbar:** Entweder du folgst dem System oder du folgst ihm nicht – kein "dieses Mal ist es anders."
2. **Emotionen vom Trading trennen:** Führe ein Trading-Tagebuch, analysiere Entscheidungen rational.
3. **Verluste akzeptieren:** Jeder Trade kann ein Verlierer sein – das ist kein Fehler, solange der Prozess stimmt.
4. **Gier kontrollieren:** Positionsgrößen nicht erhöhen, weil man "sicher" ist – die Regeln gelten immer.
5. **FOMO vermeiden:** Verpasste Trades werden nicht hinterhergejagt.

#### Typische Fehler (Lüddemann's Liste)

| Fehler | Auswirkung | Korrektur |
|---|---|---|
| SL zu eng gesetzt | Wird durch normales Rauschen ausgestoppt | SL technisch setzen, nicht zu gierig |
| Zu früh Gewinne sichern | Verpasst die besten Moves | Trailing Stop nutzen, nicht manuell schließen |
| Nachrichten überbewerten | Emotional handeln | System schlägt Nachrichten |
| Verluste aussitzen | Kleine Verluste werden groß | SL IMMER respektieren |
| Overtrading | Zu viele Trades, keine Selektion | Nur A+-Setups handeln |
| Kein Plan vor Trade | Improvisiert im Trade | Setup vor Entry vollständig definieren |
| Rache-Trades | Nach Verlust überstürzt einsteigen | Pause machen, System neu evaluieren |

---

## Abschnitt C: Nachrichtenquellen

### finanznachrichten.de

#### Überblick

`finanznachrichten.de` ist eines der meistgenutzten deutschen Finanzportale für aktuelle Unternehmensnachrichten, Analystenratings und Marktberichte.

#### Aufbau und relevante Rubriken

| Rubrik | URL-Pfad | Inhalt |
|---|---|---|
| Startseite / Topliste | `/` | Meistgelesene Nachrichten, Marktüberblick |
| Aktuelle Meldungen | `/nachrichten/` | Chronologisch sortierte Meldungen |
| Unternehmenssuche | `/aktie/{symbol}/` | Alle News zu einer Aktie |
| Analysen | `/analysen/` | Kauf-/Verkauf-Empfehlungen von Banken |
| Marktberichte | `/marktberichte/` | Tagesberichte DAX, DOW, Krypto |
| Ad-hoc-Meldungen | `/ad-hoc-meldungen/` | Pflichtmitteilungen börsennotierter Unternehmen |

#### Wie der Macro-Agent finanznachrichten.de nutzt

Der Macro-Agent filtert Nachrichten nach folgenden Kriterien:

1. **Relevanz-Filter:** Nur Meldungen zu Assets auf der aktuellen Watchlist
2. **Sentiment-Analyse:** Positiv / Negativ / Neutral Klassifikation
3. **Event-Erkennung:** Earnings, Dividenden, M&A, Regulierung, Zentralbankentscheidungen
4. **Risikoklassifikation:**
   - `HOCH` → Blockiert neue Entries (z.B. Fed-Entscheid, Kriegsausbruch)
   - `MITTEL` → Warnung, Vorsicht bei Entries
   - `NIEDRIG` → Kein Einfluss auf Pipeline

**Scraping-Hinweis:** Direktes Scraping nur mit Robots.txt-Prüfung und angemessenen Request-Delays (≥ 2 Sekunden). Alternativ RSS-Feed nutzen.

---

### finance.yahoo.com und yfinance

#### Überblick Yahoo Finance

Yahoo Finance ist die primäre englischsprachige Finanzquelle für globale Marktdaten, Earnings, News und Fundamentaldaten.

**Relevante Bereiche:**
- Marktübersicht: Indizes, Währungen, Rohstoffe, Futures
- Earnings Calendar: Quartalsergebnisse mit Datum und Erwartungen
- News-Feed: Zu jedem Ticker verfügbar
- Analyst Ratings: Kursziele und Empfehlungen

#### yfinance Python-Library – vollständige Referenz

```python
pip install yfinance
```

#### history() – Kursdaten abrufen

```python
import yfinance as yf

ticker = yf.Ticker("AAPL")

# Zeitreihe: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
df = ticker.history(period="3mo")        # letzte 3 Monate
df = ticker.history(period="1y", interval="1wk")  # 1 Jahr, Wochenkerzen

# Mit Datum-Range
df = ticker.history(start="2024-01-01", end="2024-12-31", interval="1d")

# Intervalle: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
# Hinweis: Intraday (< 1d) nur letzte 60 Tage verfügbar

print(df.columns)  # Open, High, Low, Close, Volume, Dividends, Stock Splits
print(df.tail())
```

#### info() – Fundamentaldaten und Metadaten

```python
import yfinance as yf

ticker = yf.Ticker("MSFT")
info = ticker.info

# Häufig genutzte Felder:
felder = {
    "shortName": "Unternehmensname",
    "sector": "Sektor",
    "industry": "Branche",
    "marketCap": "Marktkapitalisierung",
    "trailingPE": "KGV (trailing 12M)",
    "forwardPE": "KGV (Forward Estimate)",
    "priceToBook": "Kurs-Buchwert",
    "trailingEps": "EPS (trailing)",
    "forwardEps": "EPS (Forward)",
    "returnOnEquity": "ROE",
    "returnOnAssets": "ROA",
    "debtToEquity": "Schulden/Eigenkapital",
    "freeCashflow": "Free Cash Flow",
    "dividendYield": "Dividendenrendite",
    "beta": "Beta (Marktrisiko)",
    "52WeekHigh": "52-Wochen-Hoch",
    "52WeekLow": "52-Wochen-Tief",
    "averageVolume": "Durchschnittsvolumen",
    "shortRatio": "Short Ratio",
    "recommendationKey": "Analysten-Konsens (buy/hold/sell)",
}

for feld, beschreibung in felder.items():
    wert = info.get(feld, "N/A")
    print(f"{beschreibung}: {wert}")
```

#### news() – aktuelle Nachrichten

```python
import yfinance as yf

ticker = yf.Ticker("NVDA")
nachrichten = ticker.news

for artikel in nachrichten[:5]:
    print(f"Titel: {artikel.get('content', {}).get('title', 'N/A')}")
    print(f"Datum: {artikel.get('content', {}).get('pubDate', 'N/A')}")
    print(f"URL:   {artikel.get('content', {}).get('canonicalUrl', {}).get('url', 'N/A')}")
    print("---")
```

#### Weitere nützliche yfinance-Methoden

```python
import yfinance as yf

ticker = yf.Ticker("TSLA")

# Finanzdaten
ticker.income_stmt          # Gewinn- und Verlustrechnung (jährlich)
ticker.quarterly_income_stmt # GuV quartalsweise
ticker.balance_sheet        # Bilanz (jährlich)
ticker.quarterly_balance_sheet
ticker.cashflow             # Cashflow-Statement (jährlich)
ticker.quarterly_cashflow

# Optionen
ticker.options              # Verfügbare Verfallsdaten
chain = ticker.option_chain("2024-12-20")  # Calls und Puts
chain.calls
chain.puts

# Institutionelle Investoren
ticker.institutional_holders
ticker.major_holders

# Insider-Transaktionen
ticker.insider_transactions

# Analystenmeinungen
ticker.analyst_price_targets
ticker.upgrades_downgrades
```

#### Mehrere Ticker gleichzeitig laden (schneller)

```python
import yfinance as yf

# Download für mehrere Symbole auf einmal (effizienter als Schleife)
daten = yf.download(
    tickers=["AAPL", "MSFT", "GOOGL"],
    period="1y",
    interval="1d",
    group_by="ticker",
    auto_adjust=True
)

# Zugriff: daten["AAPL"]["Close"]
print(daten["AAPL"]["Close"].tail())
```

---

### Weitere wichtige Nachrichtenquellen

#### investing.com

**Zweck:** Internationaler Finanz-Datenprovider mit breiter Asset-Abdeckung.

| Funktion | Beschreibung |
|---|---|
| Wirtschaftskalender | Alle relevanten Makrodaten mit Prognosen und Vorwerten (NFP, CPI, BIP, Zinsentscheid) |
| Technische Zusammenfassung | Automatisiertes Signal (Strong Buy/Sell) pro Zeitrahmen |
| Kryptodaten | Echtzeit-Preise und Historien |
| Rohstoffe & Forex | Vollständige Coverage |
| News | Englisch und Deutsch |

**Für den Macro-Agent:** Wirtschaftskalender ist die wichtigste Funktion – gibt Aufschluss über anstehende Hochrisiko-Events.

#### tradingeconomics.com

**Zweck:** Makroökonomische Datenbank mit historischen Zeitreihen für Länder und Indikatoren.

| Indikator | Beschreibung |
|---|---|
| BIP-Wachstum | Quartalsweise, alle Länder |
| Inflationsrate (CPI) | Monatlich |
| Arbeitslosenquote | Monatlich |
| Leitzinsen | Aktuell und historisch |
| Handelsbilanzen | Export/Import-Daten |
| Rohstoffpreise | Öl, Gas, Metalle, Agrar |

**Für den Macro-Agent:** Nützlich zur Einordnung des globalen Konjunkturzyklus und zur Identifikation struktureller Makro-Risiken.

#### CNN Fear & Greed Index

**URL:** `https://edition.cnn.com/markets/fear-and-greed`

**Zweck:** Misst die aktuelle Marktpsychologie auf einer Skala von 0 (extreme Angst) bis 100 (extreme Gier).

**Zusammensetzung (7 Indikatoren):**
1. Stock Price Momentum (S&P 500 vs. 125-Tage-Durchschnitt)
2. Stock Price Strength (52-Wochen-Hochs vs. -Tiefs)
3. Stock Price Breadth (McClellan Volume Summation Index)
4. Put/Call Ratio (Optionsmarkt-Sentiment)
5. Market Volatility (VIX-Niveau)
6. Junk Bond Demand (Spread High Yield vs. Investment Grade)
7. Safe Haven Demand (Anleihen vs. Aktien Rendite)

**Interpretation für die InvestApp:**

| Wert | Zone | Bedeutung |
|---|---|---|
| 0–25 | Extreme Angst | Kaufgelegenheit (konträr), aber Vorsicht |
| 25–45 | Angst | Bullishes Potenzial, selektiv kaufen |
| 45–55 | Neutral | Normales Trading-Umfeld |
| 55–75 | Gier | Defensiv, Stops enger setzen |
| 75–100 | Extreme Gier | Hohes Rückschlagrisiko, Exposure reduzieren |

**Abruf per API (inoffiziell):**
```python
import requests

def hole_fear_greed_index() -> dict:
    url = "https://fear-and-greed-index.p.rapidapi.com/v1/fgi"
    headers = {
        "X-RapidAPI-Key": "DEIN_RAPIDAPI_KEY",
        "X-RapidAPI-Host": "fear-and-greed-index.p.rapidapi.com"
    }
    response = requests.get(url, headers=headers)
    data = response.json()
    return {
        "wert": data["fgi"]["now"]["value"],
        "klassifikation": data["fgi"]["now"]["valueText"]
    }
```

#### VIX – CBOE Volatility Index

**Symbol:** `^VIX` (in yfinance abrufbar)

**Zweck:** Misst die implizite Volatilität des S&P 500 (30-Tage-Optionen). Gilt als "Angst-Barometer" der Märkte.

**Interpretation:**

| VIX-Level | Marktphase | Implikation |
|---|---|---|
| < 15 | Ruhig, geringe Angst | Mögliche Selbstgefälligkeit, Risiko unterschätzt |
| 15–20 | Normal | Standardmäßige Marktbedingungen |
| 20–30 | Erhöhte Volatilität | Vorsicht, engere Stops |
| 30–40 | Hohe Angst | Starke Schwankungen, selektiv short |
| > 40 | Extreme Angst / Krise | Hochrisiko-Umfeld, ggf. Pause |

**VIX mit yfinance abrufen:**
```python
import yfinance as yf

vix = yf.Ticker("^VIX")
aktuell = vix.history(period="5d")["Close"].iloc[-1]
print(f"Aktueller VIX: {aktuell:.2f}")

# VIX-Zeitreihe für Analyse
vix_reihe = vix.history(period="1y")["Close"]
vix_durchschnitt = vix_reihe.mean()
print(f"VIX 1J-Durchschnitt: {vix_durchschnitt:.2f}")
print(f"Aktuell vs. Durchschnitt: {aktuell/vix_durchschnitt:.2f}x")
```

**Integration in den Volatility-Agent:**
```python
import yfinance as yf

def vix_freigabe(schwelle_hoch: float = 30.0, schwelle_extrem: float = 40.0) -> dict:
    vix_wert = yf.Ticker("^VIX").history(period="2d")["Close"].iloc[-1]

    if vix_wert > schwelle_extrem:
        status = "blockiert"
        grund = f"VIX {vix_wert:.1f} – extreme Volatilität, kein Trading"
    elif vix_wert > schwelle_hoch:
        status = "warnung"
        grund = f"VIX {vix_wert:.1f} – erhöhte Volatilität, Stops anpassen"
    else:
        status = "freigegeben"
        grund = f"VIX {vix_wert:.1f} – normale Marktbedingungen"

    return {"vix": round(vix_wert, 2), "status": status, "grund": grund}
```

---

*Dieses Handbuch ist die operative Grundlage für alle KI-Agenten der InvestApp-Pipeline. Es ist als lebendiges Dokument zu verstehen und wird bei Bedarf aktualisiert.*

---

## 12. Forex-Handelssessions & Überlappungen

Der Forex-Markt ist 24 Stunden täglich geöffnet (Montag bis Freitag) und teilt sich in drei Hauptsessions:

**Tokyo-Session (21:00–08:00 UTC)**
- JPY-Paare (USD/JPY, EUR/JPY, GBP/JPY) sind am aktivsten
- Oft Range-Märkte mit ruhigen, engen Bewegungen
- Geringe Volatilität außerhalb japanischer Wirtschaftsdaten
- Asiatische Paare (AUD/JPY, NZD/JPY) ebenfalls aktiv

**London-Session (08:00–17:00 UTC)**
- Höchstes Handelsvolumen weltweit (~35% des Tagesumsatzes)
- EUR, GBP, CHF-Paare besonders aktiv
- Starke Trendmärkte möglich, besonders zu Sessionsbeginn (08:00–10:00 UTC)
- Häufigste Fakeouts: erste 30 Minuten nach Eröffnung

**New York-Session (13:00–22:00 UTC)**
- USD-Paare dominieren, hohe Volatilität nach US-Wirtschaftsdaten
- Zweithöchstes Volumen (~22% des Tagesumsatzes)
- Überschneidung mit London besonders aktiv (12:00–17:00 UTC)

**London-NY-Overlap (12:00–16:00 UTC)**
- Ca. 50% des globalen Tagesvolumens in diesem Fenster
- Beste Einstiegsmöglichkeiten für Trendfolge-Strategien
- Höchste Liquidität = engste Spreads = sauberste Ausführung

**Handelsfreie Zeiten meiden:**
- Freitag ab 18:00 UTC (Liquiditätsabbau vor Wochenende, Gap-Risiko)
- Sonntagabend bis Montagöffnung (Gaps durch Wochenend-News möglich)
- Direkt nach Sessionsbeginn (Spreads erhöht, erste 5–15 Minuten)

---

## 13. Wirtschaftskalender & High-Impact Events

Wirtschaftsdaten können innerhalb von Sekunden massive Kursbewegungen auslösen. Kein System kann diese Bewegungen zuverlässig vorhersagen.

**Kritische Ereignisse nach Impakt:**

| Ereignis | Häufigkeit | Erwartete Bewegung |
|----------|-----------|-------------------|
| NFP (Nonfarm Payrolls) | 1. Freitag/Monat | 100–400+ Pips |
| FOMC-Zinsentscheid | 8x pro Jahr | 50–200+ Pips |
| EZB-Zinsentscheid | ~8x pro Jahr | 50–200 Pips (EUR-Paare) |
| CPI-Daten (USA) | Monatlich | 30–150 Pips |
| BOJ/BOE-Entscheidungen | ~8x pro Jahr | 50–150 Pips |
| Arbeitslosendaten (USA) | Wöchentlich | 10–50 Pips |

**Operative Regel: ±30 Minuten um High-Impact Events keine neuen Positionen eröffnen.**

Offene Positionen können mit engerem Stop oder temporärer Absicherung geschützt werden. Nach dem Event: Erst den ersten Volatilitäts-Spike abwarten, dann auf die Folgebewegung handeln — nicht in den Spike hinein.

**Tools für Wirtschaftskalender:**
- investing.com/economic-calendar
- forexfactory.com
- Beide zeigen Impact-Level (Hoch/Mittel/Niedrig) und Erwartungswerte

---

## 14. Währungskorrelationen

Korrelierte Positionen multiplizieren das Risiko — oder hedgen es natürlich. Korrelationen können sich im Laufe der Zeit ändern und sind keine absoluten Konstanten.

**Stark positive Korrelationen (gleichläufig):**
- EUR/USD ↔ GBP/USD: +0,81 bis +0,95
- AUD/USD ↔ NZD/USD: +0,85 bis +0,95
- EUR/USD ↔ AUD/USD: +0,70 bis +0,85
- USD/JPY ↔ USD/CHF: +0,75 bis +0,90

⚠️ **Risiko:** EUR/USD und GBP/USD gleichzeitig in gleicher Richtung handeln = doppeltes USD-Exposure. Gilt als ein Trade, nicht zwei.

**Stark negative Korrelationen (gegenläufig):**
- EUR/USD ↔ USD/CHF: −0,90 bis −0,95 → natürliches Hedge-Paar
- AUD/USD ↔ USD/CAD: −0,75 bis −0,85

**Intermarket-Korrelationen:**
- Gold ↔ USD: negativ (steigender USD-Index → Gold fällt tendenziell)
- Öl ↔ CAD: positiv (Kanada = größter Öl­exporteur → USD/CAD korreliert mit Ölpreis)
- Aktienindizes ↔ JPY: negativ (Risikoaversion → JPY steigt, Indizes fallen)

**Praxisregel:** Alle korrelierten Positionen als eine Gesamtposition beim Risikomanagement zählen. Gesamtrisiko über alle offenen Positionen täglich prüfen.

---

## 15. Safe-Haven-Währungen & Marktsentiment

**Safe-Haven-Hierarchie (Stärke bei Krisen):**

1. **JPY** (stärkste Safe-Haven-Währung)
   - Steigt bei jeder Form globaler Unsicherheit: Kriege, Finanzkrisen, Risikoaversion
   - Wird von Carry-Trade-Auflösungen verstärkt (Rückzahlung von JPY-Krediten)

2. **CHF** (zweitstärkste Safe-Haven-Währung)
   - Schweizer Neutralität und politische Stabilität
   - Profitiert besonders von geopolitischen Ereignissen in Europa
   - SNB interveniert gelegentlich gegen zu starke CHF-Aufwertung

3. **USD** (konditionale Safe-Haven-Währung)
   - Funktioniert als Safe Haven nur wenn die Krise **nicht** US-spezifisch ist
   - Bei US-Rezession, US-Schuldenkrisen oder US-politischer Instabilität kann USD fallen

**Risk-On vs. Risk-Off Dynamik:**

| Marktphase | Begünstigte Währungen | Belastete Währungen |
|-----------|----------------------|---------------------|
| Risk-On (Optimismus, Wachstum) | AUD, NZD, CAD | JPY, CHF |
| Risk-Off (Risikoaversion, Krise) | JPY, CHF, USD* | AUD, NZD, CAD |

---

## 16. Carry Trades

**Grundprinzip:** Höher verzinste Währung kaufen, niedrig verzinste verkaufen → Swap-Zinsen kassieren.

**Klassische Carry-Trade-Paare:**
- **Long AUD/JPY:** Positive tägliche Swap-Gutschriften bei Long-Positionen (AUD-Zinsen > JPY-Zinsen)
- **Long NZD/JPY:** Analog zu AUD/JPY
- Aktuelle Zinsdifferenz täglich prüfen — verändert sich mit Zentralbankpolitik

**Carry-Trade-Risiken:**
- Bei plötzlicher Risikoaversion kommt es zur massenhaften Carry-Trade-Auflösung → Flash Crashes möglich (AUD/JPY −15 % in wenigen Stunden historisch dokumentiert)
- Zinspolitik-Änderungen (BoJ-Zinserhöhung, RBA-Zinssenkung) können Verhältnis umkehren
- **Swap-Kosten und -Erträge** in der Gesamtstrategie berücksichtigen — besonders relevant für Positionen, die über Nacht gehalten werden

**Agenten-Regel (Risk-Agent):** Bei Risk-Off-Sentiment (AUD/JPY fällt) keine neuen Long-Positionen auf Carry-Trade-Paaren freigeben.

---

## 17. Forex-Risikomanagement & Spread-Management

**Position Sizing:**
- Max. 1–2% des Kontokapitals pro Trade riskieren
- Max. 5% Daily Loss Limit → Trading-Pause für den gesamten Tag (kein Revenge-Trading)
- Max. 3 gleichzeitig offene Positionen (Korrelationsrisiko und psychologische Belastung)

**Stop-Loss-Platzierung:**
- ATR-basiert: 1,5–2,5x ATR(14) je nach Volatilität und Strategie
- Strukturbasiert: unter dem letzten Swing Low (Long) / über dem Swing High (Short)
- Kombination: strukturellen Level als Basis nehmen, ATR(14) als Mindest-Puffer nutzen
- Keine runden Zahlen als Stop (50,000 / 1,2000) — institutionelle Stops liegen dort

**Spread-Management:**
- Filter: wenn Spread > 3x Normalspread → kein Entry (häufig um News-Zeiten)
- Normalwerte (Richtwerte bei ECN-Brokern):
  - EUR/USD: 0,1–1,0 Pip
  - GBP/USD: 0,5–1,5 Pip
  - USD/JPY: 0,2–0,8 Pip
  - Exotische Paare: 3–30 Pips (je nach Broker)
- News-Zeiten: Spreads können auf das 5–20-fache ansteigen → generell meiden

**Break-Even-Mathematik:**

| CRV | Minimale Win Rate für Break-Even |
|-----|----------------------------------|
| 1:1 | 50,0% |
| 1:1,5 | 40,0% |
| 1:2 | 33,4% |
| 1:3 | 25,0% |
| 1:4 | 20,0% |

Formel: `Win Rate (min) = 1 / (1 + CRV)`

Ein System mit CRV 1:2 und 40% Win Rate ist profitabel. Bei 1:1 muss man >50% treffen — psychologisch und statistisch schwierig.

---

## 18. Performance-Benchmarks

**Realistische Zielwerte für profitables Trading:**

| Kennzahl | Minimum | Gut | Exzellent |
|---------|---------|-----|---------|
| Win Rate | 35% | 45–55% | >60% |
| Durchschnittl. CRV | 1:1,5 | 1:2 – 1:3 | >1:3 |
| Profit Factor | 1,2 | 1,5 – 2,0 | >2,0 |
| Max Drawdown | <30% | <20% | <10% |
| Sharpe Ratio | >0,5 | >1,0 | >2,0 |
| Monatl. Rendite | 2–5% | 5–10% | >10% |

**Definitionen:**
- **Profit Factor** = Gesamt-Gewinne / Gesamt-Verluste (alle Trades)
  - <1,0 = Verlustprogramm; 1,0–1,3 = fragwürdig; 1,5+ = tragfähig; 2,0+ = exzellent
- **Sharpe Ratio** = (Rendite − risikofreier Zins) / Standardabweichung der Renditen
- **Max Drawdown** = größter Peak-to-Trough-Verlust in der Handelsdauer

⚠️ **Warnung:** Backtests überschätzen Profit Factor oft um 20–40% durch Overfitting und fehlende Slippage/Spread-Realismus. Live-Trading-Ergebnisse über 3–6 Monate sind der einzig valide Test.

---

## 19. SMC-Confluence im Forex-Kontext

Smart Money Concepts (SMC) beschreiben das Verhalten institutioneller Marktteilnehmer (Zentralbanken, Hedgefonds, Market Maker). Die Kernthese: Institutionelle brauchen Liquidität für ihre großen Orders — sie bewegen den Markt gezielt zu Liquiditätszonen.

**Höchste Wahrscheinlichkeit: Triple-Confluence**

**Order Block + Fair Value Gap (FVG) + Liquidity Sweep = stärkstes Signal**

Alle drei Elemente gleichzeitig: Einstiegswahrscheinlichkeit signifikant höher als bei einzelnen Signalen.

**Premium- und Discount-Zonen (Fibonacci-Kontext):**
- **Premium-Zone** (Short-Bias): Fibonacci 0,50–0,786 über dem Swing-Tief
- **Equilibrium** (faire Bewertung): Fibonacci 0,50
- **Discount-Zone** (Long-Bias): Fibonacci 0,214–0,50 unter dem Swing-Hoch
- Regel: Im Premium shorten, im Discount kaufen — immer in Richtung des Higher Timeframe Trends

**Strukturelemente:**
- **Break of Structure (BOS):** Neues Higher High über vorherigem HH im Aufwärtstrend → Trend bestätigt
- **Change of Character (ChoCh):** Erstes Lower Low im Aufwärtstrend → frühes Warnsignal für Trendwechsel (noch kein Bestätigung)
- **Equal Highs/Lows:** Zwei gleich hohe Hochs oder Tiefs = Liquiditätszonen — Market Maker treibt Kurs dorthin, triggert Stops, kehrt dann um

**Order Blocks (OB):**
- **Bullish OB:** Letzte bearishe Kerze (oder Zone) unmittelbar vor einer starken Aufwärtsbewegung
- **Bearish OB:** Letzte bullishe Kerze (oder Zone) unmittelbar vor einer starken Abwärtsbewegung
- Gültigkeit: OB ist valide, solange er nicht vom Kurs durchbrochen (konsumiert) wurde
- Retest des OB = potenzielle Einstiegszone in Trendrichtung

**Fair Value Gaps (FVG) / Imbalance:**
- Entsteht wenn Kerze 2 so stark ist, dass Lücke zwischen Kerze 1 High und Kerze 3 Low entsteht
- Kurs kehrt statistisch häufig zur Füllung dieser Lücke zurück (Effizienz-Prinzip)
- Unberührte FVGs auf höheren Timeframes sind stärkere Magneten als auf niedrigen
- Teilweise Füllung (50%) reicht oft als Reaktionszone

---

*Kapitel 12–19 basieren auf Recherchen zu institutionellem Forex-Trading, SMC-Methodologie und Risikomanagement-Standards (März 2026). Die Erkenntnisse fließen in die Agenten-Parametrisierung und Handbuch-Strategie ein.*
