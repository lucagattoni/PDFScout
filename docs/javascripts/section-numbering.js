// Number the page title and its sections on the docs site, deriving the page's
// number (e.g. "1.1") from its entry in the left navigation. So the H1 becomes
// "1.1 Quickstart" and its sections become "1.1.1 …", "1.1.2 …".
//
// Done in JS (not in the Markdown) so the source files, their heading anchors,
// and the GitHub rendering stay clean. Uses Material's `document$` so it re-runs
// on instant navigation. Idempotent via a data-flag guard.
//
// Adapted from the same mechanism in the companion Claude-Loops docs site
// (lucagattoni/Claude-Loops, docs/javascripts/section-numbering.js).
document$.subscribe(function () {
  var content = document.querySelector(".md-content");
  if (!content) return;

  // The current page's nav link text starts with its number, e.g. "1.1 Quickstart".
  var activeLink = document.querySelector(".md-nav__link--active");
  var match = activeLink && activeLink.textContent.trim().match(/^(\d+(?:\.\d+)*)\s/);
  var pageNum = match ? match[1] : null;
  if (!pageNum) return; // Home and other unnumbered pages: leave untouched.

  function prefix(el, num) {
    if (!el || el.dataset.numbered) return;
    el.dataset.numbered = "1";
    el.insertBefore(document.createTextNode(num + " "), el.firstChild);
    // Keep the right-hand table of contents in sync. With instant navigation the
    // TOC hrefs are absolute (".../page/#slug"), so match on the "#slug" suffix.
    if (el.id) {
      var idEsc = window.CSS && CSS.escape ? CSS.escape(el.id) : el.id;
      document
        .querySelectorAll('a.md-nav__link[href$="#' + idEsc + '"]')
        .forEach(function (toc) {
          if (toc.dataset.numbered) return;
          toc.dataset.numbered = "1";
          toc.insertBefore(document.createTextNode(num + " "), toc.firstChild);
        });
    }
  }

  // Page title (the "chapter"/"section" title): "1.1".
  prefix(content.querySelector("h1"), pageNum);

  // Sections and subsections: "1.1.1", "1.1.1.1".
  var h2 = 0, h3 = 0;
  content.querySelectorAll("h2, h3").forEach(function (h) {
    if (h.dataset.numbered) return;
    var num;
    if (h.tagName === "H2") {
      h2 += 1; h3 = 0;
      num = pageNum + "." + h2;
    } else {
      h3 += 1;
      num = pageNum + "." + h2 + "." + h3;
    }
    prefix(h, num);
  });
});
