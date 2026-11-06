"""Start the rig and keep it running until Ctrl-C:  python tools/ha-rig/serve.py [--reset]"""
import argparse, signal, sys, time
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from rig import Rig

ap = argparse.ArgumentParser()
ap.add_argument("--reset", action="store_true"); ap.add_argument("--config-dir")
ap.add_argument("--port", type=int, default=18123); ap.add_argument("--printer-port", type=int, default=18765)
a = ap.parse_args()
signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
rig = Rig(a.config_dir, a.port, a.printer_port, a.reset).start()
import os
open(rig.dir / "serve.pid", "w").write(str(os.getpid()))
print("READY", rig.base, flush=True)
try:
    while rig.proc.poll() is None:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    rig.stop()
