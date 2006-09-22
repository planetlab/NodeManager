forward_api_calls: forward_api_calls.c
	$(CC) -Wall -Os -o $@ $?
	strip $@
clean:
	rm -f forward_api_calls
.PHONY: clean
