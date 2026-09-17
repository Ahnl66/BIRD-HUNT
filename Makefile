ASL ?= asl
P2BIN ?= p2bin

.PHONY: all rebuild
all: bird-hunt.bin

bird-hunt.bin: bird-hunt.asm include/g7000.h
	"$(ASL)" -cpu 8048 -L bird-hunt.asm
	"$(P2BIN)" bird-hunt.p bird-hunt.bin -r 1024-3071

rebuild:
	$(MAKE) -B all
