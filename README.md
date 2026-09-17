# BIRD HUNT

Een homebrew schietspel voor Philips Videopac G7000 / Magnavox Odyssey2,
geschreven in Intel 8048 assembly. De speelbare ROM is `bird-hunt.bin` (2048 bytes).

## Spelen

Beweeg het vizier met de joystick en druk op vuur om te schieten.
Laat de vuurknop los tussen schoten. Elke ronde verschijnen drie vogels,
een voor een, met verschillende vliegpaden. Je hebt vijf schoten per ronde.
Een geraakte vogel valt naar beneden; een misser geeft een korte witte flits.

Na iedere ronde wordt de totaalscore bijgewerkt:

| Geraakte vogels | Resultaat |
| --- | --- |
| 0 | Totaal halveren, naar beneden afgerond |
| 1 | +1 punt |
| 2 | +5 punten |
| 3 | +10 punten |

De score stopt bij 65535. Het speelveld bestaat uit blauwe lucht en groen gras.
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

```sh
python3 check_rom.py /pad/naar/o2em_libretro.dylib /pad/naar/bios bird-hunt.bin PAL
python3 check_rom.py /pad/naar/o2em_libretro.dylib /pad/naar/bios bird-hunt.bin NTSC
```

Beide modi zijn getest op rondes, schoten, treffers, score en schermtiming.
`REVIEW.md` bevat het historische technische verslag onder de oude werknaam.
