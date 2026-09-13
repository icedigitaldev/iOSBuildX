import re, pathlib
p = pathlib.Path("/root/iospoc/iossdk/iPhoneOS26.2.sdk/usr/include/DarwinFoundation1.modulemap")
s = p.read_text()
pat = re.compile(r"module _c_standard_library_obsolete \[system\] \{.*?\n\}\n", re.S)
new, n = pat.subn("", s)
print("bloques eliminados:", n)
if n:
    p.write_text(new)
