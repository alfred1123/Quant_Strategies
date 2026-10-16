// Offline Mermaid initialisation for MkDocs Material.
// Mermaid is loaded locally (docs/javascripts/mermaid.min.js) so diagrams
// render without any CDN / internet access.
(function () {
  function currentTheme() {
    var scheme = document.body.getAttribute("data-md-color-scheme");
    return scheme === "slate" ? "dark" : "default";
  }

  function render() {
    if (typeof mermaid === "undefined") return;
    var blocks = document.querySelectorAll("pre.mermaid, .mermaid");
    blocks.forEach(function (el) {
      // superfences wraps the code in <pre class="mermaid"><code>…</code></pre>;
      // flatten it to the raw graph text Mermaid expects.
      var code = el.querySelector("code");
      if (code) {
        el.textContent = code.textContent;
      }
      el.removeAttribute("data-processed");
    });
    mermaid.initialize({ startOnLoad: false, theme: currentTheme() });
    mermaid.run({ querySelector: "pre.mermaid, .mermaid" });
  }

  // Initial load.
  document.addEventListener("DOMContentLoaded", render);
  // Material instant navigation (SPA-style page swaps).
  if (window.document$) {
    window.document$.subscribe(render);
  }
})();
