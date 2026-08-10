(function () {
  "use strict";

  const API_BASE_KEY = "ticketdesk.apiBase";
  const viewEl = document.getElementById("view");
  const toastEl = document.getElementById("toast");
  const apiBaseInput = document.getElementById("api-base-input");
  const apiBaseSaveBtn = document.getElementById("api-base-save");
  const apiStatusEl = document.getElementById("api-status");

  function getApiBase() {
    return (
      localStorage.getItem(API_BASE_KEY) ||
      window.TICKETDESK_DEFAULT_API_BASE ||
      ""
    ).replace(/\/+$/, "");
  }

  function setApiBase(value) {
    localStorage.setItem(API_BASE_KEY, value.replace(/\/+$/, ""));
  }

  apiBaseInput.value = getApiBase();

  apiBaseSaveBtn.addEventListener("click", () => {
    setApiBase(apiBaseInput.value.trim());
    checkApiHealth();
    render();
  });

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
  // without the prefix; it's added here in one place.
  async function api(path, options) {
    const base = getApiBase();

    const response = await fetch(base + "/api" + path, options);

    if (!response.ok) {
      let detail = response.statusText;

      try {
        const body = await response.json();
        detail = body.detail || detail;
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

  async function checkApiHealth() {
    const base = getApiBase();

    try {
      const res = await fetch(base + "/api/health");

      if (res.ok) {
        apiStatusEl.textContent = "Connected";
        apiStatusEl.className = "api-status status-good";
      } else {
        apiStatusEl.textContent = "Unreachable";
        apiStatusEl.className = "api-status status-bad";
      }
    } catch (_) {
      apiStatusEl.textContent = "Unreachable";
      apiStatusEl.className = "api-status status-bad";
    }
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

  // ---------- Dashboard ----------

  async function renderDashboard() {
    setActiveNav("dashboard");
    const node = useTemplate("tpl-dashboard");
    viewEl.replaceChildren(node);

    try {
      const data = await api("/dashboard");

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

  async function renderTickets() {
    setActiveNav("tickets");
    const node = useTemplate("tpl-tickets");
    viewEl.replaceChildren(node);

    const filters = { status: "", priority: "", category: "" };

    const filterEls = viewEl.querySelectorAll("[data-filter]");
    filterEls.forEach((el) => {
      el.addEventListener("change", () => {
        filters[el.dataset.filter] = el.value;
        loadTickets();
      });
    });

    async function loadTickets() {
      const tbody = viewEl.querySelector('[data-field="ticket-rows"]');
      tbody.replaceChildren();

      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => {
        if (v) params.set(k, v);
      });

      try {
        const tickets = await api(
          "/tickets" + (params.toString() ? "?" + params.toString() : "")
        );

        if (tickets.length === 0) {
          const tr = document.createElement("tr");
          const td = document.createElement("td");
          td.colSpan = 6;
          td.className = "empty-row";
          td.textContent = "No tickets match these filters.";
          tr.appendChild(td);
          tbody.appendChild(tr);
          return;
        }

        tickets.forEach((t) => {
          const tr = document.createElement("tr");
          tr.className = "ticket-row";
          tr.addEventListener("click", () => {
            window.location.hash = "#/tickets/" + t.id;
          });

          tr.appendChild(cell(String(t.id)));
          tr.appendChild(cell(t.title));
          tr.appendChild(cell(t.category));
          tr.appendChild(badgeCell(t.priority, "priority"));
          tr.appendChild(badgeCell(t.status, "status"));
          tr.appendChild(cell(formatDate(t.updated_at)));

          tbody.appendChild(tr);
        });
      } catch (err) {
        showToast("Could not load tickets: " + err.message, true);
      }
    }

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

        showToast("Ticket #" + ticket.id + " created.", false);
        window.location.hash = "#/tickets/" + ticket.id;
      } catch (err) {
        showToast("Could not create ticket: " + err.message, true);
      }
    });
  }

  // ---------- Ticket detail ----------

  async function renderTicketDetail(ticketId) {
    setActiveNav("tickets");
    const node = useTemplate("tpl-ticket-detail");
    viewEl.replaceChildren(node);

    async function load() {
      let ticket;

      try {
        ticket = await api("/tickets/" + ticketId);
      } catch (err) {
        showToast("Could not load ticket: " + err.message, true);
        return;
      }

      viewEl.querySelector('[data-field="id"]').textContent = ticket.id;
      viewEl.querySelector('[data-field="title"]').textContent = ticket.title;
      viewEl.querySelector('[data-field="category"]').textContent =
        ticket.category;
      viewEl.querySelector('[data-field="description"]').textContent =
        ticket.description;
      viewEl.querySelector('[data-field="created_at"]').textContent =
        formatDate(ticket.created_at);

      const priorityBadge = viewEl.querySelector(
        '[data-field="priority-badge"]'
      );
      priorityBadge.textContent = ticket.priority;
      priorityBadge.className =
        "badge badge-priority-" + ticket.priority.toLowerCase();

      const statusSelect = viewEl.querySelector(
        '[data-field="status-select"]'
      );
      statusSelect.value = ticket.status;
      statusSelect.onchange = async () => {
        try {
          await api("/tickets/" + ticketId + "/status", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: statusSelect.value }),
          });
          showToast("Status updated to " + statusSelect.value, false);
        } catch (err) {
          showToast("Could not update status: " + err.message, true);
        }
      };

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
          meta.textContent = c.author + " · " + formatDate(c.created_at);

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
      const payload = {
        author: formData.get("author"),
        message: formData.get("message"),
      };

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

  function render() {
    const hash = window.location.hash || "#/dashboard";
    const parts = hash.replace(/^#\//, "").split("/").filter(Boolean);

    if (parts.length === 0 || parts[0] === "dashboard") {
      renderDashboard();
    } else if (parts[0] === "tickets" && parts[1] === "new") {
      renderNewTicket();
    } else if (parts[0] === "tickets" && parts[1]) {
      renderTicketDetail(parts[1]);
    } else if (parts[0] === "tickets") {
      renderTickets();
    } else {
      renderDashboard();
    }
  }

  window.addEventListener("hashchange", render);
  window.addEventListener("DOMContentLoaded", () => {
    checkApiHealth();
    render();
  });
})();
