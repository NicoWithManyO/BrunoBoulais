/* Autoplay fade carrousel. Pause sources are coalesced via a counter:
   hover, focus, tab-hidden, and explicit dot interaction each push/pop
   the count; autoplay only runs when the count is 0. Honors
   prefers-reduced-motion at decision time (re-read live, so OS toggle
   takes effect without reload). */
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
    let pauseCount = 0;

    function show(next) {
      next = ((next % slides.length) + slides.length) % slides.length;
      if (next === current) return;
      slides[current].classList.remove("is-active");
      slides[next].classList.add("is-active");
      if (dots[current]) {
        dots[current].classList.remove("is-active");
        dots[current].setAttribute("aria-selected", "false");
      }
      if (dots[next]) {
        dots[next].classList.add("is-active");
        dots[next].setAttribute("aria-selected", "true");
      }
      current = next;
    }

    function canAutoplay() {
      return pauseCount === 0 && !reduceMotionMql.matches && !document.hidden;
    }

    function start() {
      if (timer || !canAutoplay()) return;
      timer = window.setInterval(() => show(current + 1), interval);
    }

    function stop() {
      if (timer) {
        window.clearInterval(timer);
        timer = null;
      }
    }

    function pause() { pauseCount += 1; stop(); }
    function resume() {
      if (pauseCount > 0) pauseCount -= 1;
      start();
    }

    dots.forEach((dot, idx) => {
      dot.addEventListener("click", () => {
        show(idx);
        // Restart the interval timer from this slide; respects current
        // pause state (no-op if hovered/focused/hidden).
        stop();
        start();
      });
    });

    carrousel.addEventListener("mouseenter", pause);
    carrousel.addEventListener("mouseleave", resume);
    carrousel.addEventListener("focusin", pause);
    carrousel.addEventListener("focusout", resume);

    // Tab visibility is global, not a hover/focus interaction — toggle the
    // timer directly without touching pauseCount.
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stop(); else start();
    });

    // Live-reread of the OS reduce-motion preference: re-evaluate
    // autoplay eligibility whenever the system toggles.
    if (typeof reduceMotionMql.addEventListener === "function") {
      reduceMotionMql.addEventListener("change", () => {
        if (reduceMotionMql.matches) stop(); else start();
      });
    }

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
