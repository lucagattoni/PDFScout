// Mark external links: open them in a new tab and flag them for the arrow icon
// (see stylesheets/external-links.css). Runs on every Material "instant navigation"
// page swap via document$, not just the first load — a plain DOMContentLoaded
// listener would miss every page after the first.
//
// Material's instant-loading rewrites every href (including in-page "#anchor"
// permalinks) to a fully-qualified absolute URL before this runs, so relative-
// vs-absolute syntax can't be used to detect "internal". Instead: resolve the
// href and compare it against this site's own deployed base URL. A plain
// same-origin check is not enough either — GitHub Pages project sites share one
// hostname (github.io), so the companion Claude-Loops docs look "same-origin"
// but are a different project and must still be flagged external.
document$.subscribe(function () {
  var SITE_BASE = "https://lucagattoni.github.io/Claude-Warp/";
  var isProdOrigin = window.location.origin === "https://lucagattoni.github.io";

  document.querySelectorAll(".md-content a[href]").forEach(function (a) {
    var href = a.getAttribute("href");
    if (!href) return;

    var resolved;
    try {
      resolved = new URL(href, window.location.href).href;
    } catch (e) {
      return;
    }

    var isInternal =
      resolved.indexOf(SITE_BASE) === 0 ||
      (!isProdOrigin && new URL(resolved).origin === window.location.origin);

    if (isInternal) return;

    a.setAttribute("target", "_blank");
    a.setAttribute("rel", "noopener noreferrer");
    a.classList.add("external-link");
  });
});
