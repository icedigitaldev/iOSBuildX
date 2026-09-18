#!/usr/bin/env python3
"""Mete en el .app los recursos que declararon los pods.

Es la fase `[CP] Copy Pods Resources` que CocoaPods añade al target de Xcode y
que aquí no existía: 21-podbuild.py compila y enlaza el código del pod, pero sus
recursos se quedaban en out/. Un pod que lee un archivo del bundle en tiempo de
ejecución no se cae al enlazar —el binario está completo— sino la primera vez
que lo busca, y eso pasa dentro del pod, en Objective-C, así que aborta el
proceso sin pasar por Dart. Con MLKit son los modelos del detector de rostro:
`FaceDetector(...)` lanzaba NSException en el constructor.

Dos destinos, los mismos que usa CocoaPods:

  - `resource_bundles` -> <App>.app/<nombre>.bundle
  - `resources`        -> <App>.app/ (la raíz)

Se corre sobre el .app ya montado y **antes de firmar**: lo que entre después
queda fuera de _CodeSignature y Apple rechaza el bundle.

El directorio de salida lo elige hatch y se lo pasa a 21-podbuild.py por
argumento, así que aquí no se puede deducir: se lee de la nota que aquel deja en
/out/out/podbuild-out.txt, o se pasa a mano.

    python3 31-resources.py <ruta/al/Runner.app> [out]
"""
import json, os, shutil, sys

POINTER = "/out/out/podbuild-out.txt"


def podbuild_out():
    """Donde dejó su salida 21-podbuild.py."""
    if len(sys.argv) > 2:
        return os.path.abspath(sys.argv[2])
    try:
        with open(POINTER) as f:
            return f.read().strip()
    except OSError:
        sys.exit("error: %s not found; run 21-podbuild.py first or pass <out>"
                 % POINTER)


APP = os.path.abspath(sys.argv[1])
OUT = podbuild_out()

# Lo que hay que compilar con herramientas que solo trae Xcode (actool, ibtool,
# momc). Copiarlos crudos no sirve de nada, así que se avisa en vez de dejar un
# bundle que parece completo y no lo está.
NEEDS_XCODE = (".xcassets", ".xib", ".storyboard", ".xcdatamodeld", ".xcdatamodel")


def copy_into(src_dir, dest_dir, label):
    """Copia el contenido de [src_dir] en [dest_dir]. Devuelve qué copió y qué
    no pudo."""
    done, skipped = [], []
    if not os.path.isdir(src_dir):
        return done, skipped

    for name in sorted(os.listdir(src_dir)):
        src = os.path.join(src_dir, name)
        if name.endswith(NEEDS_XCODE):
            skipped.append(name)
            continue

        dst = os.path.join(dest_dir, name)
        os.makedirs(dest_dir, exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)
        else:
            shutil.copy2(src, dst)
        done.append(name)

    if done:
        print("%s: %d -> %s" % (label, len(done), os.path.relpath(dest_dir, APP) or "."))
        for name in done:
            print("   ", name)
    return done, skipped


def main():
    if not os.path.isdir(APP):
        sys.exit("error: %s is not an .app bundle" % APP)

    # 21-podbuild.py escribe podbuild.json al terminar. Si no está, no llegó al
    # final, y seguir dejaría una app sin los recursos de sus pods: exactamente
    # el fallo que este paso existe para evitar, y encima en silencio.
    manifest = os.path.join(OUT, "podbuild.json")
    if not os.path.exists(manifest):
        sys.exit("error: %s not found; run 21-podbuild.py first" % manifest)

    # Los directorios se derivan de OUT, no se leen del manifest: es el mismo
    # layout que escribe 21-podbuild.py y así una ruta vieja no puede apuntar a
    # un sitio vacío. Que no existan es legítimo —ningún pod declaró recursos—.
    bundles = os.path.join(OUT, "bundles")
    loose = os.path.join(OUT, "resources")

    copied, skipped = [], []
    for src, dest, label in ((bundles, APP, "bundles"), (loose, APP, "resources")):
        done, miss = copy_into(src, dest, label)
        copied += done
        skipped += miss

    if not copied:
        print("no pod resources to copy")

    for name in skipped:
        print("warning: %s needs Xcode tooling (actool/ibtool/momc); not copied" % name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
