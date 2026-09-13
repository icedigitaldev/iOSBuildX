# iOSBuildX

Compilar una app Flutter a `.ipa` desde Linux.

Sin Mac, sin Xcode instalado y sin CI de pago. Compila, firma y sube a App Store Connect.

Verificado con una app real de 15 plugins —Firebase, MLKit, ONNX Runtime, Google Sign-In—
que resuelve 43 pods nativos: **159 segundos** de código a `.ipa` firmada.

Esto es sobre todo pegamento entre herramientas que hizo otra gente: lee
[CREDITOS.md](CREDITOS.md) antes que nada.

## Qué hace falta

**Una máquina Linux x86_64.** Probado en **Ubuntu 24.04**, y no por casualidad: swift.org
publica binarios oficiales para esa versión, así que el compilador Swift que usa el SDK de
Apple encaja sin trucos. Otra distribución obliga a compilar Swift o a pelearse con glibc.

Sirve cualquier forma de tenerla: una VM, WSL2, un contenedor o un VPS. Aquí se usa
smolvm porque el desarrollo es en Windows:

```powershell
smolvm machine create --net --net-backend virtio-net --dns 192.168.1.1 `
  --name hatch --image ubuntu:24.04 --cpus 8 --mem 6144 --overlay 24 `
  --volume "C:\ruta\a\este\repo:/out"
smolvm machine start --name hatch
```

El `--net-backend virtio-net` no es opcional: con el backend por defecto los sockets de
Dart fallan con `errno 107` y `pub` no resuelve nunca.

**El SDK de iOS y los resource dirs de Xcode**, que no se pueden redistribuir. Salen de tu
propia instalación de Xcode, en un Mac o en una VM macOS tuya. Dos tarballs y dos plist,
una sola vez, a `vendor/`:

```bash
# el SDK; iPhoneOS<versión>.sdk suele ser un symlink, hay que empaquetar el real   (32 MB)
cd /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs
tar czf iPhoneOS26.2.sdk.tar.gz "$(basename "$(readlink -f iPhoneOS26.2.sdk)")"

# resource dirs del toolchain y frameworks del platform                           (622 MB)
cd /Applications/Xcode.app/Contents/Developer
tar czf xcode-darwin-roots.tar.gz \
  Toolchains/XcodeDefault.xctoolchain/usr/lib/swift \
  Toolchains/XcodeDefault.xctoolchain/usr/lib/clang \
  Toolchains/XcodeDefault.xctoolchain/usr/include \
  Platforms/iPhoneOS.platform/Developer/Library/Frameworks \
  Platforms/iPhoneOS.platform/Developer/Library/PrivateFrameworks \
  Platforms/iPhoneOS.platform/Developer/usr/lib

# versión de Xcode y del macOS que lo tiene: van al Info.plist como DTXcode/DTXcodeBuild
# y BuildMachineOSBuild, que App Store Connect coteja contra los Xcode públicos
cp /Applications/Xcode.app/Contents/version.plist xcode-version.plist
cp /System/Library/CoreServices/SystemVersion.plist macos-SystemVersion.plist
```

**Una cuenta de Apple Developer** con un certificado de distribución, un perfil y una API
key de App Store Connect.

## Preparar (una vez)

```bash
bash /out/00-bootstrap.sh
```

Descarga Flutter, hatch, Swift 6.2.3, cctools/ld64, rcodesign y CocoaPods, y parchea el
SDK. Tarda un rato largo la primera vez. Termina con `hatch-ios doctor` en 10/10.

Después, la configuración:

```bash
cp app.env.example app.env     # tu app y los ids de tu cuenta de Apple
```

y en `signing/`: `dist.key`, `dist.cer`, tu `.mobileprovision` y tu `AuthKey_*.p8`.
Ni `app.env` ni `signing/` se versionan.

`MIN_OS` es el iOS mínimo de tu app y es **un solo número para todo**: el resolver de
CocoaPods, el `-target` de cada pod y el `MinimumOSVersion` del bundle. Por defecto 16.0.
El suelo que Apple exigirá desde 2027 es 15.0, así que 16.0 deja margen; bajarlo a 15.0 es
válido y suma iPhone 6s, 7 y SE 1ª gen. Si una dependencia pide más, el propio script te
dice cuál.

## Compilar

Empaqueta el código desde tu máquina y déjalo en `out/`:

```powershell
cd C:\ruta\al\proyecto
tar czf C:\ruta\a\este\repo\out\app.tar.gz lib assets ios pubspec.yaml pubspec.lock
```

Si el proyecto depende de un paquete local, un tarball más con ese paquete; `10-sync.sh`
reescribe la ruta sola.

Y entonces, un comando:

```bash
bash /out/release.sh
```

Mete el código, resuelve las dependencias nativas, compila, firma y valida. Deja la `.ipa`
en `out/`.

**Las dependencias nativas no se declaran en ningún sitio.** `20-podgraph.rb` resuelve el
`pubspec` con CocoaPods —incluido lo que arrastran los plugins— y `21-podbuild.py` las
compila. Un plugin nuevo no necesita tocar nada, y si cambian las dependencias tampoco hay
que limpiar: el grafo se rehace solo y tira lo construido antes.

## Subir

```bash
bash /out/release.sh --publish
```

Comprueba primero que el build del `pubspec.yaml` no esté ya en App Store Connect —uno
subido no se puede borrar, solo caducar— y aborta antes de gastar los tres minutos si lo
está. Para ver qué hay:

```bash
python3 /out/50-asc.py
```

La versión sale del `pubspec.yaml`: `version: 0.8.6+21` → versión 0.8.6, build 21.

## Los scripts

| | |
|---|---|
| `00-bootstrap.sh` | monta el toolchain entero; llama a los `01`–`09` |
| `10-sync.sh` | mete el código en la VM y adapta las rutas locales |
| `20-podgraph.rb` | resuelve las dependencias con CocoaPods → `podgraph.json` |
| `21-podbuild.py` | compila esas dependencias a objetos arm64 |
| `30-build.sh` | compila la app |
| `40-sign.sh` | compila, estampa el SDK y el Xcode reales, firma y valida |
| `41-stamp.py` | escribe en el `Info.plist` y en `LC_BUILD_VERSION` la versión real del SDK y de Xcode |
| `02-minos.py` | ajusta el `MinimumOSVersion` que hatch lleva fijo en 13.4 |
| `50-asc.py` | qué versiones y builds hay ya en App Store Connect |
| `release.sh` | los anteriores en orden, que es lo que usarás |

`env.sh` tiene lo que comparten todos: si solo una parte definiera el entorno, acabarías
firmando algo distinto de lo que compilaste.

`09-shim.sh` instala un `python` en el PATH que intercepta la llamada de hatch a su
`build_plugins.py` y la redirige a `21-podbuild.py`. Es el punto de enganche.

## Errores conocidos

| síntoma | causa |
|---|---|
| `pub` no resuelve nunca | la VM se creó sin `--net-backend virtio-net` |
| `could not find compatible versions for pod X` | algún pod exige un iOS mínimo mayor que tu `MIN_OS`; el propio script te lo dice y la solución es subirlo en `app.env` |
| en revisión: *las apps deben compilarse con las versiones públicas (GM) de Xcode* | el `Info.plist` lleva un SDK/Xcode que no existe como público; lo corrige `41-stamp.py` y falla si faltan los plist de `vendor/` |
| Apple responde **ITMS-90068** | tu `MIN_OS` es menor de 15.0, que es lo que Apple exigirá desde 2027 |
| `frontend_server` sale con **254** | hatch copia `package_config.json` sin absolutizar el `rootUri` del propio paquete; `env.sh` lo reescribe en cada build |
| un pod falla al compilar | su log está en `/root/iospoc/work/<App>/plugout/pod_<Pod>.log`, con el comando exacto en la primera línea |
| `framework not found for -framework X` | el framework de X no llegó al directorio de frameworks: mirar el log de ese pod |
| `duplicate symbol: main` | un pod Swift de un solo fichero compilado sin `-parse-as-library` |
| `rcodesign.exe not found` | hatch lo busca en `<root>/rcodesign029`; el enlace lo deja `03-toolchain.sh` |

## Más

- [ARQUITECTURA.md](ARQUITECTURA.md) — cómo está armado y por qué cada decisión.
- [CREDITOS.md](CREDITOS.md) — de quién es cada pieza.
- [LICENSE](LICENSE) — MIT.
