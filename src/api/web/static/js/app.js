document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector("[data-menu-toggle]");
  const menu = document.getElementById("main-menu");

  if (!toggle || !menu) {
    return;
  }

  const closeMenu = () => {
    toggle.setAttribute("aria-expanded", "false");
    menu.hidden = true;
  };

  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!expanded));
    menu.hidden = expanded;
  });

  menu.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) {
      closeMenu();
      toggle.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (!menu.hidden && !menu.contains(event.target) && !toggle.contains(event.target)) {
      closeMenu();
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target?.id === "main-content") {
      const heading = event.detail.target.querySelector("h1");
      event.detail.target.focus();
      const announcer = document.querySelector("[data-page-announcer]");
      if (announcer && heading) {
        announcer.textContent = heading.textContent;
        document.title = `${heading.textContent} · TTL-LAMa`;
      }
    }
  });
});