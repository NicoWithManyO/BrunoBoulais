/* Autoplay fade carrousel — pauses on hover/focus, pauses if the tab is hidden,
   honors prefers-reduced-motion (skips autoplay, dots still work). */
(function () {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function setupCarrousel(carrousel) {
    const slides = Array.from(carrousel.querySelectorAll(".carrousel__slide"));
    const dots = Array.from(carrousel.querySelectorAll(".carrousel__dot"));
    if (slides.length < 2) return;

    const interval = parseInt(carrousel.dataset.interval, 10) || 60000;
    let current = 0;
    let timer = null;

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

    function start() {
      if (timer || reduceMotion) return;
      timer = window.setInterval(() => show(current + 1), interval);
    }

    function stop() {
      if (timer) {
        window.clearInterval(timer);
        timer = null;
      }
    }

    dots.forEach((dot, idx) => {
      dot.addEventListener("click", () => {
        show(idx);
        stop();
        start();
      });
    });

    carrousel.addEventListener("mouseenter", stop);
    carrousel.addEventListener("mouseleave", start);
    carrousel.addEventListener("focusin", stop);
    carrousel.addEventListener("focusout", start);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stop(); else start();
    });

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
