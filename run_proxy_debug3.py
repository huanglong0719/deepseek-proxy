import sys, os, traceback
os.environ['DEEPSEEK_API_KEY'] = 'sk-481740aa0afc4f429292b51a46ab0dfc'
log = open(r'c:\Users\long\.codex\proxy_debug.log', 'w', encoding='utf-8')
class Tee:
    def __init__(self, *streams): self.streams = streams
    def write(self, data):
        for s in self.streams: s.write(data)
        for s in self.streams:
            try: s.flush()
            except: pass
    def flush(self):
        for s in self.streams:
            try: s.flush()
            except: pass
sys.stdout = Tee(sys.stdout, log)
sys.stderr = Tee(sys.stderr, log)
log.write("=== PROXY START ===\n")
log.flush()
try:
    import deepseek_proxy
    deepseek_proxy.run_server()
except SystemExit as e:
    log.write(f"SystemExit: {e.code}\n")
except Exception as e:
    log.write(f"FATAL: {e}\n")
    traceback.print_exc(file=log)
finally:
    log.write("=== PROXY EXIT ===\n")
    log.close()
