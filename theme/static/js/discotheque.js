/* Discothèque : au clic sur une card, charge la vidéo YouTube dans
   le mini-lecteur sticky en haut de page et met à jour le libellé
   « chanson courante » à droite du lecteur. Si l'utilisateur a
   scrollé au-delà du lecteur, on remonte en douceur. */
(function () {
  "use strict";

  function init() {
    var player = document.getElementById("yt-player");
    if (!player) return;
    var nowLabel = document.getElementById("yt-now");
    var noteLabel = document.getElementById("yt-note");
    var cards = document.querySelectorAll(".card-chanson[data-yt-id]");
    if (!cards.length) return;

    cards.forEach(function (card) {
      card.addEventListener("click", function () {
        var id = card.dataset.ytId;
        if (!id) return;

        var title = card.dataset.ytTitle || "Chanson";
        player.setAttribute("title", "Lecteur YouTube — " + title);
        player.src =
          "https://www.youtube-nocookie.com/embed/" +
          encodeURIComponent(id) +
          "?autoplay=1&rel=0";

        if (nowLabel) nowLabel.textContent = title;

        if (noteLabel) {
          var note = (card.dataset.ytNote || "").trim();
          if (note) {
            noteLabel.textContent = note;
            noteLabel.hidden = false;
          } else {
            noteLabel.textContent = "";
            noteLabel.hidden = true;
          }
        }

        // Si l'utilisateur a scrollé sous le lecteur, on remonte.
        var rect = player.getBoundingClientRect();
        if (rect.top < 0) {
          window.scrollTo({ top: 0, behavior: "smooth" });
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
