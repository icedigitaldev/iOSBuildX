# Plan futuro

Lo que falta por hacer y de dónde sacarlo. Nada de esto está implementado: está escrito para
retomarlo con contexto. Cuando se implemente una parte, pasa a [ARQUITECTURA.md](ARQUITECTURA.md)
y sale de aquí.

**Proyecto de referencia:** [xtool](https://github.com/xtool-org/xtool) (MIT), un reemplazo de
Xcode para apps SwiftPM en Linux. No compila Flutter ni CocoaPods, pero ya resolvió varias piezas
que aquí siguen siendo manuales. Las rutas `Sources/...` de este documento son de ese repo.

## Prioridades

| # | qué | esfuerzo | por qué |
|---|---|---|---|
| 1 | Versiones derivadas del SDK, no fijadas a mano | bajo | hoy `06-swift.sh`, `03-toolchain.sh` y el resource dir de clang llevan `6.2.3`, `26.2` y `17` escritos a mano |
| 2 | SDK desde `Xcode.xip` | medio | quita la única dependencia de un Mac y permite ir siempre al Xcode más reciente |
| 3 | Certificados y perfiles por la API de App Store Connect | bajo | `signing/` deja de renovarse a mano en la web |
| 4 | Subida por la API oficial (`buildUploads`) | medio | deja `iris`, la API privada que hatch sacó por ingeniería inversa |
| 5 | Ruta Swift nativa | medio-alto | apps iOS nativas con el mismo `release.sh` |
| 6 | Instalar y lanzar en el iPhone | medio | probar sin pasar por TestFlight ni gastar números de build |
| 7 | Otros frameworks (Capacitor, React Native...) | alto | ver la tabla del final; dependen de la 5 |

Antes de añadir piezas nuevas: [reorganizar en carpetas](#orden-del-código).

## 1. Versiones derivadas del SDK

Swift está fijado en 6.2.3 porque los `.swiftinterface` del SDK 26.2 los construyó
`swiftlang-6.2.3.3.2`. Si el compilador no coincide: *"this SDK is not supported by the compiler"*.
Esa es la razón de que no se pudiera subir a una versión más moderna: **quien manda la versión de
Swift es el SDK**, no la preferencia.

Si se lee del propio SDK, actualizar Xcode actualiza todo lo demás solo:

- **Swift:** la cabecera de cualquier `.swiftinterface` del SDK
  (`// swift-compiler-version: Apple Swift version X (swiftlang-Y)`) dice la versión exacta. Se
  instala esa versión desde swift.org (o con `swiftly`) y `/opt/swift` apunta a ella.
- **Versión del SDK:** `SDKSettings.json` (`Version`), en lugar de `iPhoneOS26.2.sdk` escrito en
  `03-toolchain.sh` y `06-swift.sh`.
- **Resource dir de clang:** listar `usr/lib/clang/*` en lugar de fijar `17`.
- Con eso, `env.sh` avisa si algo no coincide, como ya hace con `gen_snapshot` y Flutter.

## 2. SDK desde `Xcode.xip`

Referencia: `Sources/XToolSupport/SDKBuilder.swift`. Extrae con
[unxip](https://github.com/saagarjha/unxip) (LGPL-3.0; se usa como herramienta, no se enlaza).

- La lista de rutas que conserva (`SDKEntry.wanted`) es la misma que hoy sale de la macVM: el
  `.sdk`, `Toolchains/XcodeDefault.xctoolchain/usr/lib/{swift,clang}` y
  `Platforms/iPhoneOS.platform/Developer/{Library/Frameworks,Library/PrivateFrameworks,usr/lib}`.
  **Diferencia:** `xcode-darwin-roots.tar.gz` incluye además
  `Toolchains/XcodeDefault.xctoolchain/usr/include`, que esa lista no tiene. Hay que confirmar si
  está en el xip antes de dejar de usar el Mac.
- `xcode-version.plist` está dentro del xip, en `Xcode.app/Contents/version.plist`.
- `macos-SystemVersion.plist` **no** está en el xip. `41-stamp.py` necesita
  `BuildMachineOSBuild`, así que hace falta una tabla "Xcode → build de macOS pública" en el repo.
- El `.xip` (3-4 GB) se baja a mano desde developer.apple.com con el Apple ID; xtool también lo
  pide así. Se extrae en `/out` y no en el disco de la VM: extraído pasa de 10 GB y `--storage` no
  se puede agrandar.
- Hay que respetar los hardlinks del xip: xtool extrae todo y filtra después, porque si filtra
  durante la extracción algunos enlaces apuntan fuera de lo conservado (comentario en
  `_extractXIP`).
- Al cambiar de Xcode: bajar el `.xip`, correr el script nuevo y dejar que el punto 1 ajuste Swift.

## 3. Certificados y perfiles por API

Referencia: `Sources/XKit/DeveloperServices/` (sobre todo `Certificates/`, `Profiles/`,
`Devices/` y `OpenAPI/ASCKey.swift`).

- Usa la API pública de App Store Connect con la misma llave que ya usa `50-asc.py`
  (`signing/AuthKey_*.p8`): `/v1/certificates`, `/v1/profiles`, `/v1/bundleIds` y `/v1/devices`.
- Un `certs.py` que genere el CSR con openssl, cree o renueve `dist.cer` y el `.mobileprovision`,
  y registre el UDID para el perfil de desarrollo que necesita el punto 6.
- El modo Apple ID + contraseña de xtool (`GrandSlam/`, anisette) sirve para cuentas gratuitas.
  No hace falta y es lo más frágil de xtool.

## 4. Subida por la API oficial

Ya estaba anotado en ARQUITECTURA → "Lo que falta". Apple publicó `POST /v1/buildUploads` +
`buildUploadFiles`. Va en el mismo módulo que `50-asc.py`, con la misma llave, y quita la última
dependencia de hatch fuera de la compilación.

## 5. Ruta Swift nativa

No hay que reimplementarla: se usa **xtool como herramienta externa** y aquí se pone lo común (SDK,
firma, App Store Connect). `release.sh` elige la ruta por lo que encuentre en el proyecto:
`pubspec.yaml` → Flutter, `Package.swift` → nativo.

- Referencia: `Sources/PackLib/` (de SwiftPM a `.app`: `Planner.swift`, `Packer.swift`) y el
  `OpenAppleMacros` que instala `SDKBuilder.installMacros`, sin el cual las macros de SwiftUI
  (`#Preview`, `@Entry`...) no compilan en Linux.
- **Riesgo:** xtool pide Swift 6.4 y el SDK actual pide 6.2.3. Con el punto 1 hecho y un Xcode más
  nuevo puede que coincidan; si no, van en dos toolchains (`swiftly`) o en una segunda máquina
  smolvm.
- Mismos huecos que Flutter: sin `actool` ni `ibtool`, nada de storyboards ni catálogos de assets
  arbitrarios.

## 6. Instalar y lanzar en el iPhone

Referencia: `Sources/XKit/Installation/` y `Sources/XToolSupport/{InstallCommand,LaunchCommand}.swift`
(libimobiledevice vía SwiftyMobileDevice).

- smolvm no pasa USB a la VM: esto corre **en Windows**.
- Mejor [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) que libimobiledevice: en
  iOS 17+ monta la imagen de desarrollo personalizada. En xtool ese código (`DDIMounter.swift`)
  está desactivado con `#if false`.
- Necesita una segunda firma del mismo `.ipa` con certificado de **desarrollo** y un perfil con el
  UDID (punto 3), y el Modo Desarrollador activado en el iPhone. `rcodesign` ya firma con eso.

## 7. Otros frameworks

Prioridad: **Flutter y Swift nativo primero.** El resto se apoya en la ruta nativa (punto 5) y en
el compilador de pods que ya existe (`20-podgraph.rb`, `21-podbuild.py`).

| framework | qué hay que añadir | viable sin Mac |
|---|---|---|
| **Capacitor** (Ionic) | build web → `App/public`; el resto es una app Swift nativa con plugins en pods o SwiftPM | sí; el más cercano |
| **React Native** | Hermes compila el bundle JS en Linux; muchos pods con C++; el codegen de la nueva arquitectura corre en `script_phases`, que hoy no se ejecutan | sí, pero el más trabajoso |
| **Tauri 2** | Rust se cruza a `aarch64-apple-ios` con este mismo SDK; el envoltorio es un proyecto Xcode | probable; hay que probarlo |
| **Kotlin Multiplatform** | Kotlin/Native solo compila targets de Apple en un host macOS | no |
| **.NET MAUI** | el build de iOS exige Xcode en un Mac | no |

Los dos "no" hay que revisarlos de vez en cuando: dependen de decisiones de JetBrains y Microsoft,
no de Apple.

## Orden del código

Hoy son unos 20 scripts en la raíz con prefijo numérico, y a este tamaño se leen bien. Con lo de
arriba pasarían de 30, así que conviene agruparlos por responsabilidad, como `Sources/` en xtool:

```
iOSBuildX/
├── release.sh        # único punto de entrada
├── env.sh
├── app.env.example
├── setup/            # una vez: 00-bootstrap … 09-shim, 11-gensnapshot
├── sdk/              # from-xip + tabla Xcode → macOS (puntos 1 y 2)
├── flutter/          # 10-sync, 20-podgraph, 21-podbuild, 30-build, 31-resources, frontend_server.sh
├── swift/            # ruta nativa vía xtool (punto 5)
├── sign/             # 40-sign, 41-stamp, 02-minos, certs.py (punto 3)
├── asc/              # 50-asc, upload (punto 4)
├── device/           # corre en Windows: install / launch (punto 6)
├── docs/             # ARQUITECTURA, CREDITOS, PLAN
└── vendor/  signing/  out/
```

- Dentro de cada carpeta se mantienen los números (`flutter/20-podgraph.rb`) para que se siga
  viendo el orden.
- Los scripts se llaman entre sí con rutas absolutas `/out/<archivo>`: `release.sh`, `env.sh` y el
  shim de `09-shim.sh`, que redirige a `21-podbuild.py`. El movimiento va en una fase propia, sin
  cambiar lógica, y se comprueba con un build completo.
- Se hace **antes** de añadir las piezas nuevas.
