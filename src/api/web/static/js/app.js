document.addEventListener("DOMContentLoaded", () => {
  const formatDate = (value) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(document.documentElement.lang, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  };

  const initializeDeviceWorkspace = () => {
    const workspace = document.querySelector("[data-device-workspace]");
    if (!workspace || workspace.dataset.initialized) {
      return;
    }
    workspace.dataset.initialized = "true";
    const deviceForm = workspace.querySelector("[data-device-form]");
    const deviceList = workspace.querySelector("[data-device-list]");
    const deviceDetail = workspace.querySelector("[data-device-detail]");
    const emptyState = workspace.querySelector("[data-device-empty]");
    const createDialog = workspace.querySelector("[data-device-dialog]");
    const deleteDialog = workspace.querySelector("[data-delete-dialog]");
    const openDialogButton = workspace.querySelector("[data-open-device-dialog]");
    const deleteButton = workspace.querySelector("[data-delete-device]");
    const confirmDeleteButton = workspace.querySelector("[data-confirm-delete]");
    const deleteStatus = workspace.querySelector("[data-delete-status]");
    const announcer = document.querySelector("[data-page-announcer]");
    const publicKeyInput = deviceForm.querySelector("[name='public_key']");
    const privateKeyInput = deviceForm.querySelector("#device-private-key");
    const privateKeyPanel = deviceForm.querySelector("[data-private-key-panel]");
    const status = deviceForm.querySelector("[data-device-status]");
    let activeDeviceButton = null;
    const encodeBytes = (value) => {
      return btoa(String.fromCodePoint(...value));
    };

    const fromBase64Url = (value) => Uint8Array.from(
      atob(value.replaceAll("-", "+").replaceAll("_", "/")),
      (character) => character.codePointAt(0) ?? 0,
    );

    const announce = (message) => {
      if (announcer) announcer.textContent = message;
    };

    const selectDevice = (button, focus = false) => {
      activeDeviceButton = button;
      deviceList.querySelectorAll("[data-device-select]").forEach((item) => {
        const selected = item === button;
        item.setAttribute("aria-pressed", String(selected));
        item.closest("li").classList.toggle("is-selected", selected);
      });
      deviceDetail.hidden = false;
      emptyState.hidden = true;
      deviceDetail.querySelector("[data-device-detail-name]").textContent = button.dataset.name;
      deviceDetail.querySelector("[data-device-detail-id]").textContent = `#${button.dataset.deviceId}`;
      const created = deviceDetail.querySelector("[data-device-detail-created]");
      created.dateTime = button.dataset.createdAt;
      created.textContent = formatDate(button.dataset.createdAt);
      deviceDetail.querySelector("[data-device-detail-key]").textContent = button.dataset.publicKey;
      if (focus) button.focus();
    };

    const makeDeviceItem = (device) => {
      const item = document.createElement("li");
      item.dataset.deviceItem = "";
      const button = document.createElement("button");
      button.className = "device-select";
      button.type = "button";
      button.dataset.deviceSelect = "";
      button.dataset.deviceId = String(device.id);
      button.dataset.name = String(device.name);
      button.dataset.publicKey = String(device.public_key);
      button.dataset.createdAt = String(device.created_at);
      button.setAttribute("aria-pressed", "false");
      const name = document.createElement("span");
      name.textContent = device.name;
      const identifier = document.createElement("small");
      identifier.textContent = `#${device.id}`;
      button.append(name, identifier);
      item.append(button);
      return item;
    };

    openDialogButton.addEventListener("click", () => {
      status.textContent = "";
      createDialog.showModal();
    });
    workspace.querySelector("[data-close-device-dialog]").addEventListener("click", () => {
      createDialog.close();
    });

    deviceList.addEventListener("click", (event) => {
      const button = event.target.closest("[data-device-select]");
      if (button) selectDevice(button);
    });

    workspace.querySelector("[data-cancel-delete]").addEventListener("click", () => {
      deleteDialog.close();
    });

    deleteButton.addEventListener("click", () => {
      if (!activeDeviceButton) return;
      deleteStatus.textContent = "";
      workspace.querySelector("[data-delete-target]").textContent =
        `${activeDeviceButton.dataset.name} (#${activeDeviceButton.dataset.deviceId})`;
      deleteDialog.showModal();
    });

    confirmDeleteButton.addEventListener("click", async () => {
      if (!activeDeviceButton) return;
      const removedButton = activeDeviceButton;
      confirmDeleteButton.disabled = true;
      deleteStatus.textContent = "";
      try {
        const response = await fetch(
          `${workspace.dataset.deviceEndpoint}/${encodeURIComponent(removedButton.dataset.deviceId)}`,
          {
            method: "DELETE",
            credentials: "same-origin",
            headers: {
              "X-CSRFToken": document.querySelector("meta[name='csrf-token']").content,
            },
          },
        );
        if (response.status !== 204) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || workspace.dataset.deleteError);
        }
        const item = removedButton.closest("li");
        const nextButton = item.nextElementSibling?.querySelector("[data-device-select]")
          || item.previousElementSibling?.querySelector("[data-device-select]");
        item.remove();
        deleteDialog.close();
        if (nextButton) {
          selectDevice(nextButton, true);
        } else {
          activeDeviceButton = null;
          deviceList.hidden = true;
          deviceDetail.hidden = true;
          emptyState.hidden = false;
          openDialogButton.focus();
        }
        announce(workspace.dataset.deleteSuccess);
      } catch (error) {
        deleteStatus.textContent = error.message || workspace.dataset.deleteError;
      } finally {
        confirmDeleteButton.disabled = false;
      }
    });

    const firstDevice = deviceList.querySelector('[data-device-select][aria-pressed="true"]')
      || deviceList.querySelector("[data-device-select]");
    if (firstDevice) selectDevice(firstDevice);

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
        const item = makeDeviceItem(payload);
        deviceList.append(item);
        deviceList.hidden = false;
        emptyState.hidden = true;
        createDialog.close();
        selectDevice(item.querySelector("[data-device-select]"), true);
        announce(deviceForm.dataset.successText);
        deviceForm.elements.name.value = "";
      } catch (error) {
        status.textContent = error.message || deviceForm.dataset.createError;
      } finally {
        submit.disabled = false;
      }
    });
  };
  initializeDeviceWorkspace();

  const initializeLeaseWorkspace = () => {
    const workspace = document.querySelector("[data-lease-workspace]");
    if (!workspace || workspace.dataset.initialized) {
      return;
    }
    workspace.dataset.initialized = "true";
    const leaseList = workspace.querySelector("[data-lease-list]");
    const revokedList = workspace.querySelector("[data-revoked-list]");
    const revokedSection = workspace.querySelector("[data-revoked-section]");
    const detail = workspace.querySelector("[data-lease-detail]");
    const emptyState = workspace.querySelector("[data-lease-empty]");
    const createDialog = workspace.querySelector("[data-lease-dialog]");
    const revokeDialog = workspace.querySelector("[data-revoke-dialog]");
    const createForm = workspace.querySelector("[data-lease-form]");
    const createStatus = workspace.querySelector("[data-lease-status]");
    const revokeStatus = workspace.querySelector("[data-revoke-status]");
    const createButton = workspace.querySelector("[data-open-lease-dialog]");
    const confirmRevokeButton = workspace.querySelector("[data-confirm-revoke]");
    const announcer = document.querySelector("[data-page-announcer]");
    const profileSelect = createForm.elements.profile_id;
    let selectedLeaseButton = null;

    const announce = (message) => {
      if (announcer) announcer.textContent = message;
    };

    const updatePolicySummary = () => {
      const option = profileSelect.selectedOptions[0];
      const durations = workspace.querySelector("[data-lease-policy-durations]");
      const networks = workspace.querySelector("[data-lease-policy-networks]");
      if (!option) return;
      durations.textContent = `${workspace.dataset.defaultLabel}: ${option.dataset.defaultDuration} · `
        + `${workspace.dataset.maximumLabel}: ${option.dataset.maximumDuration}`;
      networks.replaceChildren();
      try {
        JSON.parse(option.dataset.networks || "[]").forEach((network) => {
          const item = document.createElement("li");
          const code = document.createElement("code");
          code.textContent = network;
          item.append(code);
          networks.append(item);
        });
      } catch {
        networks.replaceChildren();
      }
    };

    const updateDetails = (button) => {
      selectedLeaseButton = button;
      workspace.querySelectorAll("[data-lease-select]").forEach((item) => {
        const selected = item === button;
        item.setAttribute("aria-pressed", String(selected));
        item.closest("li").classList.toggle("is-selected", selected);
      });
      detail.hidden = false;
      emptyState.hidden = true;
      detail.querySelector("[data-lease-detail-heading]").textContent = button.dataset.profileName;
      detail.querySelector("[data-lease-detail-id]").textContent = `#${button.dataset.leaseId}`;
      detail.querySelector("[data-lease-detail-device]").textContent =
        `${button.dataset.deviceName} (#${button.dataset.deviceId})`;
      detail.querySelector("[data-lease-detail-profile]").textContent =
        `${button.dataset.profileName} (#${button.dataset.profileId})`;
      detail.querySelector("[data-lease-detail-status]").textContent = button.dataset.statusLabel;
      const created = detail.querySelector("[data-lease-detail-created]");
      created.dateTime = button.dataset.createdAt;
      created.textContent = formatDate(button.dataset.createdAt);
      const ended = detail.querySelector("[data-lease-detail-ended]");
      ended.dateTime = button.dataset.endedAt;
      ended.textContent = formatDate(button.dataset.endedAt);
      const revokedDetails = detail.querySelector("[data-lease-revoked-details]");
      const revoked = detail.querySelector("[data-lease-detail-revoked]");
      revokedDetails.hidden = button.dataset.status !== "revoked";
      revoked.dateTime = button.dataset.revokedAt;
      revoked.textContent = formatDate(button.dataset.revokedAt);
      detail.querySelector("[data-open-revoke-dialog]").hidden = button.dataset.status !== "active";
    };

    const makeLeaseItem = (lease, device, profile) => {
      const item = document.createElement("li");
      item.dataset.leaseItem = "";
      const button = document.createElement("button");
      button.className = "lease-select";
      button.type = "button";
      button.dataset.leaseSelect = "";
      button.dataset.leaseId = String(lease.id);
      button.dataset.status = lease.status || "active";
      button.dataset.statusLabel = workspace.dataset.activeLabel;
      button.dataset.deviceId = String(device.id);
      button.dataset.deviceName = device.name;
      button.dataset.profileId = String(profile.id);
      button.dataset.profileName = profile.name;
      button.dataset.createdAt = lease.created_at;
      button.dataset.endedAt = lease.ended_at;
      button.dataset.revokedAt = "";
      button.setAttribute("aria-pressed", "false");
      const name = document.createElement("span");
      name.textContent = `${device.name} · ${profile.name}`;
      const identifier = document.createElement("small");
      identifier.textContent = `#${lease.id} · ${workspace.dataset.activeLabel}`;
      button.append(name, identifier);
      item.append(button);
      return item;
    };

    const selectInitialLease = () => {
      const first = leaseList.querySelector('[data-lease-select][aria-pressed="true"]')
        || leaseList.querySelector("[data-lease-select]")
        || revokedList.querySelector("[data-lease-select]");
      if (first) updateDetails(first);
    };

    createButton.addEventListener("click", () => {
      createStatus.textContent = "";
      createDialog.showModal();
    });
    workspace.querySelector("[data-close-lease-dialog]").addEventListener("click", () => {
      createDialog.close();
    });
    profileSelect.addEventListener("change", updatePolicySummary);
    const handleLeaseSelection = (event) => {
      const button = event.target.closest("[data-lease-select]");
      if (button) updateDetails(button);
    };
    leaseList.addEventListener("click", handleLeaseSelection);
    revokedList.addEventListener("click", handleLeaseSelection);

    workspace.querySelector("[data-open-revoke-dialog]").addEventListener("click", () => {
      if (!selectedLeaseButton) return;
      revokeStatus.textContent = "";
      workspace.querySelector("[data-revoke-target]").textContent =
        `${selectedLeaseButton.dataset.deviceName} · ${selectedLeaseButton.dataset.profileName} `
        + `(#${selectedLeaseButton.dataset.leaseId})`;
      revokeDialog.showModal();
    });
    workspace.querySelector("[data-cancel-revoke]").addEventListener("click", () => {
      revokeDialog.close();
    });

    confirmRevokeButton.addEventListener("click", async () => {
      if (!selectedLeaseButton) return;
      const revokedButton = selectedLeaseButton;
      confirmRevokeButton.disabled = true;
      revokeStatus.textContent = "";
      try {
        const response = await fetch(
          `${workspace.dataset.revokeEndpoint}/${encodeURIComponent(revokedButton.dataset.leaseId)}/revoke`,
          {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "X-CSRFToken": document.querySelector("meta[name='csrf-token']").content,
            },
          },
        );
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || workspace.dataset.revokeError);
        }
        const payload = await response.json();
        const item = revokedButton.closest("li");
        revokedButton.dataset.status = "revoked";
        revokedButton.dataset.statusLabel = workspace.dataset.revokedLabel;
        revokedButton.dataset.revokedAt = payload.revoked_at;
        revokedButton.querySelector("small").textContent =
          `#${revokedButton.dataset.leaseId} · ${workspace.dataset.revokedLabel}`;
        item.remove();
        revokedList.prepend(item);
        revokedSection.hidden = false;
        workspace.querySelector("[data-revoked-count]").textContent =
          String(revokedList.children.length);
        leaseList.hidden = leaseList.children.length === 0;
        emptyState.hidden = !leaseList.hidden;
        revokeDialog.close();
        updateDetails(revokedButton);
        announce(workspace.dataset.revokeSuccess);
      } catch (error) {
        revokeStatus.textContent = error.message || workspace.dataset.revokeError;
      } finally {
        confirmRevokeButton.disabled = false;
      }
    });

    createForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      createStatus.textContent = "";
      const submit = createForm.querySelector("[type='submit']");
      const deviceOption = createForm.elements.device_id.selectedOptions[0];
      const profileOption = profileSelect.selectedOptions[0];
      const body = {
        device_id: Number(createForm.elements.device_id.value),
        profile_id: Number(profileSelect.value),
      };
      const duration = createForm.elements.duration.value.trim();
      if (duration) body.duration = duration;
      submit.disabled = true;
      try {
        const response = await fetch(workspace.dataset.createEndpoint, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector("meta[name='csrf-token']").content,
          },
          body: JSON.stringify(body),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || workspace.dataset.createError);
        }
        const item = makeLeaseItem(
          payload,
          { id: body.device_id, name: deviceOption.textContent.trim().replace(/ \(#\d+\)$/, "") },
          { id: body.profile_id, name: profileOption.textContent.trim().replace(/ \(#\d+\)$/, "") },
        );
        leaseList.prepend(item);
        leaseList.hidden = false;
        emptyState.hidden = true;
        createDialog.close();
        updateDetails(item.querySelector("[data-lease-select]"));
        createForm.elements.duration.value = "";
        announce(workspace.dataset.createSuccess);
      } catch (error) {
        createStatus.textContent = error.message || workspace.dataset.createError;
      } finally {
        submit.disabled = false;
      }
    });

    updatePolicySummary();
    selectInitialLease();
  };
  initializeLeaseWorkspace();

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
    initializeDeviceWorkspace();
    initializeLeaseWorkspace();
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