// Site menu on narrow screens: the button opens and closes the nav. Without
// JavaScript the header never gets the "js" class, so the nav simply stays open.
(function () {
  var header = document.querySelector(".site-header");
  var button = header && header.querySelector(".nav-toggle");
  if (!button) return;
  header.classList.add("js");

  function setOpen(open) {
    header.classList.toggle("open", open);
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  button.addEventListener("click", function () {
    setOpen(!header.classList.contains("open"));
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && header.classList.contains("open")) {
      setOpen(false);
      button.focus();
    }
  });
  document.addEventListener("click", function (e) {
    if (!header.contains(e.target)) setOpen(false);
  });
  // Jumping to an anchor on the same page closes the menu too
  header.querySelectorAll(".site-nav a").forEach(function (a) {
    a.addEventListener("click", function () { setOpen(false); });
  });
})();
