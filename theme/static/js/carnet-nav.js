/* Navigation manuelle entre billets du carnet (home).
   Les billets sont rendus du plus récent (index 0) au plus ancien ;
   un seul est visible à la fois. La flèche « newer » (‹) remonte vers
   le billet le plus récent, « older » (›) descend vers les plus anciens. */
(function () {
  "use strict";

  function setup(root) {
    const items = Array.from(root.querySelectorAll("[data-carnet-item]"));
    const newer = root.querySelector("[data-carnet-newer]"); // plus récent (‹)
    const older = root.querySelector("[data-carnet-older]"); // plus ancien (›)
    if (items.length < 2 || !newer || !older) return;

    let current = 0;

    function render() {
      items.forEach((item, i) => item.classList.toggle("hidden", i !== current));
      newer.disabled = current <= 0;
      older.disabled = current >= items.length - 1;
    }

    newer.addEventListener("click", () => {
      if (current > 0) { current -= 1; render(); }
    });
    older.addEventListener("click", () => {
      if (current < items.length - 1) { current += 1; render(); }
    });

    render();
  }

  function init() {
    document.querySelectorAll("[data-carnet-nav]").forEach(setup);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
