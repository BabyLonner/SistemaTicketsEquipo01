# ======================================================================
#  Copia ESTE contenido en el archivo WSGI de PythonAnywhere:
#  Web > (tu app) > "WSGI configuration file"  (/var/www/jcachay_pythonanywhere_com_wsgi.py)
#  Cambia la ruta si tu carpeta tiene otro nombre.
# ======================================================================
import os
import sys

RUTA_PROYECTO = "/home/jcachay/mesa_ayuda_ti"
if RUTA_PROYECTO not in sys.path:
    sys.path.insert(0, RUTA_PROYECTO)
os.chdir(RUTA_PROYECTO)

from run import app as application  # noqa: E402
