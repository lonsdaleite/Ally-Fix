/* pulls in the fake steamclient.so as DT_NEEDED, so dlopen() sees only THIS name */
extern unsigned fake_read(void);
unsigned wrap_read(void) { return fake_read(); }
