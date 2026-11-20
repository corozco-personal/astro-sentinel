"""
Logger seguro para entornos concurrentes y procesos desacoplados en segundo plano.
Previene errores de tipo `ValueError: I/O operation on closed file.` cuando stdout/stderr se cierran.
"""
import sys
import logging
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / "outputs" / "scanner.log"
LOG_FILE.parent.mkdir(exist_ok=True)

def safe_print(*args, **kwargs):
    text = " ".join(str(a) for a in args)
    # Intentar escribir a stdout normal
    try:
        if sys.stdout and not sys.stdout.closed:
            print(*args, **kwargs)
            sys.stdout.flush()
            return
    except Exception:
        pass
    
    # Si stdout está cerrado o falló, guardar en archivo seguro
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
