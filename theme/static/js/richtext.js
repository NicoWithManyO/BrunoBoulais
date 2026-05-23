/* Mini rich-text editor: bold/italic + Enter handling.
 * Backs every [data-richtext] with a hidden <textarea> kept in sync. */
(function () {
    "use strict";

    function init(root) {
        var editor = root.querySelector("[data-richtext-editor]");
        var input = root.querySelector("[data-richtext-input]");
        var toolbar = root.querySelector(".richtext__toolbar");
        if (!editor || !input || !toolbar) return;

        var inline = root.dataset.mode === "inline";
        var sync = function () { input.value = editor.innerHTML; };

        editor.addEventListener("input", sync);
        editor.addEventListener("blur", sync);

        editor.addEventListener("keydown", function (e) {
            if (inline && e.key === "Enter") {
                e.preventDefault();
                document.execCommand("insertLineBreak");
                sync();
            }
        });

        toolbar.addEventListener("mousedown", function (e) {
            // mousedown (not click) so the editor doesn't lose focus before execCommand.
            var btn = e.target.closest("button[data-cmd]");
            if (!btn) return;
            e.preventDefault();
            editor.focus();
            document.execCommand(btn.dataset.cmd);
            sync();
        });

        // Catch Enter-to-submit and similar paths where blur never fires.
        var form = root.closest("form");
        if (form) form.addEventListener("submit", sync);
    }

    function initAll() {
        try { document.execCommand("defaultParagraphSeparator", false, "p"); } catch (e) { /* old browsers */ }
        document.querySelectorAll("[data-richtext]").forEach(init);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
