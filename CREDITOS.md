# De dónde sale cada cosa

Este repositorio es **pegamento**: unos scripts que conectan herramientas que ya existían
y que hizo otra gente. Casi todo el trabajo duro es de ellos. Lo propio aquí son la
resolución de dependencias nativas con CocoaPods fuera de Xcode, el compilador de pods y
el arreglo de los detalles que impedían que la cadena cerrara en Linux.

## Lo que hace el trabajo

| proyecto | qué aporta | licencia |
|---|---|---|
| [hatch](https://github.com/mario-chamuty/hatch) + [hatch-ios-plugin](https://github.com/mario-chamuty/hatch-ios-plugin) | Dart AOT, `App.framework`, `Assets.car`, enlazado del Runner, empaquetado, firma y subida. **Es la pieza central**: sin esto no hay nada | MIT / Apache-2.0 |
| [CocoaPods](https://github.com/CocoaPods/CocoaPods) | resuelve qué dependencias nativas hay y con qué flags se compila cada una | MIT |
| [Swift](https://swift.org) | el compilador que cruza a `arm64-apple-ios` | Apache-2.0 |
| [cctools-port](https://github.com/tpoechtrager/cctools-port) | `ld64`, `libtool`, `otool` y compañía para Linux | APSL-2.0 / GPL-2.0 |
| [apple-codesign (rcodesign)](https://github.com/indygreg/apple-platform-rs) | firma sin `codesign` de Apple | MPL-2.0 |
| [Flutter](https://github.com/flutter/flutter) | el engine y `gen_snapshot` | BSD-3-Clause |

[xcross](https://xcross.sh) sirvió de referencia para la parte de SwiftPM, aunque al final
no se usa: solo hace builds debug y exige un `Xcode.xip` completo.

## Lo que no está aquí y tienes que poner tú

El **SDK de iOS y los resource dirs de Xcode no se redistribuyen**: son de Apple y su
licencia no lo permite. Salen de tu propia instalación de Xcode, en un Mac o en una VM
macOS tuya, y nunca entran al repositorio (`vendor/` está en `.gitignore`).

Lo mismo con tu certificado de distribución, tu perfil y tu API key: `signing/` y
`app.env` tampoco se versionan.

## Licencia

Los scripts de este repositorio van bajo [MIT](LICENSE). Cubre **solo estos scripts**:
cada herramienta de la tabla de arriba mantiene la suya, y el SDK de Apple se rige por su
propio acuerdo.

Si construyes algo encima, el crédito que de verdad importa es el de
[hatch](https://github.com/mario-chamuty/hatch): es la pieza sin la que esto no existiría.
