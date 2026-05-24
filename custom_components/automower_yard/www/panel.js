class RobotMowerYardPanel extends HTMLElement {
  connectedCallback() {
    this._onMessage = (event) => this.handleFrameMessage(event);
    window.addEventListener("message", this._onMessage);
    this.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100%;
          background: #f5f7f6;
          color: #111111;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        :host * {
          color: inherit;
        }
        main {
          max-width: 1040px;
          margin: 0 auto;
          padding: 28px;
        }
        header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 22px;
        }
        h1 {
          margin: 0;
          color: #000000;
          font-size: 28px;
          font-weight: 640;
          letter-spacing: 0;
        }
        button {
          height: 36px;
          border: 1px solid #b9c7c0;
          border-radius: 6px;
          background: #ffffff;
          color: #111111;
          padding: 0 14px;
          cursor: pointer;
        }
        .yard {
          background: #ffffff;
          border: 1px solid #d6ded8;
          border-radius: 8px;
          padding: 18px;
          margin-bottom: 16px;
          color: #111111;
        }
        .yard h2 {
          margin: 0 0 8px;
          color: #111111;
          font-size: 20px;
          font-weight: 620;
        }
        .meta {
          color: #26332d;
          margin-bottom: 14px;
        }
        .actions {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-bottom: 14px;
        }
        a.action {
          display: inline-flex;
          align-items: center;
          height: 34px;
          border: 1px solid #b9c7c0;
          border-radius: 6px;
          background: #ffffff;
          color: #111111;
          padding: 0 12px;
          text-decoration: none;
        }
        .setup-note {
          display: none;
          color: #111111;
          background: #eef5f1;
          border: 1px solid #c9d4ce;
          border-radius: 8px;
          padding: 12px;
          margin-bottom: 14px;
          line-height: 1.45;
        }
        .setup-note.open {
          display: block;
        }
        iframe.zone-editor {
          width: 100%;
          height: min(760px, 78vh);
          border: 1px solid #c9d4ce;
          border-radius: 8px;
          background: #ffffff;
        }
        .providers {
          border-top: 1px solid #e2e8e4;
          margin: 4px 0 16px;
          padding-top: 10px;
        }
        .provider-row {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          align-items: center;
          gap: 10px;
          padding: 8px 0;
        }
        .provider-name {
          color: #111111;
          font-weight: 600;
        }
        .provider-type {
          color: #26332d;
          font-size: 13px;
          margin-top: 2px;
        }
        .provider-settings {
          display: none;
          grid-column: 1 / -1;
          background: #f8faf8;
          border: 1px solid #d6ded8;
          border-radius: 8px;
          padding: 12px;
        }
        .provider-settings.open {
          display: block;
        }
        .provider-settings form {
          display: grid;
          grid-template-columns: repeat(4, minmax(150px, 1fr)) auto;
          align-items: end;
          gap: 10px;
        }
        label {
          display: grid;
          gap: 5px;
          color: #26332d;
          font-size: 12px;
          text-transform: uppercase;
        }
        input {
          height: 34px;
          border: 1px solid #b9c7c0;
          border-radius: 6px;
          background: #ffffff;
          box-sizing: border-box;
          color: #111111;
          caret-color: #111111;
          font-size: 14px;
          padding: 0 10px;
          -webkit-text-fill-color: #111111;
        }
        input:focus {
          border-color: #6f8579;
          outline: 2px solid #dbe7e1;
          outline-offset: 1px;
        }
        .provider-status {
          color: #26332d;
          font-size: 13px;
          margin-top: 8px;
          min-height: 18px;
        }
        .status-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 10px;
          margin: 0 0 16px;
        }
        .mower-card {
          border: 1px solid #d6ded8;
          border-radius: 8px;
          background: #fbfcfb;
          padding: 12px;
        }
        .mower-card-header {
          display: flex;
          justify-content: space-between;
          gap: 10px;
          align-items: center;
          margin-bottom: 10px;
        }
        .mower-card-title {
          color: #111111;
          font-size: 15px;
          font-weight: 700;
        }
        .status-pill {
          border-radius: 999px;
          border: 1px solid #bfd0c6;
          background: #eef5f1;
          color: #111111;
          font-size: 12px;
          padding: 3px 8px;
          white-space: nowrap;
        }
        .status-pill.problem {
          border-color: #e0aaa5;
          background: #fff1ef;
          color: #7a1d16;
        }
        .mower-facts {
          display: grid;
          grid-template-columns: max-content minmax(0, 1fr);
          gap: 6px 10px;
          font-size: 13px;
        }
        .mower-facts dt {
          color: #26332d;
          font-weight: 600;
        }
        .mower-facts dd {
          color: #111111;
          margin: 0;
          overflow-wrap: anywhere;
        }
        .map-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 14px;
          margin-top: 16px;
        }
        .map-panel {
          border: 1px solid #d6ded8;
          border-radius: 8px;
          overflow: hidden;
          background: #ffffff;
        }
        .map-panel-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          border-bottom: 1px solid #e2e8e4;
          padding: 8px 10px 8px 12px;
        }
        .map-panel h3 {
          margin: 0;
          color: #111111;
          font-size: 14px;
          font-weight: 700;
        }
        .map-expand {
          height: 30px;
          padding: 0 10px;
          font-size: 13px;
        }
        .map-panel iframe {
          display: block;
          width: 100%;
          height: clamp(260px, 48vw, 480px);
          border: 0;
          aspect-ratio: 9 / 5;
          background: #edf3ef;
        }
        .map-overlay {
          position: fixed;
          inset: 0;
          z-index: 2147483000;
          display: grid;
          grid-template-rows: auto minmax(0, 1fr);
          background: #ffffff;
        }
        .map-overlay[hidden] {
          display: none;
        }
        .map-overlay-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          min-height: 50px;
          border-bottom: 1px solid #d6ded8;
          background: #ffffff;
          padding: max(8px, env(safe-area-inset-top)) max(10px, env(safe-area-inset-right)) 8px max(12px, env(safe-area-inset-left));
          box-sizing: border-box;
        }
        .map-overlay-title {
          color: #111111;
          font-size: 16px;
          font-weight: 700;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .map-overlay iframe {
          width: 100%;
          height: 100%;
          border: 0;
          background: #edf3ef;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          background: #ffffff;
          color: #111111;
        }
        th, td {
          border-top: 1px solid #e2e8e4;
          padding: 10px 8px;
          text-align: left;
        }
        th {
          color: #26332d;
          font-size: 12px;
          text-transform: uppercase;
        }
        td {
          color: #111111;
        }
        .mower-name {
          color: #111111;
          font-weight: 600;
        }
        .mower-provider,
        .mower-state,
        .mower-battery,
        .mower-problem {
          color: #111111;
        }
        .empty {
          color: #26332d;
          background: #ffffff;
          border: 1px solid #d6ded8;
          border-radius: 8px;
          padding: 18px;
        }
        .note {
          color: #26332d;
          font-size: 13px;
          margin: -12px 0 18px;
        }
        @media (max-width: 720px) {
          main {
            padding: 18px;
          }
          .provider-row,
          .provider-settings form {
            grid-template-columns: 1fr;
          }
          .map-grid {
            grid-template-columns: 1fr;
          }
        }
      </style>
      <main>
        <header>
          <h1>Robot Mower Yard</h1>
          <button id="refresh">Refresh</button>
        </header>
        <div id="content" class="empty">Loading...</div>
      </main>
      <div class="map-overlay" id="map-overlay" hidden>
        <div class="map-overlay-header">
          <div class="map-overlay-title" id="map-overlay-title"></div>
          <button type="button" id="map-overlay-close">Close</button>
        </div>
        <iframe id="map-overlay-frame" title="Expanded mower map"></iframe>
      </div>
    `;
    this.querySelector("#refresh").addEventListener("click", () => this.load());
    this.querySelector("#map-overlay-close").addEventListener("click", () => this.closeMapOverlay());
    this.load();
  }

  disconnectedCallback() {
    if (this._onMessage) {
      window.removeEventListener("message", this._onMessage);
      this._onMessage = null;
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (this.isConnected && !this._loaded) {
      this._loaded = true;
      this.load();
    }
  }

  async load() {
    const content = this.querySelector("#content");
    if (!this._hass) {
      return;
    }
    let data;
    try {
      data = await this._hass.callApi("GET", "robot_mower_yard/overview");
    } catch (error) {
      content.className = "empty";
      content.textContent = `Unable to load yard overview: ${error.message || error}`;
      return;
    }
    if (!data.yards?.length) {
      content.className = "empty";
      content.textContent = "No yards configured.";
      return;
    }
    content.className = "";
    content.innerHTML = data.yards.map((yard) => `
      <section class="yard">
        <h2>${escapeHtml(yard.title)}</h2>
        <div class="meta">
          ${yard.mower_count} mowers · ${yard.providers.length || 0} providers
        </div>
        <div class="actions">
          <button class="action" data-zone-toggle="${escapeHtml(yard.entry_id)}">
            Configure zones
          </button>
        </div>
        <div class="setup-note" id="zones-${escapeHtml(yard.entry_id)}">
          <iframe
            class="zone-editor"
            title="${escapeHtml(yard.title)} zone editor"
            data-src="/robot_mower_yard_static/zone_editor.html?ha=1&yard_entry_id=${encodeURIComponent(yard.entry_id)}"
          ></iframe>
        </div>
        ${renderProviders(yard.providers)}
        ${renderMowerStatus(yard.mowers)}
        ${renderMaps(yard)}
      </section>
    `).join("");
    content.querySelectorAll("button[data-zone-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const note = content.querySelector(`#zones-${CSS.escape(button.dataset.zoneToggle)}`);
        const iframe = note?.querySelector("iframe[data-src]");
        if (iframe && !iframe.src) {
          iframe.src = iframe.dataset.src;
        }
        note?.classList.toggle("open");
      });
    });
    content.querySelectorAll(".setup-note").forEach((note) => {
      note.addEventListener("click", (event) => event.stopPropagation());
      note.addEventListener("pointerdown", (event) => event.stopPropagation());
    });
    content.querySelectorAll("button[data-provider-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const panel = content.querySelector(`#provider-${CSS.escape(button.dataset.providerToggle)}`);
        panel?.classList.toggle("open");
      });
    });
    content.querySelectorAll("form[data-provider-form]").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        await this.saveProviderSettings(form);
      });
    });
    content.querySelectorAll("button[data-map-expand]").forEach((button) => {
      button.addEventListener("click", () => this.openMapOverlay(button));
    });
  }

  openMapOverlay(button) {
    const overlay = this.querySelector("#map-overlay");
    const frame = this.querySelector("#map-overlay-frame");
    const title = this.querySelector("#map-overlay-title");
    const src = button.dataset.mapSrc;
    if (!overlay || !frame || !title || !src) {
      return;
    }
    const url = new URL(src, window.location.origin);
    url.searchParams.set("expanded", "1");
    url.searchParams.set("_", String(Date.now()));
    title.textContent = button.dataset.mapTitle || "Mower map";
    frame.src = url.pathname + url.search;
    overlay.hidden = false;
  }

  closeMapOverlay() {
    const overlay = this.querySelector("#map-overlay");
    const frame = this.querySelector("#map-overlay-frame");
    if (frame) {
      frame.removeAttribute("src");
    }
    if (overlay) {
      overlay.hidden = true;
    }
  }

  async saveProviderSettings(form) {
    const status = form.parentElement.querySelector(".provider-status");
    status.textContent = "Saving...";
    const providerEntryId = form.dataset.providerForm;
    const formData = new FormData(form);
    try {
      await this._hass.callApi("POST", "robot_mower_yard/provider", {
        provider_entry_id: providerEntryId,
        base_station_latitude: formData.get("base_station_latitude") || null,
        base_station_longitude: formData.get("base_station_longitude") || null,
        position_offset_north_m: formData.get("position_offset_north_m") || null,
        position_offset_east_m: formData.get("position_offset_east_m") || null,
      });
      status.textContent = "Saved.";
      await this.load();
      const panel = this.querySelector(`#provider-${CSS.escape(providerEntryId)}`);
      panel?.classList.add("open");
    } catch (error) {
      status.textContent = `Save failed: ${error.message || error}`;
    }
  }

  async handleFrameMessage(event) {
    const message = event.data || {};
    if (message.type !== "robot-mower-yard-state-request" || !message.requestId) {
      return;
    }
    if (!this._hass || !event.source) {
      return;
    }
    try {
      const query = message.yardEntryId
        ? `?yard_entry_id=${encodeURIComponent(message.yardEntryId)}`
        : "";
      const payload = await this._hass.callApi("GET", `robot_mower_yard/zones${query}`);
      event.source.postMessage(
        {
          type: "robot-mower-yard-state-response",
          requestId: message.requestId,
          ok: true,
          payload,
        },
        event.origin,
      );
    } catch (error) {
      event.source.postMessage(
        {
          type: "robot-mower-yard-state-response",
          requestId: message.requestId,
          ok: false,
          error: error.message || String(error),
        },
        event.origin,
      );
    }
  }

}

function renderProviders(providers) {
  if (!providers.length) {
    return "";
  }
  return `
    <div class="providers">
      ${providers.map((provider) => `
        <div class="provider-row">
          <div>
            <div class="provider-name">${escapeHtml(provider.title)}</div>
            <div class="provider-type">${escapeHtml(provider.provider_type)}</div>
          </div>
          ${provider.provider_type === "navimow" ? `
            <button type="button" data-provider-toggle="${escapeHtml(provider.entry_id)}">
              Provider settings
            </button>
            <div class="provider-settings" id="provider-${escapeHtml(provider.entry_id)}">
              <form data-provider-form="${escapeHtml(provider.entry_id)}">
                <label>
                  Base station latitude
                  <input
                    name="base_station_latitude"
                    inputmode="decimal"
                    value="${escapeHtml(provider.options?.base_station_latitude ?? "")}"
                  >
                </label>
                <label>
                  Base station longitude
                  <input
                    name="base_station_longitude"
                    inputmode="decimal"
                    value="${escapeHtml(provider.options?.base_station_longitude ?? "")}"
                  >
                </label>
                <label>
                  Offset north (m)
                  <input
                    name="position_offset_north_m"
                    inputmode="decimal"
                    value="${escapeHtml(provider.options?.position_offset_north_m ?? "")}"
                  >
                </label>
                <label>
                  Offset east (m)
                  <input
                    name="position_offset_east_m"
                    inputmode="decimal"
                    value="${escapeHtml(provider.options?.position_offset_east_m ?? "")}"
                  >
                </label>
                <button type="submit">Save</button>
              </form>
              <div class="provider-status"></div>
            </div>
          ` : ""}
        </div>
      `).join("")}
    </div>
  `;
}

function renderMowers(mowers) {
  if (!mowers.length) {
    return `<div class="empty">No mowers attached to this yard.</div>`;
  }
  return `
    <table>
      <thead>
        <tr>
          <th>Mower</th>
          <th>Provider</th>
          <th>State</th>
          <th>Battery</th>
          <th>Problem</th>
        </tr>
      </thead>
      <tbody>
        ${mowers.map((mower) => `
          <tr>
            <td class="mower-name">${escapeHtml(mower.name || mower.id)}</td>
            <td class="mower-provider">${escapeHtml(mower.provider)}</td>
            <td class="mower-state">${escapeHtml(mower.state || "")}</td>
            <td class="mower-battery">${mower.battery_percent ?? ""}</td>
            <td class="mower-problem">${mower.is_problem ? "Yes" : "No"}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderMowerStatus(mowers) {
  if (!mowers.length) {
    return `<div class="empty">No mowers attached to this yard.</div>`;
  }
  return `
    <div class="status-grid">
      ${mowers.map((mower) => `
        <article class="mower-card">
          <div class="mower-card-header">
            <div class="mower-card-title">${escapeHtml(mower.name || mower.id)}</div>
            <span class="status-pill${mower.is_problem ? " problem" : ""}">
              ${mower.is_problem ? "Problem" : "OK"}
            </span>
          </div>
          <dl class="mower-facts">
            <dt>Provider</dt>
            <dd>${escapeHtml(mower.provider)}</dd>
            <dt>State</dt>
            <dd>${escapeHtml(mower.state || "Unknown")}</dd>
            <dt>Activity</dt>
            <dd>${escapeHtml(mower.activity || mower.state || "Unknown")}</dd>
            <dt>Battery</dt>
            <dd>${mower.battery_percent == null ? "Unknown" : `${mower.battery_percent}%`}</dd>
            <dt>Last updated</dt>
            <dd>${escapeHtml(formatDateTime(mower.updated_at))}</dd>
            <dt>Zone</dt>
            <dd>${escapeHtml(mower.yard_zone || "Unknown")}</dd>
            <dt>All zones</dt>
            <dd>${escapeHtml((mower.yard_zones || []).join(", ") || "None")}</dd>
            <dt>Location</dt>
            <dd>${formatCoordinate(mower.latitude, mower.longitude)}</dd>
            <dt>Error</dt>
            <dd>${escapeHtml(mower.error_code || "None")}</dd>
            <dt>Source</dt>
            <dd>${escapeHtml(mower.data_source || "Unknown")}</dd>
          </dl>
        </article>
      `).join("")}
    </div>
  `;
}

function renderMaps(yard) {
  const stamp = "20260524-location-maps";
  const yardId = encodeURIComponent(yard.entry_id);
  const base = `/robot_mower_yard_static/zone_editor.html?ha=1&readonly=1&refresh_ms=2000&yard_entry_id=${yardId}&v=${stamp}`;
  return `
    <div class="map-grid">
      <section class="map-panel">
        <div class="map-panel-header">
          <h3>Zone Map</h3>
          <button
            type="button"
            class="map-expand"
            data-map-title="${escapeHtml(yard.title)} Zone Map"
            data-map-src="${base}&mode=zones"
          >Expand</button>
        </div>
        <iframe title="${escapeHtml(yard.title)} zone map" src="${base}&mode=zones"></iframe>
      </section>
      <section class="map-panel">
        <div class="map-panel-header">
          <h3>Heatmap</h3>
          <button
            type="button"
            class="map-expand"
            data-map-title="${escapeHtml(yard.title)} Heatmap"
            data-map-src="${base}&mode=heatmap"
          >Expand</button>
        </div>
        <iframe title="${escapeHtml(yard.title)} heatmap" src="${base}&mode=heatmap"></iframe>
      </section>
    </div>
  `;
}

function formatCoordinate(latitude, longitude) {
  if (latitude == null || longitude == null) {
    return "Unknown";
  }
  const lat = Number(latitude);
  const lon = Number(longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    return "Unknown";
  }
  return `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
}

function formatDateTime(value) {
  if (!value) {
    return "Unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

if (!customElements.get("robot-mower-yard-panel")) {
  customElements.define("robot-mower-yard-panel", RobotMowerYardPanel);
}
