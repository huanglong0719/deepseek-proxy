import sys, os, traceback
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
if not DEEPSEEK_API_KEY:
    print('ERROR: DEEPSEEK_API_KEY 环境变量未设置，请先设置后再启动代理')
    sys.exit(1)
LOG_PATH = os.path.join(os.path.expanduser('~'), '.codex', 'proxy_debug.log')
log = open(LOG_PATH, 'w', encoding='utf-8')
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
