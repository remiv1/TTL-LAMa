document.addEventListener("DOMContentLoaded", () => {
  const initializeDeviceForm = () => {
    const deviceForm = document.querySelector("[data-device-form]");
    if (!deviceForm || deviceForm.dataset.initialized) {
      return;
    }
    deviceForm.dataset.initialized = "true";
    const publicKeyInput = deviceForm.querySelector("[name='public_key']");
    const privateKeyInput = deviceForm.querySelector("#device-private-key");
    const privateKeyPanel = deviceForm.querySelector("[data-private-key-panel]");
    const status = deviceForm.querySelector("[data-device-status]");
    const encodeBytes = (value) => {
      return btoa(String.fromCodePoint(...value));
    };

    const fromBase64Url = (value) => Uint8Array.from(
      atob(value.replaceAll("-", "+").replaceAll("_", "/")),
      (character) => character.codePointAt(0) ?? 0,
    );

    deviceForm.querySelector("[data-generate-keys]").addEventListener("click", async () => {
      try {
        const keyPair = await crypto.subtle.generateKey(
          { name: "X25519" },
          true,
          ["deriveBits"],
        );
        const [publicJwk, privateJwk] = await Promise.all([
          crypto.subtle.exportKey("jwk", keyPair.publicKey),
          crypto.subtle.exportKey("jwk", keyPair.privateKey),
        ]);
        publicKeyInput.value = encodeBytes(fromBase64Url(publicJwk.x));
        privateKeyInput.value = encodeBytes(fromBase64Url(privateJwk.d));
        privateKeyPanel.hidden = false;
        status.textContent = "";
      } catch {
        status.textContent = deviceForm.dataset.keygenError;
      }
    });

    deviceForm.querySelector("[data-copy-private-key]").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(privateKeyInput.value);
        status.textContent = deviceForm.dataset.copiedText;
      } catch {
        privateKeyInput.select();
        status.textContent = deviceForm.dataset.copyError;
      }
    });

    deviceForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      status.textContent = "";
      const submit = deviceForm.querySelector("[type='submit']");
      submit.disabled = true;
      try {
        const response = await fetch(deviceForm.dataset.endpoint, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector("meta[name='csrf-token']").content,
          },
          body: JSON.stringify({
            name: deviceForm.elements.name.value,
            public_key: publicKeyInput.value,
          }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || deviceForm.dataset.createError);
        }
        const item = document.createElement("li");
        const name = document.createElement("span");
        const identifier = document.createElement("small");
        name.textContent = payload.name;
        identifier.textContent = `#${payload.id}`;
        item.append(name, identifier);
        const list = deviceForm.parentElement.querySelector("[data-device-list]");
        list.append(item);
        list.hidden = false;
        const empty = deviceForm.parentElement.querySelector("[data-device-empty]");
        if (empty) empty.hidden = true;
        status.textContent = deviceForm.dataset.successText;
        deviceForm.elements.name.value = "";
      } catch (error) {
        status.textContent = error.message || deviceForm.dataset.createError;
      } finally {
        submit.disabled = false;
      }
    });
  };
  initializeDeviceForm();

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
    initializeDeviceForm();
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