/* The hologram house renderer slot.

   The example house ships as the classic renderer only (js/home-twin.js), so
   HomeHolo stays undefined here and the page draws the classic even when
   Mirror Controls asks for the hologram (panels.js checks for HomeHolo).

   A house pack can supply its own hologram at visual-gate/js/home-holo.js,
   defining HomeHolo with mount(el), update(state) and setTuning(tuning) and
   drawing on the shared stage (js/stage.js). */
