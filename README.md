# BIRD HUNT

Een homebrew schietspel voor Philips Videopac G7000 / Magnavox Odyssey2,
geschreven in Intel 8048 assembly. De speelbare ROM is `bird-hunt.bin` (8192 bytes).
Op de G7400 verschijnt een landschap met boom, struiken en gras. Op de G7000
blijft het oorspronkelijke blauwe/groene speelveld behouden.

## Spelen

Beweeg het vizier met de joystick en druk op vuur om te schieten.
Laat de vuurknop los tussen schoten. Elke ronde verschijnen drie vogels,
een voor een, met verschillende vliegpaden. Je hebt vijf schoten per ronde.
Een geraakte vogel valt naar beneden; een misser geeft een korte witte flits.
Rechtsboven staan vijf gele patroontjes. Elk schot laat er een verdwijnen;
bij het begin van een nieuwe ronde worden ze alle vijf aangevuld.
Voor iedere ronde, ook de eerste, volgt twee seconden wachttijd en daarna
`tune_buzz` als startsignaal, gevolgd door nog een seconde wachttijd. Bij vervolgrondes begint die wachttijd pas na
het rondedeuntje. Tijdens het wachten zijn de vogels verborgen en kun je
niet schieten, maar het vizier blijft beweegbaar. Fire vanuit het titelscherm of tijdens de wachttijd verbruikt
geen kogel: laat na de start los en druk opnieuw om te schieten.

Na iedere ronde wordt de totaalscore bijgewerkt:

| Geraakte vogels | Resultaat |
| --- | --- |
| 0 | Totaal halveren, naar beneden afgerond |
| 1 | +1 punt |
| 2 | +5 punten |
| 3 | +10 punten, plus 5 punten per resterende kogel |

De score stopt bij 65535. Het speelveld bestaat uit blauwe lucht en groen gras.
Bij drie treffers klinkt `tune_select`; met twee kogels over klinkt dit driemaal.
Als halveren de score op nul brengt (ook bij 0 of 1 punt), volgt game-over:
`tune_alarm`, twee seconden wachten en terug naar het lager geplaatste titelscherm.
Een toets op het consoletoetsenbord pauzeert het spel. Fire hervat zonder
een schot te verbruiken; laat fire los voordat je weer schiet. Rondetimers
en vogelbeweging staan stil tijdens pauze. Een vastgehouden toets pauzeert
niet opnieuw na hervatten; daarvoor moet je de toets opnieuw indrukken.
Kopieer `bird-hunt.bin` naar de PicoPac om te spelen.

## Bouwen

Installeer de ASL Macro Assembler met 8048-ondersteuning en het bijbehorende
`p2bin`. Zet beide op PATH en voer `make rebuild` uit, of geef de paden mee:

```sh
make rebuild ASL=/pad/naar/asl P2BIN=/pad/naar/p2bin
```

`include/g7000.h` bevat de hardware- en BIOS-definities van Soeren Gust.
De oorspronkelijke copyright- en licentietekst is behouden in dat bestand.
Er worden geen BIOS-ROMs, commerciele spellen of assemblerbinaries meegeleverd.

## Testen

De tests gebruiken een libretro O2EM-core en een eigen, legaal verkregen
`o2rom.bin` in een aparte BIOS-map. Gebruik de optionele `test-core.patch`
op libretro-o2em revisie `679d6fec04963f6e70a7ec217e3d0ebb1fe472fc` voor
extra VDC-timingcontroles. De interne `artgame_test_*` namen blijven behouden
voor compatibiliteit met die testcore; ArtGame was de werknaam van dit spel.
Pas de patch in de O2EM-bronmap toe met
`git apply --ignore-whitespace /pad/naar/BIRD-HUNT/test-core.patch`;
de oorspronkelijke emulatorbron gebruikt CRLF-regelafbrekingen.

```sh
python3 check_rom.py /pad/naar/o2em_libretro.dylib /pad/naar/bios bird-hunt.bin PAL
python3 check_rom.py /pad/naar/o2em_libretro.dylib /pad/naar/bios bird-hunt.bin NTSC
python3 check_rom.py /pad/naar/o2em_libretro.dylib /pad/naar/bios bird-hunt.bin PAL G7400
```

Voor de laatste test is ook een eigen `g7400.bin` BIOS vereist.
Beide G7000-modi en G7400 PAL zijn getest op rondes, schoten, treffers, score
en schermtiming. De G7400-test controleert daarnaast de geladen tilebytes,
het samengestelde beeld en drie resets/herstarts. Fysieke G7400-test nog nodig.
`REVIEW.md` bevat het historische technische verslag onder de oude werknaam.

## G7400-architectuur

De ROM gebruikt vier standaard 2 KB-cartridgebanken in bestandsvolgorde
0, 1, 2, 3. Bank 3 bevat het spel; banken 0-2 bevatten identieke laadcode
en elk 960 bytes achtergronddata. De laadcode schakelt alleen met interrupts
uit en herstelt MB0 na elke toegang tot de bovenste ROM-pagina's.

Detectie gebruikt twee opcode-signaturen uit de Europese G7400-BIOS
(037eh=39h en 0394h=bbh). Andere BIOS-versies vallen terug op het gewone
speelveld als ze deze signatuur niet hebben. Jopac en Odyssey3 zijn niet getest.
De Plus-laag blijft verborgen op het zwarte titelscherm en wordt daarna
zichtbaar door de blauwe/groene VDC-kleuren transparant te maken.

De munitie-indicator gebruikt quad 0 en karakter A, boven het vlieggebied.
Een smalle I-vorm uit de ingebouwde tekenset stelt een patroon voor.
Het verborgen karakter B bewaart de laatst getekende munitiewaarde.
Alleen na een wijziging worden de vijf tekenpointers vernieuwd; de score
wacht dan een frame. De HUD-routine op 0800h-0854h roept geen BIOS aan en
de aanroeper herstelt expliciet MB0. De uitgebreide spelcyclus op 0900h-09a4h
en rondelogica vanaf 0a00h gebruiken expliciete MB0/MB1-wissels rond
BIOS- en spelroutineaanroepen. De rondewachtroutine staat op 0b00h-0b3ah.
De testcore bewaakt deze MB1-codegebieden.
Pauze en toetsenbordflank gebruiken bits 7/6 van `game_active`; de RAM-indeling
blijft verder gelijk. Voor game-over wordt de VBlank-lengte gemeten zodat
de wachttijd 100 PAL- of 120 NTSC-frames bedraagt.

Beide publieke cartridge-ingangen (0400h reset en 0408h menustart) voeren
nu de volledige initialisatie uit. De Plus-loader keert via een aparte
bankbrug op 07f8h terug, zodat hij niet opnieuw wordt gestart.
Voor het eerste schot wordt het geluidsverschuifregister expliciet gevuld:
`tune_shoot` wijzigt alleen de besturing en vult zelf geen golfvorm.
De tests controleren ook hoorbare samples bij het eerste schot en na resets.
Voeg `MENU` achter een testcommando toe om direct via 0408h op te starten.

`assets/g7400` bevat het ontwerp, de conversie en de geladen data.
Na aanpassen van het ontwerp: converteer opnieuw en voer `make rebuild` uit.
