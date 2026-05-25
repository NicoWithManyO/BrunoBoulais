/* Visionneuse plein écran pour la galerie : ouverture au clic sur une vignette,
   navigation prev/next (boutons, flèches clavier, swipe tactile), fermeture
   au clic sur le fond / bouton × / touche Échap. Hijacke les liens
   [data-lightbox-trigger] et laisse le href fonctionnel si JS indisponible. */
(function () {
  "use strict";

  function init() {
    const triggers = Array.from(document.querySelectorAll("[data-lightbox-trigger]"));
    if (!triggers.length) return;

    const modal = document.querySelector("[data-lightbox-modal]");
    if (!modal) return;

    const imgEl = modal.querySelector("[data-lightbox-img]");
    const captionEl = modal.querySelector("[data-lightbox-caption]");
    const counterEl = modal.querySelector("[data-lightbox-counter]");
    const closeBtn = modal.querySelector("[data-lightbox-close]");
    const prevBtn = modal.querySelector("[data-lightbox-prev]");
    const nextBtn = modal.querySelector("[data-lightbox-next]");

    const items = triggers.map((t) => ({
      src: t.dataset.lightboxSrc || t.getAttribute("href") || "",
      caption: t.dataset.lightboxCaption || "",
      alt: t.dataset.lightboxAlt || "",
    }));

    let currentIndex = 0;
    let previouslyFocused = null;

    function show(idx) {
      currentIndex = ((idx % items.length) + items.length) % items.length;
      const item = items[currentIndex];
      imgEl.src = item.src;
      imgEl.alt = item.alt;
      captionEl.textContent = item.caption;
      captionEl.hidden = !item.caption;
      if (counterEl) counterEl.textContent = items.length > 1
        ? (currentIndex + 1) + " / " + items.length
        : "";
      const multiple = items.length > 1;
      prevBtn.hidden = !multiple;
      nextBtn.hidden = !multiple;
    }

    function open(idx) {
      previouslyFocused = document.activeElement;
      show(idx);
      modal.hidden = false;
      document.body.style.overflow = "hidden";
      closeBtn.focus();
      document.addEventListener("keydown", onKey);
    }

    function close() {
      modal.hidden = true;
      imgEl.removeAttribute("src");
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
      if (previouslyFocused && typeof previouslyFocused.focus === "function") {
        previouslyFocused.focus();
      }
    }

    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); close(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); show(currentIndex - 1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); show(currentIndex + 1); }
    }

    triggers.forEach((t, i) => {
      t.addEventListener("click", (e) => {
        // Laisse passer si modificateur (ctrl/cmd/middle-click) → ouverture dans nouvel onglet
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
        e.preventDefault();
        open(i);
      });
    });

    closeBtn.addEventListener("click", close);
    prevBtn.addEventListener("click", () => show(currentIndex - 1));
    nextBtn.addEventListener("click", () => show(currentIndex + 1));

    modal.addEventListener("click", (e) => {
      if (e.target === modal) close();
    });

    // Swipe tactile
    let touchStartX = 0;
    let touchStartY = 0;
    modal.addEventListener("touchstart", (e) => {
      const t = e.changedTouches[0];
      touchStartX = t.screenX;
      touchStartY = t.screenY;
    }, { passive: true });
    modal.addEventListener("touchend", (e) => {
      const t = e.changedTouches[0];
      const dx = t.screenX - touchStartX;
      const dy = t.screenY - touchStartY;
      // Geste horizontal franc uniquement
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
        if (dx > 0) show(currentIndex - 1);
        else show(currentIndex + 1);
      }
    }, { passive: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
