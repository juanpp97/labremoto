#!/usr/bin/env bash
# Regenera las imágenes SVG de los diagramas a partir de su código Mermaid (*.mmd).
#
# Uso:
#   ./render.sh                     # todos los diagramas
#   ./render.sh 06-estados-del-lease.mmd
#
# Requiere Node.js. Por defecto usa mermaid-cli vía npx (descarga Chromium la primera vez).
# Variables opcionales:
#   MMDC              comando de mermaid-cli a usar (p. ej. la ruta a un mmdc ya instalado)
#   PUPPETEER_CONFIG  JSON de puppeteer, p. ej. para usar el Chrome instalado:
#                     {"executablePath": "C:/Program Files/Google/Chrome/Application/chrome.exe"}
#
# Todos los diagramas comparten mermaid-config.json (tema, tipografía y colores) y se
# exportan con fondo blanco, así se ven igual en cualquier visor, con tema claro u oscuro.
set -euo pipefail
cd "$(dirname "$0")"

MMDC="${MMDC:-npx --yes -p @mermaid-js/mermaid-cli@11 mmdc}"
EXTRA=()
if [ -n "${PUPPETEER_CONFIG:-}" ]; then
  EXTRA=(-p "$PUPPETEER_CONFIG")
fi

files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  files=(*.mmd)
fi

for f in "${files[@]}"; do
  $MMDC -c mermaid-config.json -i "$f" -o "${f%.mmd}.svg" -b white -q ${EXTRA[@]+"${EXTRA[@]}"}
  echo "ok  ${f%.mmd}.svg"
done
