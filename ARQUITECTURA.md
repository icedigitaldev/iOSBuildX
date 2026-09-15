# Cómo está armado

Toolchain Darwin dentro de smolvm (Linux x86_64) que compila una app Flutter a `.ipa`
arm64 con Dart AOT. Verificado el 12 sep 2026 con Educanet 0.8.5+20 completa: 15 plugins,
43 pods nativos resueltos y compilados (Firebase, MLKit, ONNX Runtime, Google Sign-In),
295 objetos arm64, 42,6 MB, en 151 s.

Para usarlo: [README.md](README.md). Este documento es por qué está hecho así.

## El flujo

```
proyecto Flutter
      │
      ├── Dart ──────────► Hatch ──► gen_snapshot (AOT) ──► App.framework
      │
      └── pubspec ───────► CocoaPods (Resolver + Analyzer) ──► podgraph.json
                                        │
                                        ▼
                            21-podbuild.py: por cada pod
                              <Modulo>.framework  +  objetos arm64
                                        │
                     SDK iOS + resource dirs de Xcode (de la macVM)
                                        │
                          Hatch: Runner + ld64.lld ──► Runner.app ──► .ipa
                                        │
                                 rcodesign ──► subida
```

Tres piezas, cada una cubre el hueco de la otra:

| pieza | qué aporta | por qué no basta sola |
|---|---|---|
| **Hatch** (`mario-chamuty/hatch` + `hatch-ios-plugin`) | Dart AOT, App.framework, Assets.car, link del Runner, empaquetado, firma, subida | su compilador de plugins está marcado `INTERIM` y trae rutas Windows del autor |
| **CocoaPods** (la gema completa) | qué dependencias hay, de dónde salen y con qué flags se compila cada una | no compila nada fuera de Xcode |
| **Toolchain Darwin** (Swift de swift.org + SDK y resource dirs de Xcode) | Swift/ObjC/ObjC++ → `arm64-apple-ios` | no sabe nada de Flutter ni de pods |

## Qué sale de la macVM

Dos tarballs y dos plist, una vez, a `vendor/`. No hace falta `Xcode.xip`.

```bash
# SDK. OJO: iPhoneOS26.2.sdk es un symlink; hay que empaquetar el real       (32 MB)
ssh mac 'cd /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs && tar cf - "$(readlink -f iPhoneOS26.2.sdk | xargs basename)" | gzip -1' > C:\ruta\a\este\repo\vendor\iPhoneOS26.2.sdk.tar.gz

# resource dirs del toolchain + frameworks del platform                      (622 MB)
ssh mac 'cd /Applications/Xcode.app/Contents/Developer && tar cf - Toolchains/XcodeDefault.xctoolchain/usr/lib/swift Toolchains/XcodeDefault.xctoolchain/usr/lib/clang Toolchains/XcodeDefault.xctoolchain/usr/include Platforms/iPhoneOS.platform/Developer/Library/Frameworks Platforms/iPhoneOS.platform/Developer/Library/PrivateFrameworks Platforms/iPhoneOS.platform/Developer/usr/lib | gzip -1' > C:\ruta\a\este\repo\vendor\xcode-darwin-roots.tar.gz

# versión de Xcode y del macOS que lo tiene, para los DT* del Info.plist
ssh mac 'cat /Applications/Xcode.app/Contents/version.plist' > C:\ruta\a\este\repo\vendor\xcode-version.plist
ssh mac 'cat /System/Library/CoreServices/SystemVersion.plist' > C:\ruta\a\este\repo\vendor\macos-SystemVersion.plist
```

`00-bootstrap.sh` deja el toolchain en `/root/iospoc`:

```
engine/            artefactos del engine Flutter          1,5 GB
iossdk/            SDK iOS 26.2 parcheado                  72 MB
xc/                resource dirs y frameworks de Xcode    1,6 GB
cctools-port/      cctools + ld64
rcodesign/         apple-codesign 0.29.0
darwin-bin/        libtool, lipo, otool, ar sin prefijo
fw/<App>/          los .framework de las dependencias
work/<App>/        objetos, headers y logs del build
```

## Las dependencias nativas

Esta es la parte que hace que sirva para cualquier app y no solo para Educanet.

**`20-podgraph.rb`** monta un Podfile en memoria con los plugins que declara
`.flutter-plugins-dependencies` y corre el **Installer de CocoaPods** con
`skip_pods_project_generation` e `integrate_targets: false`: resuelve versiones, descarga
los pods y calcula el xcconfig de cada `PodTarget` — el mismo que usaría Xcode. Vuelca a
`podgraph.json` lo que hace falta para compilar: fuentes separadas en ARC y no-ARC,
headers públicos y privados, `header_dir`, defines, search paths, frameworks vendidos,
resource bundles y dependencias.

Nada de eso se deduce ni se mantiene a mano. Antes había listas de pods, de headers que
faltaban, de pods sin ARC y de `-D` por plugin; ya no hay ninguna.

**`21-podbuild.py`** compila ese grafo. Por extensión: `.swift` → swiftc, `.m`/`.c` →
clang, `.mm`/`.cpp` → clang++. Dos fases: primero monta el framework de **todos** los
pods, después compila.

### Por qué frameworks y no un árbol de headers

Cada pod se materializa como `<Modulo>.framework` —lo mismo que produce
`use_frameworks!` en Xcode, que es lo que dice el Podfile de Flutter:

- un framework es **un** módulo con las dos caras dentro (`Modules/*.swiftmodule` y
  `Modules/module.modulemap`), así que `import X` da a la vez la API Swift y la ObjC. Con
  los dos árboles separados, un pod Swift consumido desde otro acaba viendo dos tipos
  distintos con el mismo nombre, y el error aparece a mil kilómetros de la causa
  (`Storage.storage(app:url:)` → *"extra argument 'app' in call"*);
- un header solo es alcanzable por una ruta, `Headers/`. Visible por dos, clang lo declara
  dos veces: *"duplicate interface definition"*;
- se descubren con `-F`, sin listas de `-fmodule-map-file`.

El framework de un pod compilado de fuente no lleva su código —los objetos van a `obj/`,
que es lo que enlaza hatch— pero sí un archivo estático con un objeto vacío dentro: hatch
pasa `-framework` para todo lo que encuentra en el directorio y sin binario el enlazador
no lo halla.

### Un solo contexto para todas las compilaciones

clang identifica un módulo por el hash de los flags con que se construyó. Si cada pod
aporta sus propios `-I`, `-F` o `-target`, el `FirebaseCore` que grabó el `.swiftmodule`
de `FirebaseStorage` y el que construye `firebase_core` son dos módulos distintos, con dos
`FIRApp` que ya no unifican. Por eso el mínimo de iOS, los search paths y la caché de
módulos son únicos para todo el grafo. El mínimo sale del Podfile de la app (`max` con el
que exija el pod más nuevo), igual que hace el `post_install` de Flutter.

## Las decisiones que no son obvias

**El `gen_snapshot` es de iOS.** El snapshot AOT declara sistema operativo y punteros
comprimidos (`arm64 ios no-compressed-pointers`) y tiene que coincidir con el
`Flutter.framework`. Flutter publica ese `gen_snapshot` solo para macOS, así que
`11-gensnapshot.sh` lo compila para Linux desde el Dart SDK con `target_os` fijado a iOS en
`dart_os_config`. `env.sh` lo instala en cada build y `40-sign.sh` verifica las features del
`App.framework`.

**La versión de Swift la manda el SDK, no el Xcode.** Xcode 26.3 reporta Swift 6.2.4, pero
los `.swiftinterface` del SDK 26.2 los construyó swiftlang-6.2.3.3.2: hay que instalar
**Swift 6.2.3**. Si no coincide: *"this SDK is not supported by the compiler"*.

**Los resource dirs tienen que ser los de Xcode**, no los del Swift de Linux. Con los de
Linux salen 658 errores de `redefinition of module 'Dispatch'` porque sus module maps
chocan con los del SDK Darwin. Van por `-resource-dir` (swift) y `-Xcc -resource-dir`
(clang).

**Dos parches al SDK** para el clang de Ubuntu: borrar el módulo
`_c_standard_library_obsolete` de `usr/include/DarwinFoundation1.modulemap`, que exige una
feature que solo existe en el clang de Apple; y enlazar `System/Library/SubFrameworks/*`
dentro de `System/Library/Frameworks/`, o `UIKitDefines.h` no encuentra
`UIUtilities/UIDefines.h`.

**La máquina smolvm va con `--net-backend virtio-net`.** Con el backend TSI, que es el
default, los sockets de Dart fallan con `errno 107` mientras curl y python funcionan: `pub`
no resuelve nunca. No se puede cambiar después de crear la máquina.

**El `-Swift.h` generado nunca se excluye del umbrella** aunque contenga `namespace`: ese
bloque está detrás de `#if __cplusplus` y es la cara ObjC del propio módulo. Excluirlo deja
al pod Swift sin interfaz para sus consumidores ObjC.

**Foundation/UIKit solo entran en el umbrella de un pod ObjC.** Muchos pods dan por hecho
el prefix header precompilado de Xcode y no importan nada; ponérselo a uno de C puro
(nanopb) rompe su módulo en cuanto se construye desde un `.c`.

**El mínimo de iOS sale de `MIN_OS` y de ningún otro sitio.** hatch lo lleva fijo en 13.4
dentro del binario —no mira el `AppFrameworkInfo.plist`, ni el `.xcodeproj`, ni el engine—
y no es configurable: el esquema de `~/.hatch/ios.json` solo acepta `asc`, `signing`,
`team_id`, `bundle_id`, `wsl_distro` y `toolchain_root`. Con 13.4 App Store Connect avisa
con ITMS-90068 y a partir de 2027 rechazará por debajo de 15.0. `02-minos.py` cambia ese
valor en sitio (es un inmediato de 4 bytes, misma longitud) y `env.sh` lo reajusta en cada
build, así que el binario nunca se desincroniza de `MIN_OS`. El mismo número va al
resolver de CocoaPods y al `-target` de cada pod: si viniera de tres sitios distintos
acabarías con los pods compilados para una versión y la app declarando otra.

**Los pods Swift se compilan con `-parse-as-library`.** Sin eso, un pod de un solo fichero
se compila en modo script y emite un `main` que choca con el del Runner.

**El SDK y el Xcode del `Info.plist` salen de los ficheros de Apple, no de hatch.** hatch
estampa `DTSDKBuild=23A340` y `DTXcodeBuild=17A324` fijos: el primero es el iOS 26.0 RC
de dispositivo, que ningún Xcode público llevó como SDK, y App Store Connect lo cataloga
como beta y no deja mandar el build a revisión (TestFlight sí lo acepta, así que el fallo
aparece tarde). Son constantes del código Rust, de longitud distinta a las reales, así que
no se parchean como el `MinimumOSVersion`: `40-sign.sh` compila sin firmar, `41-stamp.py`
reescribe los `DT*` y `BuildMachineOSBuild` con lo que dicen `SystemVersion.plist` y
`SDKSettings.json` del SDK, el `version.plist` de Xcode y el `SystemVersion.plist` del
macOS —los mismos ficheros que consulta Xcode— y alinea el campo `sdk` de
`LC_BUILD_VERSION` de cada Mach-O, y después se firma igual que lo hace hatch.

## Lo que falta

- **Assets.car**: hatch no tiene `actool`; usa un catálogo donante y da por hecho el
  iconset de 25 entradas que genera `flutter_launcher_icons`. Una app con otro catálogo,
  storyboards o app extensions puede descubrir otro hueco.
- **La subida** va por `iris`, la API privada de Transporter que hatch sacó por ingeniería
  inversa. Apple ya publicó `POST /v1/buildUploads` + `buildUploadFiles` oficial; migrar a
  esa sería la mejora más clara.
- **`script_phases` de los pods no se ejecutan** (se avisa en el resumen). Ninguno de los
  43 de Educanet las usa.

