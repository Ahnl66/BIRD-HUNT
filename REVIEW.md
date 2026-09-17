# ArtGame review en correctie

## Gevonden oorzaken

1. **P1: geheugenbank bleef verkeerd staan na CALL.** In de vorige ROM
   schakelde `call shape_byte` op 0726h naar MB1. Na `ret` bleef de banklatch
   op MB1 staan. De daaropvolgende `call gfxon` op 052ch werd daardoor een
   sprong naar 0927h in plaats van BIOS-adres 0127h. Dezelfde fout zat in
   `shoot`, `update_birds` en `shot_sound`. ASL compileerde dit zonder fout.
   In de emulator liep de oude ROM na starten op 0947h met beschadigde
   cursor- en vogelgegevens. Code en tabellen blijven volledig onder 0800h;
   de assembler bewaakt de bovengrens van MB0.

2. **P2: onvolledige scherminitialisatie en kwetsbare interruptketen.**
   De vogels kregen hun eerste posities pas nadat het beeld al aan stond.
   De eigen VSYNC-routine sprong midden in de BIOS-routine en sloeg onder
   meer de opslag van botsingsgegevens en de frameklok over. De vervanging
   gebruikt de vaste vectoren 0400/0402/0404/0406/0408/040ah en de volledige
   BIOS-routine `vsyncirq`. Alle vier sprites worden opgebouwd voordat de
   graphics worden ingeschakeld. Tekst en quads worden verborgen.

3. **P2: raakdetectie en cursorcoordinaten waren niet consistent.**
   De cursor gebruikte Y+4 als midden, terwijl 8 spriterijen 16 scanlijnen
   innemen. Dat is nu Y+8. X wordt in hele VDC-pixels bijgehouden; de
   halve-pixelbit wordt niet langer gevuld met het laagste bit van die X.
   Al vallende vogels worden overgeslagen bij de raakdetectie.

## Schermupdate

Joysticks en spelregels worden berekend voordat `waitvsync` wordt aangeroepen.
Daarna: VDC selecteren, `gfxoff`, posities/kleuren/bitmaps schrijven, `gfxon`.
Met een vogel per keer past ook een compacte bitmap-kopieerlus ruimschoots
in de korte NTSC-blanking. Er zijn twee vleugelstanden en een rode valvorm. Het schotgeluid
wordt na het opnieuw inschakelen van het beeld gestart. Vuur vasthouden
blokkeert de spel-lus niet en geeft geen herhaalde schoten.

## Verificatie

- ASL 1.42, build 274: 0 fouten, 0 waarschuwingen; ROM 2048 bytes.
- De oude ROM faalt in dezelfde O2EM-test op de cursorinitialisatie.
- De nieuwe ROM doorstaat de tests op zowel PAL als NTSC: initialisatie,
  spritebitmaps, beweging per frame, alle schermgrenzen, misschoten,
  raakschoten op elk van de drie vogels, verticaal vallen, opnieuw
  verschijnen, vasthouden en opnieuw indrukken van vuur.
- Geinstrumenteerde O2EM: 0 objectschrijfacties met foreground ingeschakeld,
  0 spel-objectschrijfacties buiten VBlank en 0 instructies in MB1. De
  eenmalige scherminitialisatie valt buiten de VBlank-meetperiode; die
  gebeurt wel met foreground uitgeschakeld.
- Visueel gecontroleerd: door O2EM gerenderde PAL-beelden van vliegen en
  vallen. De ROM is ook in de geinstalleerde O2Em-app geopend.
- Geen test op fysieke G7000-hardware uitgevoerd.

`check_rom.py` voert de gecompileerde ROM uit in de echte O2EM CPU/VDC-core,
met het G7000-BIOS (CRC32 8016a315), en stuurt joystickinvoer. Het bevat geen
BIOS. Voor herhalen met een eigen BIOS en gebouwde libretro-O2EM-core:

```sh
python3 check_rom.py /pad/o2em_libretro.dylib /map/met/bios artgame.bin PAL
python3 check_rom.py /pad/o2em_libretro.dylib /map/met/bios artgame.bin NTSC
```

De tests schrijven `intro-*`, `flying-*`, `miss-*` en `falling-*` PNG-beelden naast de
ROM. De optionele timingcontroles vereisen `test-core.patch`; zonder die
patch meldt het script expliciet dat de timinginstrumentatie ontbreekt.

## Update: BIRD HUNT, lucht en gras (2026-09-13)

De intro toont negen gekleurde tekens, `BIRD HUNT`, op zwart. Tijdens het
spel zet een VSYNC-hook de achtergrond weer blauw en activeert de
scanlijnteller. De timer-interrupt wacht op de ingestelde Y-positie en
schrijft groen op de eerstvolgende HBlank. Hiervoor wordt T1 gebruikt:
de horizontale statusbit in A1h is niet hetzelfde als het HBlank-signaal.
De interrupt bewaart A/P1, gebruikt RB0 en laat de BIOS-geluidsregisters
R3/R4 intact. De volledige BIOS-VSYNC-afhandeling blijft actief.

In het 250-regelige O2EM-beeld zijn regels 0-149 blauw en 150-249 groen.
Dat is 60% lucht en 40% gras; de zichtbare uitsnede van een fysieke TV kan
door overscan afwijken. Het schotgeluid blijft `tune_shoot`.

De bestaande speltests en nieuwe beeldtests slagen op PAL en NTSC. Tijdens
meer dan 1600 gecontroleerde frames per modus blijft de horizon op regel
150: geen extra kleurbanden en geen verschuivingen. De instrumentatie telt
0 objectschrijfacties met foreground aan, 0 objectschrijfacties buiten
VBlank, 0 gras-kleurwissels buiten HBlank en 0 instructies in MB1.
De ROM blijft 2048 bytes; ASL meldt 0 fouten en 0 waarschuwingen.

De T1-aansluiting en de verschillende betekenis van de horizontale statusbit
zijn ook gecontroleerd in de primaire MAME-broncode:
[T1 = VBlank of HBlank](https://github.com/mamedev/mame/blob/master/src/mame/philips/odyssey2.cpp)
en [8244/8245-status en beam counters](https://github.com/mamedev/mame/blob/master/src/devices/video/i8244.cpp).

## Update: rondes en missers (2026-09-17)

- Iedere ronde heeft drie vogels, een voor een. De volgende verschijnt
  nadat de vorige uit beeld is gevlogen of na een treffer naar beneden is gevallen.
- Vijf schoten per volledige ronde. Elke nieuwe druk verbruikt een schot;
  vasthouden geeft geen herhaalde schoten. Met nul schoten blijven de vogels
  doorvliegen; extra drukken leveren geen schot, geluid of misserflits op.
- Een misser toont acht frames een witte ronde vlek op de vastgelegde
  schotpositie. De cursor kan ondertussen onafhankelijk bewegen. Sprite 0
  is het vizier, sprite 1 de enige vogel, sprite 2 de flits; sprite 3 blijft verborgen.
- Een 8-bit LFSR bepaalt startkant, starthoogte en veranderende verticale
  helling. De intro-wachttijd varieert de beginwaarde. Reflecties houden
  vliegende vogels op Y=32..128, volledig boven de horizon; treffers vallen recht omlaag.
- Na vogel drie klinkt `tune_select2`, met 30 frames pauze (0.5-0.6 seconde).
  Daarna begint een nieuwe ronde met vijf schoten. Een ingedrukte vuurknop
  vuurt niet automatisch bij het aanvullen. Gewone schoten behouden `tune_shoot`.

`check_rom.py` controleert de misserpositie en levensduur, nul-ammo,
drie opeenvolgende vogels, treffers en vallen, rondegeluid, aanvullen en
ingedrukt houden over een rondegrens. Een langere test controleert meerdere
volledige rondes, verschillende paden en beide startkanten. Beide modi
(PAL/NTSC) slagen, met meer dan 3000 gecontroleerde frames, een horizon op
regel 150 en nul onveilige object- of kleurwrites. Ook de misser- en
valbeelden zijn gerenderd. Code en data eindigen op 07b4h; de ROM blijft
2048 bytes. Geen nieuwe test op fysieke hardware uitgevoerd.

## Update: totaalscore (2026-09-17)

Onderaan in het gras staat `SCORE 00000`. Elke treffer telt eenmaal mee voor
de huidige ronde. Pas na afloop van de derde vogel wordt de totaalscore
bijgewerkt: 1 treffer geeft 1 punt, 2 geven 5 punten en 3 geven 10 punten.
Zonder treffers wordt het totaal gehalveerd, afgerond naar beneden.
Een nieuwe ronde wist alleen de rondetreffers, niet de totaalscore.
De 16-bit score stopt bij 65535 in plaats van terug te springen naar nul.

RAM 33h bevat de rondetreffers, 34h/35h de totaalscore, 36h de resterende
te verversen cijfers en 37h..3bh de decimale cijfers. Conversie gebeurt
buiten de schermupdate; per VBlank wordt hoogstens een cijfer geschreven.
De vijf cijfers zijn binnen vijf frames bijgewerkt. Code en data eindigen
op 07e9h, volledig in MB0; de ROM blijft 2048 bytes.

PAL- en NTSC-tests controleren echte joysticktreffers, uitgestelde bijtelling,
alle vier ronde-uitkomsten, oneven halvering, nul, carry, maximumscore,
de decimale cijfers en hun VDC-tekencodes. Rekengrenzen worden getest via
RAM-fixtures waarna de echte ROM de ronde afhandelt. Beide modi doorlopen
meer dan 3500 frames zonder onveilige VDC-writes, MB1-uitvoering of
kleurwissels buiten HBlank. De horizon blijft op regel 150.
Het scorebeeld is visueel gecontroleerd; niet opnieuw op fysieke hardware getest.

## Bronnen

- De meegeleverde `../PROGRAMMING MANUAL.md` van Soeren Gust: paragrafen
  2.6 (vectoren), 9.1 (VSYNC), 10.1 (MB0/MB1), 16.4 (sprites) en
  17.14-17.17/17.45-17.49 (BIOS-aanroepen en gereserveerd RAM).
- [libretro O2EM](https://github.com/libretro/libretro-o2em), revisie
  `679d6fec04963f6e70a7ec217e3d0ebb1fe472fc`: `src/cpu.c`, `src/vdc.c`,
  `src/vmachine.c` en `libretro.c` voor uitvoering en timingcontrole.
