ASL ?= asl
P2BIN ?= p2bin

.PHONY: all rebuild
all: bird-hunt.bin

bird-hunt.bin: bird-hunt.asm plus-loader.inc include/g7000.h tools/build_rom.py assets/g7400/patterns.bin assets/g7400/screen.bin
	ASL="$(ASL)" P2BIN="$(P2BIN)" python3 tools/build_rom.py

rebuild:
	$(MAKE) -B all
