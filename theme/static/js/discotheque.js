/* Discothèque : au clic sur une card, charge soit la vidéo YouTube (chanson)
   soit le fichier audio (enregistrement téléphonique) dans le mini-lecteur
   sticky en haut de page, et met à jour le libellé « en cours » à droite.
   Si l'utilisateur a scrollé au-delà du lecteur, on remonte en douceur.
   Les pills filtrent les cartes par type. */
(function () {
  "use strict";

  function init() {
    var player = document.getElementById("yt-player");
    if (!player) return;
    var bar = document.querySelector(".yt-bar");
    var nowLabel = document.getElementById("yt-now");
    var noteLabel = document.getElementById("yt-note");
    var audioStage = document.getElementById("audio-stage");
    var audioCover = document.getElementById("audio-cover");
    var audioPlayer = document.getElementById("audio-player");
    var cards = document.querySelectorAll(".card-chanson[data-type]");

    function setMeta(card) {
      var title = (card.dataset.ytTitle || "").trim();
      if (nowLabel) nowLabel.textContent = title;
      if (noteLabel) {
        var note = (card.dataset.ytNote || "").trim();
        noteLabel.textContent = note;
        noteLabel.hidden = !note;
      }
      return title;
    }

    function playYoutube(card, title) {
      // Coupe l'audio en cours et cache la scène audio.
      if (audioPlayer) {
        audioPlayer.pause();
        audioPlayer.removeAttribute("src");
        audioPlayer.hidden = true;
      }
      if (audioStage) audioStage.hidden = true;

      player.setAttribute("title", title ? "Lecteur YouTube — " + title : "Lecteur YouTube");
      player.src =
        "https://www.youtube-nocookie.com/embed/" +
        encodeURIComponent(card.dataset.ytId) +
        "?autoplay=1&rel=0";
    }

    function playAudio(card) {
      var src = card.dataset.audioSrc;
      if (!src) return;
      // Coupe la vidéo YouTube : removeAttribute ne décharge pas une iframe
      // déjà chargée (le player continue de jouer), il faut naviguer ailleurs.
      player.src = "about:blank";

      if (audioCover) {
        var cover = card.dataset.cover;
        if (cover) {
          audioCover.src = cover;
          audioCover.hidden = false;
        } else {
          audioCover.removeAttribute("src");
          audioCover.hidden = true;
        }
      }
      if (audioStage) audioStage.hidden = false;
      if (audioPlayer) {
        audioPlayer.src = src;
        audioPlayer.hidden = false;
        audioPlayer.play().catch(function () {});
      }
    }

    cards.forEach(function (card) {
      card.addEventListener("click", function () {
        var title = setMeta(card);

        if (card.dataset.type === "enregistrement") {
          playAudio(card);
        } else {
          if (!card.dataset.ytId) return;
          playYoutube(card, title);
        }

        if (bar) bar.classList.add("is-playing");

        // Si l'utilisateur a scrollé sous le lecteur, on remonte.
        var rect = player.getBoundingClientRect();
        if (rect.top < 0) {
          window.scrollTo({ top: 0, behavior: "smooth" });
        }
      });
    });

    initPills();
  }

  function initPills() {
    var pills = document.querySelectorAll(".disco-pills .pill");
    if (!pills.length) return;
    var items = document.querySelectorAll(".cards-discotheque > li[data-type]");

    pills.forEach(function (pill) {
      pill.addEventListener("click", function () {
        pills.forEach(function (p) {
          p.classList.toggle("is-active", p === pill);
        });
        var filter = pill.dataset.filter;
        items.forEach(function (li) {
          li.hidden = filter !== "all" && li.dataset.type !== filter;
        });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
