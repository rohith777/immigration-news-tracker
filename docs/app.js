(function () {
  "use strict";

  const CATEGORY_ORDER = ["All", "H-1B", "F-1 / OPT / CPT", "I-140", "PERM", "Green Card"];

  const feedEl = document.getElementById("feed");
  const filtersEl = document.getElementById("filters");
  const searchEl = document.getElementById("search");
  const updatedAtEl = document.getElementById("updated-at");
  const itemCountEl = document.getElementById("item-count");

  let allItems = [];
  let activeCategory = "All";
  let searchQuery = "";

  // Point "View source" at wherever this page is actually hosted.
  const repoLink = document.getElementById("repo-link");
  if (repoLink && location.hostname.endsWith("github.io")) {
    const [user] = location.hostname.split(".");
    const repo = location.pathname.split("/").filter(Boolean)[0];
    if (user && repo) repoLink.href = `https://github.com/${user}/${repo}`;
  }

  function timeAgo(iso) {
    if (!iso) return "undated";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "undated";
    const diffMs = Date.now() - then;
    const mins = Math.round(diffMs / 60000);
    if (mins < 60) return mins <= 1 ? "just now" : `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.round(hours / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  function dayKey(iso) {
    if (!iso) return "Undated";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "Undated";
    return d.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  }

  function escapeHtml(str) {
    return str.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  function countFor(category) {
    if (category === "All") return allItems.length;
    return allItems.filter((i) => i.categories.includes(category)).length;
  }

  function renderFilters() {
    filtersEl.innerHTML = "";
    const present = CATEGORY_ORDER.filter((c) => c === "All" || countFor(c) > 0);
    for (const cat of present) {
      const btn = document.createElement("button");
      btn.className = "filter-btn" + (cat === activeCategory ? " active" : "");
      btn.type = "button";
      btn.innerHTML = `${escapeHtml(cat)} <span class="count">${countFor(cat)}</span>`;
      btn.addEventListener("click", () => {
        activeCategory = cat;
        renderFilters();
        renderFeed();
      });
      filtersEl.appendChild(btn);
    }
  }

  function matchesSearch(item, q) {
    if (!q) return true;
    const hay = (item.title + " " + item.summary + " " + item.source_name).toLowerCase();
    return hay.includes(q);
  }

  function renderFeed() {
    const q = searchQuery.trim().toLowerCase();
    const filtered = allItems.filter((item) => {
      const catOk = activeCategory === "All" || item.categories.includes(activeCategory);
      return catOk && matchesSearch(item, q);
    });

    if (filtered.length === 0) {
      feedEl.innerHTML = `<p class="empty">No matching updates. Try a different filter or search term.</p>`;
      return;
    }

    let html = "";
    let lastDay = null;

    for (const item of filtered) {
      const day = dayKey(item.published);
      if (day !== lastDay) {
        html += `<h2 class="day-heading">${escapeHtml(day)}</h2>`;
        lastDay = day;
      }

      const tags = item.categories
        .map((c) => `<span class="tag">${escapeHtml(c)}</span>`)
        .join("");

      html += `
        <article class="item">
          <div class="item-tags">${tags}</div>
          <h2><a href="${item.url}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a></h2>
          ${item.summary ? `<p class="summary">${escapeHtml(item.summary)}</p>` : ""}
          <p class="citation">Source: <a href="${item.url}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.source_name)}</a> · ${timeAgo(item.published)}</p>
        </article>`;
    }

    feedEl.innerHTML = html;
  }

  searchEl.addEventListener("input", (e) => {
    searchQuery = e.target.value;
    renderFeed();
  });

  fetch("data/news.json", { cache: "no-store" })
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((data) => {
      allItems = data.items || [];
      updatedAtEl.textContent = data.generated_at
        ? `Updated ${timeAgo(data.generated_at)}`
        : "Updated recently";
      itemCountEl.textContent = `${allItems.length} tracked updates`;
      renderFilters();
      renderFeed();
    })
    .catch((err) => {
      feedEl.innerHTML = `<p class="empty">Couldn't load news data (${escapeHtml(String(err.message || err))}).
        If this is a brand-new deployment, the GitHub Action hasn't run yet — trigger it once from the
        Actions tab, or wait for the next scheduled run.</p>`;
      updatedAtEl.textContent = "No data yet";
    });
})();
