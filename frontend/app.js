(function () {
  "use strict";

  const TOKEN_KEY = "ticketdesk.token";
  const USER_KEY = "ticketdesk.user";

  const PUBLIC_ROUTES = new Set(["landing", "login", "register"]);

  const STATUS_TRANSITIONS = {
    OPEN: ["IN_PROGRESS"],
    IN_PROGRESS: ["RESOLVED", "OPEN"],
    RESOLVED: ["CLOSED", "IN_PROGRESS"],
    CLOSED: ["IN_PROGRESS"],
  };

  const viewEl = document.getElementById("view");
  const toastEl = document.getElementById("toast");
  const appShellEl = document.querySelector(".app-shell");
  const sidebarAuthEl = document.getElementById("sidebar-auth");
  const topbarBrandEl = document.getElementById("topbar-brand");
  const topbarActionsEl = document.getElementById("topbar-actions");
  const brandBellEl = document.getElementById("brand-bell");
  const dashboardNavLink = document.querySelector(
    '.nav a[data-route="dashboard"]'
  );
  const ticketsNavLink = document.querySelector(
    '.nav a[data-route="tickets"]'
  );
  const newTicketNavLink = document.querySelector(
    '.nav a[data-route="new"]'
  );

  const EYE_ICON =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"/><circle cx="12" cy="12" r="3"/></svg>';
  const EYE_OFF_ICON =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a20.6 20.6 0 0 1 5.06-5.94M9.9 4.24A10.4 10.4 0 0 1 12 4c7 0 11 8 11 8a20.6 20.6 0 0 1-3.22 4.44M14.12 14.12a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

  const THEME_KEY = "ticketdesk.theme";

  const THEME_PRESETS = [
    {
      id: "off-white",
      name: "Off-White",
      swatch: "#F8F9FA",
      vars: {
        "--bg": "#F8F9FA",
        "--panel": "#FFFFFF",
        "--border": "#E5E7EB",
        "--text": "#1E293B",
        "--text-muted": "#64748B",
        "--primary": "#3B82F6",
        "--primary-dark": "#2563EB",
        "--sidebar-bg": "#FFFFFF",
        "--sidebar-text": "#334155",
      },
    },
    {
      id: "soft-blue",
      name: "Soft Blue",
      swatch: "#3B82F6",
      vars: {
        "--bg": "#E0F2FE",
        "--panel": "#FFFFFF",
        "--border": "#BAE6FD",
        "--text": "#1E293B",
        "--text-muted": "#475569",
        "--primary": "#3B82F6",
        "--primary-dark": "#2563EB",
        "--sidebar-bg": "#FFFFFF",
        "--sidebar-text": "#334155",
      },
    },
    {
      id: "black",
      name: "Black",
      swatch: "#000000",
      vars: {
        "--bg": "#0B0F19",
        "--panel": "#151B28",
        "--border": "#2A3342",
        "--text": "#F1F5F9",
        "--text-muted": "#94A3B8",
        "--primary": "#60A5FA",
        "--primary-dark": "#3B82F6",
        "--sidebar-bg": "#0F1420",
        "--sidebar-text": "#CBD5E1",
      },
    },
  ];

  function getSavedTheme() {
    return localStorage.getItem(THEME_KEY) || THEME_PRESETS[0].id;
  }

  function applyTheme(id) {
    const preset =
      THEME_PRESETS.find((t) => t.id === id) || THEME_PRESETS[0];

    Object.entries(preset.vars).forEach(([key, value]) => {
      document.documentElement.style.setProperty(key, value);
    });

    localStorage.setItem(THEME_KEY, preset.id);
  }

  applyTheme(getSavedTheme());

  function wirePasswordToggles(container) {
    container.querySelectorAll('[data-field="password-toggle"]').forEach((btn) => {
      const input = btn.previousElementSibling;
      btn.innerHTML = EYE_ICON;

      btn.addEventListener("click", () => {
        const showing = input.type === "password";
        input.type = showing ? "text" : "password";
        btn.innerHTML = showing ? EYE_OFF_ICON : EYE_ICON;
        btn.setAttribute(
          "aria-label",
          showing ? "Hide password" : "Show password"
        );
      });
    });
  }

  // Set at deploy time - config.js is Terraform-generated in AWS with the
  // real ALB DNS name baked in (infra/s3_frontend_website.tf), and just a
  // local default otherwise. Not user-configurable in the UI; if you're
  // pointing this at a different backend for local testing, edit
  // config.js directly.
  function getApiBase() {
    return (window.TICKETDESK_DEFAULT_API_BASE || "").replace(/\/+$/, "");
  }

  // ---------- Auth state ----------

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }

  function getUser() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY));
    } catch (_) {
      return null;
    }
  }

  function setUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function isAuthenticated() {
    return Boolean(getToken());
  }

  function roleIs(...roles) {
    const user = getUser();
    return Boolean(user && roles.includes(user.role));
  }

  function clearAuth() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    stopNotificationPolling();
  }

  function showToast(message, isError) {
    toastEl.textContent = message;
    toastEl.hidden = false;
    toastEl.className = "toast" + (isError ? " toast-error" : " toast-ok");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => {
      toastEl.hidden = true;
    }, 4000);
  }

  // Every backend route lives under /api (see src/main.py). Deployed,
  // the frontend (S3 static website) and API (ALB) are separate origins
  // tied together with CORS rather than one CDN domain - see
  // infra/README.md's "Why no CloudFront". Callers below pass paths
  // without the prefix; it's added here in one place, along with the
  // bearer token for authenticated calls.
  async function api(path, options) {
    const base = getApiBase();
    const token = getToken();

    const opts = Object.assign({}, options);
    opts.headers = Object.assign({}, options && options.headers);

    if (token) {
      opts.headers["Authorization"] = "Bearer " + token;
    }

    const response = await fetch(base + "/api" + path, opts);

    if (response.status === 401) {
      const wasAuthenticated = isAuthenticated();
      clearAuth();

      // Land on the marketing page, not straight into the login form -
      // e.g. after a dev server restart mints a new session-signing
      // secret (src/security.py) and this stale token stops verifying.
      if (wasAuthenticated && window.location.hash !== "#/") {
        window.location.hash = "#/";
      }

      throw new Error("Your session has expired. Please log in again.");
    }

    if (!response.ok) {
      let detail = response.statusText;

      try {
        const body = await response.json();

        if (Array.isArray(body.detail)) {
          detail = body.detail.map((e) => e.msg || String(e)).join(" ");
        } else if (body.detail) {
          detail = body.detail;
        }
      } catch (_) {
        // response had no JSON body
      }

      throw new Error(detail);
    }

    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
      return response.json();
    }

    return response;
  }

  function formatDate(isoString) {
    if (!isoString) return "";
    const d = new Date(isoString);
    return d.toLocaleString();
  }

  function useTemplate(id) {
    const tpl = document.getElementById(id);
    return tpl.content.cloneNode(true);
  }

  function setActiveNav(route) {
    document.querySelectorAll(".nav a").forEach((a) => {
      a.classList.toggle("active", a.dataset.route === route);
    });
  }

  // Bumped by render() on every route change. Async view functions
  // capture the value at the top and re-check it after each await -
  // if it's moved on, the user navigated away while a fetch was in
  // flight, so the old view's DOM is gone and must not be touched.
  let currentRenderToken = 0;

  // ---------- Sidebar (auth box + notification bell) ----------

  let notificationPollTimer = null;

  function stopNotificationPolling() {
    if (notificationPollTimer) {
      clearInterval(notificationPollTimer);
      notificationPollTimer = null;
    }
  }

  function startNotificationPolling() {
    stopNotificationPolling();
    refreshUnreadCount();
    notificationPollTimer = setInterval(refreshUnreadCount, 20000);
  }

  async function refreshUnreadCount() {
    const badge = document.getElementById("notif-badge");
    if (!badge) return;

    try {
      const data = await api("/notifications/unread-count");

      if (data.unread_count > 0) {
        badge.textContent = data.unread_count > 9 ? "9+" : String(data.unread_count);
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    } catch (_) {
      // Transient errors (e.g. right after logout) shouldn't spam toasts.
    }
  }

  async function loadNotificationDropdown(dropdown) {
    dropdown.replaceChildren();

    try {
      const items = await api("/notifications");

      if (items.length === 0) {
        const empty = document.createElement("p");
        empty.className = "hint notif-empty";
        empty.textContent = "No notifications yet.";
        dropdown.appendChild(empty);
        return;
      }

      items.forEach((n) => {
        const item = document.createElement("div");
        item.className = "notif-item" + (n.is_read ? "" : " notif-unread");

        const msg = document.createElement("div");
        msg.className = "notif-message";
        msg.textContent = n.message;

        const meta = document.createElement("div");
        meta.className = "notif-meta";
        meta.textContent = formatDate(n.created_at);

        item.append(msg, meta);

        item.addEventListener("click", async () => {
          if (!n.is_read) {
            try {
              await api("/notifications/" + n.id + "/read", {
                method: "PATCH",
              });
            } catch (_) {
              // Non-fatal - still navigate.
            }
            refreshUnreadCount();
          }

          if (n.ticket_id) {
            dropdown.hidden = true;
            window.location.hash = "#/tickets/" + n.ticket_id;
          }
        });

        dropdown.appendChild(item);
      });

      const markAllBtn = document.createElement("button");
      markAllBtn.type = "button";
      markAllBtn.className = "btn btn-ghost notif-mark-all";
      markAllBtn.textContent = "Mark all read";

      markAllBtn.addEventListener("click", async (e) => {
        e.stopPropagation();

        try {
          await api("/notifications/read-all", { method: "PATCH" });
          await loadNotificationDropdown(dropdown);
          refreshUnreadCount();
        } catch (err) {
          showToast("Could not update notifications: " + err.message, true);
        }
      });

      dropdown.appendChild(markAllBtn);
    } catch (err) {
      const p = document.createElement("p");
      p.className = "hint";
      p.textContent = "Could not load notifications.";
      dropdown.appendChild(p);
    }
  }

  function buildNotificationBell() {
    const wrap = document.createElement("div");
    wrap.className = "notif-wrap";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "notif-bell";
    btn.setAttribute("aria-label", "Notifications");
    btn.textContent = "🔔";

    const badge = document.createElement("span");
    badge.id = "notif-badge";
    badge.className = "notif-badge";
    badge.hidden = true;
    btn.appendChild(badge);

    const dropdown = document.createElement("div");
    dropdown.className = "notif-dropdown";
    dropdown.hidden = true;

    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const wasHidden = dropdown.hidden;
      dropdown.hidden = !wasHidden;

      if (wasHidden) {
        await loadNotificationDropdown(dropdown);
      }
    });

    dropdown.addEventListener("click", (e) => e.stopPropagation());
    document.addEventListener("click", () => {
      dropdown.hidden = true;
    });

    wrap.append(btn, dropdown);
    return wrap;
  }

  function renderSidebarAuth() {
    sidebarAuthEl.replaceChildren();

    if (!isAuthenticated()) {
      dashboardNavLink.hidden = true;
      ticketsNavLink.hidden = true;
      newTicketNavLink.hidden = true;
      return;
    }

    const user = getUser();

    dashboardNavLink.hidden = !roleIs("ADMIN", "AGENT");
    ticketsNavLink.hidden = false;
    newTicketNavLink.hidden = false;

    const info = document.createElement("div");
    info.className = "sidebar-user";

    const name = document.createElement("span");
    name.className = "sidebar-username";
    name.textContent = user.username;

    const role = document.createElement("span");
    role.className = "role-badge role-badge-" + user.role.toLowerCase();
    role.textContent = user.role;

    info.append(name, role);

    const logoutBtn = document.createElement("button");
    logoutBtn.type = "button";
    logoutBtn.className = "btn btn-ghost btn-logout";
    logoutBtn.textContent = "Log out";
    logoutBtn.addEventListener("click", () => {
      clearAuth();
      window.location.hash = "#/";
    });

    sidebarAuthEl.append(info, logoutBtn);
  }

  function renderBrandBell() {
    brandBellEl.replaceChildren();

    if (isAuthenticated()) {
      brandBellEl.appendChild(buildNotificationBell());
      startNotificationPolling();
    } else {
      stopNotificationPolling();
    }
  }

  function buildThemeBox() {
    const wrap = document.createElement("div");
    wrap.className = "theme-wrap";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "theme-toggle-btn";
    btn.setAttribute("aria-label", "Theme colors");
    btn.textContent = "🎨";

    const panel = document.createElement("div");
    panel.className = "theme-panel";
    panel.hidden = true;

    const title = document.createElement("p");
    title.className = "theme-panel-title";
    title.textContent = "Theme";
    panel.appendChild(title);

    const dotsRow = document.createElement("div");
    dotsRow.className = "theme-dots-row";

    const current = getSavedTheme();

    THEME_PRESETS.forEach((preset) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className =
        "theme-dot" + (preset.id === current ? " theme-dot-active" : "");
      dot.style.background = preset.swatch;
      dot.title = preset.name;
      dot.setAttribute("aria-label", preset.name);

      dot.addEventListener("click", (e) => {
        e.stopPropagation();
        applyTheme(preset.id);
        dotsRow
          .querySelectorAll(".theme-dot")
          .forEach((d) => d.classList.remove("theme-dot-active"));
        dot.classList.add("theme-dot-active");
      });

      dotsRow.appendChild(dot);
    });

    panel.appendChild(dotsRow);

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      panel.hidden = !panel.hidden;
    });

    panel.addEventListener("click", (e) => e.stopPropagation());
    document.addEventListener("click", () => {
      panel.hidden = true;
    });

    wrap.append(btn, panel);
    return wrap;
  }

  function renderTopbarActions() {
    topbarActionsEl.replaceChildren();

    if (!isAuthenticated()) {
      const loginLink = document.createElement("a");
      loginLink.href = "#/login";
      loginLink.className = "btn btn-ghost btn-sm";
      loginLink.textContent = "Log In";

      const registerLink = document.createElement("a");
      registerLink.href = "#/register";
      registerLink.className = "btn btn-primary btn-sm";
      registerLink.textContent = "Sign Up";

      topbarActionsEl.append(loginLink, registerLink);
    }

    topbarActionsEl.appendChild(buildThemeBox());
  }

  function renderTopbarBrand() {
    topbarBrandEl.replaceChildren();

    if (isAuthenticated()) return;

    const link = document.createElement("a");
    link.href = "#/";
    link.className = "topbar-brand-link";

    const mark = document.createElement("span");
    mark.className = "brand-mark";
    mark.textContent = "TD";

    const name = document.createElement("span");
    name.className = "brand-name";
    name.textContent = "TicketDesk";

    link.append(mark, name);
    topbarBrandEl.appendChild(link);
  }

  // ---------- Landing ----------

  function renderLanding() {
    const node = useTemplate("tpl-landing");
    viewEl.replaceChildren(node);
  }

  // ---------- Login / Register ----------

  function renderLogin() {
    const node = useTemplate("tpl-login");
    viewEl.replaceChildren(node);
    wirePasswordToggles(viewEl);

    const form = viewEl.querySelector('[data-field="login-form"]');

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const formData = new FormData(form);

      try {
        const auth = await api("/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: formData.get("username"),
            password: formData.get("password"),
          }),
        });

        setToken(auth.token);
        setUser({
          id: auth.user_id,
          username: auth.username,
          email: auth.email,
          role: auth.role,
        });

        window.location.hash = ["ADMIN", "AGENT"].includes(auth.role)
          ? "#/dashboard"
          : "#/tickets";
      } catch (err) {
        showToast("Login failed: " + err.message, true);
      }
    });
  }

  function renderRegister() {
    const node = useTemplate("tpl-register");
    viewEl.replaceChildren(node);
    wirePasswordToggles(viewEl);

    const form = viewEl.querySelector('[data-field="register-form"]');

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const formData = new FormData(form);

      try {
        await api("/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: formData.get("username"),
            email: formData.get("email"),
            password: formData.get("password"),
            role: formData.get("role"),
          }),
        });

        showToast("Account created. Please log in.", false);
        window.location.hash = "#/login";
      } catch (err) {
        showToast("Could not register: " + err.message, true);
      }
    });
  }

  // ---------- Dashboard ----------

  async function renderDashboard() {
    const myToken = currentRenderToken;
    setActiveNav("dashboard");
    const node = useTemplate("tpl-dashboard");
    viewEl.replaceChildren(node);

    try {
      const data = await api("/tickets/dashboard");
      if (myToken !== currentRenderToken) return;

      viewEl.querySelector('[data-field="total"]').textContent =
        data.total_tickets;

      renderBars(
        viewEl.querySelector('[data-field="status-bars"]'),
        data.by_status,
        data.total_tickets
      );

      renderBars(
        viewEl.querySelector('[data-field="priority-bars"]'),
        data.by_priority,
        data.total_tickets
      );
    } catch (err) {
      showToast("Could not load dashboard: " + err.message, true);
    }
  }

  function renderBars(container, counts, total) {
    container.replaceChildren();

    Object.entries(counts).forEach(([label, count]) => {
      const pct = total > 0 ? Math.round((count / total) * 100) : 0;

      const row = document.createElement("div");
      row.className = "bar-row";

      const labelEl = document.createElement("span");
      labelEl.className = "bar-label";
      labelEl.textContent = label;

      const track = document.createElement("span");
      track.className = "bar-track";

      const fill = document.createElement("span");
      fill.className = "bar-fill bar-" + label.toLowerCase();
      fill.style.width = pct + "%";
      track.appendChild(fill);

      const countEl = document.createElement("span");
      countEl.className = "bar-count";
      countEl.textContent = count;

      row.append(labelEl, track, countEl);
      container.appendChild(row);
    });
  }

  // ---------- Ticket list ----------

  function cell(text) {
    const td = document.createElement("td");
    td.textContent = text;
    return td;
  }

  function badgeCell(value, kind) {
    const td = document.createElement("td");
    const span = document.createElement("span");
    span.className = "badge badge-" + kind + "-" + value.toLowerCase();
    span.textContent = value.replace("_", " ");
    td.appendChild(span);
    return td;
  }

  function unassignedCell() {
    const td = document.createElement("td");
    const span = document.createElement("span");
    span.className = "unassigned-label";
    span.textContent = "Unassigned";
    td.appendChild(span);
    return td;
  }

  async function renderTickets() {
    const myToken = currentRenderToken;
    setActiveNav("tickets");
    const node = useTemplate("tpl-tickets");
    viewEl.replaceChildren(node);

    const filters = {
      status: "",
      priority: "",
      category: "",
      assigned_status: "",
    };
    let page = 1;
    const size = 10;
    let totalPages = 0;

    if (roleIs("ADMIN")) {
      viewEl.querySelector(
        '[data-field="assigned-filter-wrap"]'
      ).hidden = false;
    }

    viewEl.querySelectorAll("[data-filter]").forEach((el) => {
      el.addEventListener("change", () => {
        filters[el.dataset.filter] = el.value;
        page = 1;
        loadTickets();
      });
    });

    const prevBtn = viewEl.querySelector('[data-field="prev-page"]');
    const nextBtn = viewEl.querySelector('[data-field="next-page"]');
    const pageInfo = viewEl.querySelector('[data-field="page-info"]');

    prevBtn.addEventListener("click", () => {
      if (page > 1) {
        page -= 1;
        loadTickets();
      }
    });

    nextBtn.addEventListener("click", () => {
      if (page < totalPages) {
        page += 1;
        loadTickets();
      }
    });

    async function loadTickets() {
      const tbody = viewEl.querySelector('[data-field="ticket-rows"]');
      tbody.replaceChildren();

      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => {
        if (v) params.set(k, v);
      });
      params.set("page", String(page));
      params.set("size", String(size));

      try {
        const result = await api("/tickets?" + params.toString());
        if (myToken !== currentRenderToken) return;
        totalPages = result.total_pages || 0;

        pageInfo.textContent =
          totalPages === 0
            ? "No results"
            : `Page ${result.page} of ${totalPages} (${result.total} total)`;
        prevBtn.disabled = page <= 1;
        nextBtn.disabled = totalPages === 0 || page >= totalPages;

        if (result.items.length === 0) {
          const tr = document.createElement("tr");
          const td = document.createElement("td");
          td.colSpan = 7;
          td.className = "empty-row";
          td.textContent = "No tickets match these filters.";
          tr.appendChild(td);
          tbody.appendChild(tr);
          return;
        }

        result.items.forEach((t) => {
          const tr = document.createElement("tr");
          tr.className = "ticket-row";
          tr.addEventListener("click", () => {
            window.location.hash = "#/tickets/" + t.id;
          });

          tr.appendChild(cell(t.ticket_number));
          tr.appendChild(cell(t.title));
          tr.appendChild(cell(t.category));
          tr.appendChild(badgeCell(t.priority, "priority"));
          tr.appendChild(badgeCell(t.status, "status"));
          tr.appendChild(cell(t.created_by_username));
          tr.appendChild(
            t.assigned_to_username ? cell(t.assigned_to_username) : unassignedCell()
          );

          tbody.appendChild(tr);
        });
      } catch (err) {
        showToast("Could not load tickets: " + err.message, true);
      }
    }

    loadTickets();
  }

  // ---------- New ticket ----------

  function renderNewTicket() {
    setActiveNav("new");
    const node = useTemplate("tpl-new-ticket");
    viewEl.replaceChildren(node);

    const form = viewEl.querySelector('[data-field="create-form"]');

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const formData = new FormData(form);
      const payload = {
        title: formData.get("title"),
        description: formData.get("description"),
        category: formData.get("category"),
        priority: formData.get("priority"),
      };

      try {
        const ticket = await api("/tickets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        showToast("Ticket " + ticket.ticket_number + " created.", false);
        window.location.hash = "#/tickets/" + ticket.id;
      } catch (err) {
        showToast("Could not create ticket: " + err.message, true);
      }
    });
  }

  // ---------- Ticket detail ----------

  async function renderTicketDetail(ticketId) {
    const myToken = currentRenderToken;
    setActiveNav("tickets");
    const node = useTemplate("tpl-ticket-detail");
    viewEl.replaceChildren(node);

    function renderStatusControl(ticket) {
      const control = viewEl.querySelector('[data-field="status-control"]');
      const buttonsWrap = viewEl.querySelector('[data-field="status-buttons"]');
      buttonsWrap.replaceChildren();

      const nextOptions = roleIs("ADMIN", "AGENT")
        ? STATUS_TRANSITIONS[ticket.status] || []
        : [];

      if (nextOptions.length === 0) {
        control.hidden = true;
        return;
      }

      control.hidden = false;

      nextOptions.forEach((target) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-secondary";
        btn.textContent = target.replace("_", " ");

        btn.addEventListener("click", async () => {
          try {
            await api("/tickets/" + ticketId + "/status", {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ status: target }),
            });
            showToast("Status updated to " + target, false);
            await load();
          } catch (err) {
            showToast("Could not update status: " + err.message, true);
          }
        });

        buttonsWrap.appendChild(btn);
      });
    }

    async function renderAssignControl(ticket) {
      const control = viewEl.querySelector('[data-field="assign-control"]');

      if (!roleIs("ADMIN")) {
        control.hidden = true;
        return;
      }

      control.hidden = false;

      const select = viewEl.querySelector('[data-field="assign-select"]');
      select.replaceChildren();

      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Select an agent…";
      select.appendChild(placeholder);

      try {
        const agents = await api("/auth/agents");
        if (myToken !== currentRenderToken) return;

        agents.forEach((agent) => {
          const opt = document.createElement("option");
          opt.value = String(agent.id);
          opt.textContent = agent.username;
          if (ticket.assigned_to === agent.id) opt.selected = true;
          select.appendChild(opt);
        });
      } catch (err) {
        showToast("Could not load agents: " + err.message, true);
      }

      const assignBtn = viewEl.querySelector('[data-field="assign-btn"]');

      assignBtn.onclick = async () => {
        if (!select.value) {
          showToast("Choose an agent first.", true);
          return;
        }

        try {
          await api(
            "/tickets/" +
              ticketId +
              "/assign?" +
              new URLSearchParams({ agent_id: select.value }),
            { method: "PATCH" }
          );
          showToast("Ticket assigned.", false);
          await load();
        } catch (err) {
          showToast("Could not assign ticket: " + err.message, true);
        }
      };
    }

    async function load() {
      let ticket;

      try {
        ticket = await api("/tickets/" + ticketId);
      } catch (err) {
        showToast("Could not load ticket: " + err.message, true);
        return;
      }
      if (myToken !== currentRenderToken) return;

      viewEl.querySelector('[data-field="ticket_number"]').textContent =
        ticket.ticket_number;
      viewEl.querySelector('[data-field="title"]').textContent = ticket.title;
      viewEl.querySelector('[data-field="category"]').textContent =
        ticket.category;
      viewEl.querySelector('[data-field="description"]').textContent =
        ticket.description;
      viewEl.querySelector('[data-field="created_at"]').textContent =
        formatDate(ticket.created_at);
      viewEl.querySelector('[data-field="created_by"]').textContent =
        ticket.created_by_username;
      viewEl.querySelector('[data-field="assignment-info"]').textContent =
        ticket.assigned_to_username
          ? "Assigned to " + ticket.assigned_to_username
          : "Unassigned";

      const priorityBadge = viewEl.querySelector(
        '[data-field="priority-badge"]'
      );
      priorityBadge.textContent = ticket.priority;
      priorityBadge.className =
        "badge badge-priority-" + ticket.priority.toLowerCase();

      const statusBadge = viewEl.querySelector('[data-field="status-badge"]');
      statusBadge.textContent = ticket.status.replace("_", " ");
      statusBadge.className =
        "badge badge-status-" + ticket.status.toLowerCase();

      renderStatusControl(ticket);
      await renderAssignControl(ticket);

      await loadAttachment();
      await loadComments();
    }

    async function loadAttachment() {
      const container = viewEl.querySelector(
        '[data-field="attachment-current"]'
      );
      container.replaceChildren();

      try {
        const attachment = await api(
          "/tickets/" + ticketId + "/attachments"
        );
        if (myToken !== currentRenderToken) return;

        if (attachment) {
          const sizeLabel = attachment.size_bytes
            ? " (" + Math.ceil(attachment.size_bytes / 1024) + " KB)"
            : "";

          const link = document.createElement("a");
          link.href = attachment.download_url;
          link.textContent = attachment.original_filename + sizeLabel;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          container.appendChild(link);

          // Written by the S3-triggered Lambda thumbnailer (M5) a few
          // seconds after upload - if it isn't there yet, hide the <img>
          // instead of showing a broken-image icon.
          const thumb = document.createElement("img");
          thumb.className = "attachment-thumb";
          thumb.alt = "thumbnail";
          thumb.src = attachment.thumbnail_url;
          thumb.onerror = () => thumb.remove();
          container.appendChild(thumb);
        } else {
          const p = document.createElement("p");
          p.className = "hint";
          p.textContent = "No attachment yet.";
          container.appendChild(p);
        }
      } catch (err) {
        showToast("Could not load attachment: " + err.message, true);
      }
    }

    const attachmentForm = viewEl.querySelector(
      '[data-field="attachment-form"]'
    );

    attachmentForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      const fileInput = attachmentForm.querySelector('input[type="file"]');
      const file = fileInput.files[0];

      if (!file) return;

      try {
        // 1. Ask the API for a presigned POST - the file bytes never
        //    touch it (checklist item 23).
        const presigned = await api(
          "/tickets/" + ticketId + "/attachments/presign",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename: file.name,
              content_type: file.type,
            }),
          }
        );

        // 2. Upload straight to S3 using the fields S3 requires.
        const uploadForm = new FormData();
        Object.entries(presigned.upload_fields).forEach(([key, value]) => {
          uploadForm.append(key, value);
        });
        uploadForm.append("file", file);

        const uploadResponse = await fetch(presigned.upload_url, {
          method: "POST",
          body: uploadForm,
        });

        if (!uploadResponse.ok) {
          throw new Error(
            "S3 rejected the upload (" + uploadResponse.status + ")"
          );
        }

        showToast(
          "Attachment uploaded. Thumbnail will appear shortly.",
          false
        );
        fileInput.value = "";
        await loadAttachment();
      } catch (err) {
        showToast("Could not upload attachment: " + err.message, true);
      }
    });

    async function loadComments() {
      const list = viewEl.querySelector('[data-field="comments-list"]');
      list.replaceChildren();

      try {
        const comments = await api(
          "/tickets/" + ticketId + "/comments"
        );
        if (myToken !== currentRenderToken) return;

        if (comments.length === 0) {
          const p = document.createElement("p");
          p.className = "hint";
          p.textContent = "No comments yet.";
          list.appendChild(p);
          return;
        }

        comments.forEach((c) => {
          const item = document.createElement("div");
          item.className = "comment";

          const meta = document.createElement("div");
          meta.className = "comment-meta";
          meta.textContent =
            c.author_username + " · " + formatDate(c.created_at);

          const body = document.createElement("div");
          body.className = "comment-body";
          body.textContent = c.message;

          item.append(meta, body);
          list.appendChild(item);
        });
      } catch (err) {
        showToast("Could not load comments: " + err.message, true);
      }
    }

    const commentForm = viewEl.querySelector('[data-field="comment-form"]');

    commentForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      const formData = new FormData(commentForm);
      const payload = { message: formData.get("message") };

      try {
        await api("/tickets/" + ticketId + "/comments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        commentForm.reset();
        await loadComments();
      } catch (err) {
        showToast("Could not add comment: " + err.message, true);
      }
    });

    load();
  }

  // ---------- Router ----------

  function defaultRoute() {
    if (!isAuthenticated()) return "landing";
    return roleIs("ADMIN", "AGENT") ? "dashboard" : "tickets";
  }

  const PAGE_TITLES = {
    landing: "",
    login: "Login",
    register: "Register",
    dashboard: "Dashboard",
    tickets: "Tickets",
  };

  function setPageTitle(route, parts) {
    let label;

    if (route === "tickets" && parts[1] === "new") {
      label = "New Ticket";
    } else if (route === "tickets" && parts[1]) {
      label = "Ticket #" + parts[1];
    } else {
      label = PAGE_TITLES[route] || "";
    }

    document.title = label ? "TicketDesk – " + label : "TicketDesk";
  }

  function render() {
    const hash = window.location.hash || "#/" + defaultRoute();
    const parts = hash.replace(/^#\//, "").split("/").filter(Boolean);
    const route = parts[0] || defaultRoute();

    if (!isAuthenticated() && !PUBLIC_ROUTES.has(route)) {
      // Land on the marketing page, not straight into the login form -
      // this is also what a stale/invalidated session (e.g. right after
      // a dev server restart - see verifySessionOnBoot below) resolves
      // to, since api()'s 401 handling redirects here too.
      window.location.hash = "#/";
      return;
    }

    if (isAuthenticated() && PUBLIC_ROUTES.has(route)) {
      window.location.hash = "#/" + defaultRoute();
      return;
    }

    if (route === "dashboard" && !roleIs("ADMIN", "AGENT")) {
      window.location.hash = "#/tickets";
      return;
    }

    currentRenderToken += 1;

    appShellEl.classList.toggle("no-sidebar", PUBLIC_ROUTES.has(route));

    setPageTitle(route, parts);
    renderSidebarAuth();
    renderTopbarBrand();
    renderTopbarActions();
    renderBrandBell();

    if (route === "landing") {
      renderLanding();
    } else if (route === "login") {
      renderLogin();
    } else if (route === "register") {
      renderRegister();
    } else if (route === "dashboard") {
      renderDashboard();
    } else if (route === "tickets" && parts[1] === "new") {
      renderNewTicket();
    } else if (route === "tickets" && parts[1]) {
      renderTicketDetail(parts[1]);
    } else if (route === "tickets") {
      renderTickets();
    } else {
      window.location.hash = "#/" + defaultRoute();
    }
  }

  // If a token is sitting in localStorage from a previous visit, confirm
  // it's still valid before the first render instead of waiting for the
  // next notification poll (up to 20s away) to notice. A dev server
  // restart mints a new JWT_SECRET (see src/security.py), which makes
  // any old token fail here - api()'s existing 401 handling then clears
  // it and routes to #/login, so a restart actually logs the user out
  // instead of leaving a stale "logged in" UI up.
  async function verifySessionOnBoot() {
    if (!getToken()) return;

    try {
      await api("/auth/me");
    } catch (_) {
      // A 401 is already handled (storage cleared, redirected) by
      // api() itself. Anything else (e.g. the backend being briefly
      // unreachable) shouldn't log a valid session out.
    }
  }

  window.addEventListener("hashchange", render);
  window.addEventListener("DOMContentLoaded", async () => {
    await verifySessionOnBoot();
    render();
  });
})();
