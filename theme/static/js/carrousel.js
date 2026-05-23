/* Autoplay fade carrousel. canAutoplay() composes four pause sources
   (hover, focus, tab-hidden, prefers-reduced-motion) — handlers update
   state and call start()/stop(); start() is a no-op when any source
   asks to pause. */
(function () {
  "use strict";

  const MIN_INTERVAL_MS = 2000;
  const DEFAULT_INTERVAL_MS = 60000;
  const reduceMotionMql = window.matchMedia("(prefers-reduced-motion: reduce)");

  function clampInterval(raw) {
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return DEFAULT_INTERVAL_MS;
    return Math.max(MIN_INTERVAL_MS, n);
  }

  function setupCarrousel(carrousel) {
    const slides = Array.from(carrousel.querySelectorAll(".carrousel__slide"));
    const dots = Array.from(carrousel.querySelectorAll(".carrousel__dot"));
    if (slides.length < 2) return;

    const interval = clampInterval(carrousel.dataset.interval);
    let current = 0;
    let timer = null;
    let hovered = false;
    let focused = false;

    function show(next) {
      next = ((next % slides.length) + slides.length) % slides.length;
      if (next === current) return;
      slides[current].classList.remove("is-active");
      slides[next].classList.add("is-active");
      if (dots[current]) {
        dots[current].classList.remove("is-active");
        dots[current].setAttribute("aria-pressed", "false");
      }
      if (dots[next]) {
        dots[next].classList.add("is-active");
        dots[next].setAttribute("aria-pressed", "true");
      }
      current = next;
    }

    function canAutoplay() {
      return !hovered && !focused && !document.hidden && !reduceMotionMql.matches;
    }

    function start() {
      if (timer || !canAutoplay()) return;
      timer = window.setInterval(() => show(current + 1), interval);
    }

    function stop() {
      if (!timer) return;
      window.clearInterval(timer);
      timer = null;
    }

    function sync() { stop(); start(); }

    dots.forEach((dot, idx) => {
      dot.addEventListener("click", () => { show(idx); sync(); });
    });

    carrousel.addEventListener("mouseenter", () => { hovered = true; stop(); });
    carrousel.addEventListener("mouseleave", () => { hovered = false; start(); });
    carrousel.addEventListener("focusin",    () => { focused = true; stop(); });
    carrousel.addEventListener("focusout",   () => { focused = false; start(); });
    document.addEventListener("visibilitychange", sync);
    reduceMotionMql.addEventListener("change", sync);

    start();
  }

  function init() {
    document.querySelectorAll("[data-carrousel]").forEach(setupCarrousel);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
