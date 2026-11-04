# three.js r161 (MIT)

`three.module.js` and `RoomEnvironment.js` are unmodified copies from
https://github.com/mrdoob/three.js at 0.161.0, MIT licensed, vendored so the
equipment renderer (`scene.js`) runs offline and reproducibly. They ship with
the package: the build scripts render the 3D set with them, `Iso(...)` renders
an item by spec with them in headless Chromium, and a page that can build 3D
items embeds them (`iso3d/bundle.py`). `THIRD_PARTY_LICENSES.md` credits them.
