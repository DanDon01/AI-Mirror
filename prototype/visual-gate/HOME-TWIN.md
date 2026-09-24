# Live miniature home

The existing SmartHomeModule remains the sole Home Assistant client. The bridge
reuses its full state snapshot (including attributes), polls HA every five seconds,
and rejects snapshots older than thirty seconds. The browser polls the local
bridge every two seconds. Very short motion pulses between HA polls can be missed.

Existing upstairs/downstairs temperature, curtain, occupancy, light, solar,
consumption and car SOC mappings are preserved. Additional environment aliases:

- VISUAL_GATE_CAR_CHARGING: actual charging entity, never scheduled dispatch.
- VISUAL_GATE_DOORBELL_PERSON: person activity near the entrance.
- VISUAL_GATE_FRONTCAMERA_MOTION: front exterior motion.

These variables hold entity IDs. No environment file or credentials are changed.
Optional room light entities and home battery mappings are also exposed in the
control panel. Home battery indication stays absent unless telemetry is configured.
The exterior camera is provisionally placed above the porch; this is an area
representation, not a surveyed location. Presence figures indicate sensor areas,
not measured person coordinates.

The former green strip was the decorative plinth using the old CSS .band fill,
not real energy or temperature data. Both its polygons and material were removed.
Architecture now uses fixed projected 3D coordinates; the car uses lofted bodywork,
window planes, curved tyres and wheel arches rather than box primitives.

## Verification

Run test_home_twin.py with Python and test_home_twin.js with Node.

test_house_layout.js (Node) is the real-home architecture lock. It builds the
renderer's scene with WebGL output stubbed and compares every object's
position and extent with fixtures/house-layout.golden.json. It fails on a 1 cm
move. Regenerate the golden file with --update only after owner sign-off.
qa_home.py uses Chrome to capture the production DOM/CSS/panel renderer at
1440 x 2560, with explicitly isolated synthetic sensor cases. It never modifies
the live endpoint. Ignored shots/home-*.png include full frames and detail crops.

Visually inspected idle, ground/first-floor temperatures, closed curtains with
motion/charging, and partial curtains. Garage attachment, downslope flush array,
no green plane, vehicle silhouette, visible curtain differences, tiny camera
housings, mapped presence and non-overlapping captions checked in those renders.
Real HA connectivity, hardware performance and readability through the physical
mirror still require checking on the Pi.
