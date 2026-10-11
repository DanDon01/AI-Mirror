# Live miniature home

The energy panel shows a live 3D model of the home. The bridge collects Home
Assistant state through the existing SmartHomeModule (no second HA client),
and the page draws it: lit windows and room lights, anonymous presence figures,
floor temperatures as colour, the front door, the alarm, the car and its
charging, solar export and heavy weather. Nothing is drawn without a real
reading behind it.

## The example house and your own

`js/home-twin.js` is a plain example house built from the `HOUSE` description
at the top of the file: footprint, storeys, rooms, front windows, door, solar
panels and a parking spot. Edit it to resemble your home, using the room keys
the bridge produces (livingroom, kitchen, hallway, bedroom1-3, bathroom, and
the downstairs/upstairs floor temperatures).

For a fully custom model, put your own renderer in your house pack instead:

    house/visual-gate/js/home-twin.js     classic renderer (defines HomeTwin)
    house/visual-gate/js/home-holo.js     optional hologram on the shared stage (HomeHolo)
    house/visual-gate/fixtures/house-layout.golden.json   its architecture lock

The server serves house-pack files in place of the public ones (see
`house_overlay_dir()` in serve.py and `house_pack.py`), so the page needs no
change. A renderer provides `update(state)`, `setTuning(tuning)`, `render()`
and `mount(el)`, which returns a per-frame function with a `dispose()`.

Entity IDs are configured with `VISUAL_GATE_*` variables in `Variables.env`
(see config.py `visual_gate`). The control page's House tab steers the camera,
position and brightness of whichever renderer is in use.

## Verification

    node test_house_layout.js          architecture lock (house pack's, else the example's)
    node test_house_layout.js --holo   hologram solids match, when a hologram exists
    node test_house_layout.js --update rewrite the lock after a deliberate change
    node test_home_twin.js             renderer state checks
    python test_home_twin.py           bridge telemetry checks (no HA needed)
