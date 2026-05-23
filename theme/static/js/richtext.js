/* Mini rich-text editor: bold/italic + Enter handling.
 * Backs every [data-richtext] with a hidden <textarea> kept in sync. */
(function () {
    "use strict";

    function syncToInput(editor, input) {
        input.value = editor.innerHTML;
    }

    function setupKeyboardShortcuts(editor, sync) {
        editor.addEventListener("keydown", function (e) {
            // Ctrl/Cmd + B / I as fallback (browsers usually map these natively)
            if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
                if (e.key === "b" || e.key === "B") { document.execCommand("bold"); e.preventDefault(); sync(); }
                else if (e.key === "i" || e.key === "I") { document.execCommand("italic"); e.preventDefault(); sync(); }
            }
        });
    }

    function init(root) {
        var editor = root.querySelector("[data-richtext-editor]");
        var input = root.querySelector("[data-richtext-input]");
        var toolbar = root.querySelector(".richtext__toolbar");
        if (!editor || !input || !toolbar) return;

        var mode = root.dataset.mode || "block";
        var sync = function () { syncToInput(editor, input); };

        editor.addEventListener("input", sync);
        editor.addEventListener("blur", sync);

        toolbar.addEventListener("mousedown", function (e) {
            // mousedown (not click) so the editor doesn't lose focus before execCommand
            var btn = e.target.closest("button[data-cmd]");
            if (!btn) return;
            e.preventDefault();
            document.execCommand(btn.dataset.cmd);
            sync();
        });

        setupKeyboardShortcuts(editor, sync);

        if (mode === "inline") {
            // Single-paragraph: Enter inserts <br>, Shift+Enter does the same.
            editor.addEventListener("keydown", function (e) {
                if (e.key === "Enter") {
                    e.preventDefault();
                    document.execCommand("insertLineBreak");
                    sync();
                }
            });
        }

        // Belt-and-braces: sync once more right before the form submits.
        var form = root.closest("form");
        if (form) form.addEventListener("submit", sync);
    }

    function initAll() {
        // Tell browsers (once) to use <p> on Enter instead of <div>.
        try { document.execCommand("defaultParagraphSeparator", false, "p"); } catch (e) { /* IE/old */ }
        document.querySelectorAll("[data-richtext]").forEach(init);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
