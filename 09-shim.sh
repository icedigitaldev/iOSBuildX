#!/bin/bash
# hatch-ios invoca `python <ruta>/build_plugins.py <proyecto> <out>`, un script
# Windows-only marcado INTERIM. El shim lo redirige a nuestro compilador, que
# tiene la misma firma y deja la misma salida (obj/, inc/, mod/).
set -euo pipefail
cat > /usr/local/bin/python <<'SHIM'
#!/bin/bash
case "${1:-}" in
  */build_plugins.py)
    shift
    exec python3 /out/21-podbuild.py "$@"
    ;;
esac
exec python3 "$@"
SHIM
chmod +x /usr/local/bin/python
echo "pod build hook installed"
