const scanButton = document.querySelector("#scanButton");
const refreshButton = document.querySelector("#refreshButton");
const searchForm = document.querySelector("#searchForm");
const shoeQuery = document.querySelector("#shoeQuery");
const shoeSize = document.querySelector("#shoeSize");
const searchButton = document.querySelector("#searchButton");
const dealsOnly = document.querySelector("#dealsOnly");
const retailerFilters = document.querySelector("#retailerFilters");
const searchTitle = document.querySelector("#searchTitle");
const searchCount = document.querySelector("#searchCount");
const searchResults = document.querySelector("#searchResults");
const statusPill = document.querySelector("#statusPill");
const statusTitle = document.querySelector("#statusTitle");
const statusDetail = document.querySelector("#statusDetail");
const progressText = document.querySelector("#progressText");
const lastRunText = document.querySelector("#lastRunText");
const progressBar = document.querySelector("#progressBar");
const productsEl = document.querySelector("#products");
const productCount = document.querySelector("#productCount");
const newMatchesEl = document.querySelector("#newMatches");
const matchCount = document.querySelector("#matchCount");
const sightingsEl = document.querySelector("#sightings");
const sightingCount = document.querySelector("#sightingCount");

let pollTimer = null;
let retailersLoaded = false;

async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderProducts(products) {
  productCount.textContent = products.length;
  productsEl.innerHTML = products.map((product) => {
    const rule = product.discount_only ? "Discount only" : "Any stock";
    const sizes = product.required_sizes.length ? `Size ${product.required_sizes.join(", ")}` : "All sizes";
    return `
      <div class="product">
        <div class="product-title">${escapeHtml(product.name)}</div>
        <div class="meta">
          <span class="tag">${escapeHtml(product.sku)}</span>
          <span class="tag ${product.discount_only ? "alert" : ""}">${rule}</span>
          <span class="tag">${escapeHtml(sizes)}</span>
        </div>
      </div>
    `;
  }).join("");
}

function renderMatches(matches) {
  matchCount.textContent = matches.length;
  if (!matches.length) {
    newMatchesEl.className = "empty";
    newMatchesEl.textContent = "No new matches from the latest scan.";
    return;
  }

  newMatchesEl.className = "match-list";
  newMatchesEl.innerHTML = matches.map((match) => {
    const prices = match.prices && match.prices.length
      ? `<span class="tag">${match.prices.map((price) => `$${Number(price).toFixed(2)}`).join(", ")}</span>`
      : "";
    return `
      <div class="match">
        <div class="match-title"><a href="${escapeHtml(match.url)}" target="_blank" rel="noreferrer">${escapeHtml(match.title)}</a></div>
        <div class="meta">
          <span class="tag">${escapeHtml(match.product)}</span>
          <span class="tag">${escapeHtml(match.retailer)}</span>
          <span class="tag">${escapeHtml(match.sku)}</span>
          ${prices}
        </div>
      </div>
    `;
  }).join("");
}

function formatMoney(value) {
  if (value === null || value === undefined) {
    return "Price not shown";
  }
  return `$${Number(value).toFixed(2)}`;
}

function availabilityLabel(value) {
  if (value === "available") {
    return "Available";
  }
  if (value === "unavailable") {
    return "Unavailable";
  }
  return "Possibly available";
}

function renderRetailerFilters(retailers) {
  retailerFilters.innerHTML = retailers.map((retailer) => `
    <label class="retailer-option">
      <input type="checkbox" name="retailer" value="${escapeHtml(retailer.id)}" checked>
      <span>${escapeHtml(retailer.name)}${retailer.source_type === "second_hand" ? " · used" : ""}</span>
    </label>
  `).join("");
  retailersLoaded = true;
}

function renderSearchResults(results, query) {
  searchCount.textContent = results.length;
  searchTitle.textContent = query ? `Results for "${query}"` : "Search Results";

  if (!results.length) {
    searchResults.className = "empty";
    searchResults.textContent = query
      ? "No matching products found from supported retailers. Try a SKU, fewer words, or turn off Deals only."
      : "Search for any shoe name, SKU, or keyword to check supported Australian retailers.";
    return;
  }

  searchResults.className = "result-grid";
  searchResults.innerHTML = results.map((result) => {
    const dealClass = result.is_deal ? "deal" : "";
    const wasPrice = result.was_price ? `<span class="was-price">${formatMoney(result.was_price)}</span>` : "";
    const sourceBadge = result.source_type === "second_hand" ? `<span class="tag alert">Second-hand</span>` : `<span class="tag">Retail</span>`;
    const location = result.location ? `<span class="tag">${escapeHtml(result.location)}</span>` : "";
    const image = result.image_url ? `<img class="result-image" src="${escapeHtml(result.image_url)}" alt="">` : "";
    const confidence = result.query_terms
      ? `${result.matched_terms}/${result.query_terms} terms`
      : `${result.matched_terms} terms`;
    return `
      <article class="result-card">
        ${image}
        <div class="result-topline">
          <span class="retailer-name">${escapeHtml(result.retailer)}</span>
          <span class="availability ${escapeHtml(result.availability)}">${availabilityLabel(result.availability)}</span>
        </div>
        <h3><a href="${escapeHtml(result.url)}" target="_blank" rel="noreferrer">${escapeHtml(result.title)}</a></h3>
        <div class="price-row">
          <span class="price">${formatMoney(result.price)}</span>
          ${wasPrice}
          <span class="deal-badge ${dealClass}">${result.is_deal ? "Deal detected" : "No deal signal"}</span>
        </div>
        <div class="meta">
          ${sourceBadge}
          <span class="tag">${escapeHtml(confidence)}</span>
          ${location}
          ${result.requested_size ? `<span class="tag ${result.size_match === "found" ? "alert" : ""}">US ${escapeHtml(result.requested_size)} ${result.size_match === "found" ? "found" : "not shown"}</span>` : ""}
          <a href="${escapeHtml(result.source_search_url)}" target="_blank" rel="noreferrer">Retailer search</a>
        </div>
      </article>
    `;
  }).join("");
}

function renderSightings(sightings) {
  sightingCount.textContent = sightings.length;
  if (!sightings.length) {
    sightingsEl.className = "sightings empty";
    sightingsEl.textContent = "No saved sightings yet.";
    return;
  }

  sightingsEl.className = "sighting-list";
  sightingsEl.innerHTML = sightings.map((sighting) => `
    <div class="sighting">
      <div class="sighting-title"><a href="${escapeHtml(sighting.url)}" target="_blank" rel="noreferrer">${escapeHtml(sighting.title)}</a></div>
      <div class="meta">
        <span class="tag">${escapeHtml(sighting.retailer)}</span>
        ${sighting.source_type ? `<span class="tag">${escapeHtml(sighting.source_type === "second_hand" ? "Second-hand" : "Retail")}</span>` : ""}
        ${sighting.location ? `<span class="tag">${escapeHtml(sighting.location)}</span>` : ""}
        <span class="tag">${escapeHtml(sighting.first_seen_at)}</span>
      </div>
      <p class="snippet">${escapeHtml(sighting.matched_text).slice(0, 220)}</p>
    </div>
  `).join("");
}

function renderStatus(status) {
  const total = status.total || 0;
  const current = status.current || 0;
  const percent = total ? Math.round((current / total) * 100) : 0;

  scanButton.disabled = Boolean(status.running);
  progressBar.style.width = `${percent}%`;
  progressText.textContent = `${current} of ${total} checks`;
  lastRunText.textContent = status.last_finished_at
    ? `Last finished ${status.last_finished_at}`
    : status.last_started_at
      ? `Started ${status.last_started_at}`
      : "No scan yet";

  statusPill.className = "pill";
  if (status.error) {
    statusPill.classList.add("error");
    statusPill.textContent = "Error";
    statusTitle.textContent = "Scan failed";
    statusDetail.textContent = status.error;
    return;
  }

  if (status.running) {
    statusPill.classList.add("running");
    statusPill.textContent = "Running";
    statusTitle.textContent = status.retailer ? `Checking ${status.retailer}` : "Starting scan";
    statusDetail.textContent = status.product
      ? `${status.product} (${status.sku})`
      : "Preparing retailer checks.";
    return;
  }

  statusPill.classList.add("idle");
  statusPill.textContent = "Idle";
  statusTitle.textContent = status.last_finished_at ? "Scan complete" : "Ready to scan";
  statusDetail.textContent = status.last_finished_at
    ? `${status.new_hits.length} new match${status.new_hits.length === 1 ? "" : "es"} found in the latest scan.`
    : "Click Run scan to check all configured retailers.";
}

async function refreshDashboard() {
  const requests = [
    getJson("/api/status"),
    getJson("/api/products"),
    getJson("/api/sightings"),
  ];
  if (!retailersLoaded) {
    requests.push(getJson("/api/retailers"));
  }

  const [status, products, sightings, retailers] = await Promise.all(requests);

  renderStatus(status);
  renderProducts(products.products);
  renderMatches(status.new_hits || []);
  renderSightings(sightings.sightings);
  if (retailers) {
    renderRetailerFilters(retailers.retailers);
  }

  if (status.running && !pollTimer) {
    pollTimer = window.setInterval(refreshDashboard, 1200);
  }
  if (!status.running && pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function searchShoes(event) {
  event.preventDefault();
  const query = shoeQuery.value.trim();
  const size = shoeSize.value.trim();
  if (!query) {
    shoeQuery.focus();
    return;
  }

  const selectedRetailers = [...document.querySelectorAll('input[name="retailer"]:checked')]
    .map((input) => input.value);
  const params = new URLSearchParams({
    q: query,
    deals_only: dealsOnly.checked ? "true" : "false",
  });
  const sourceType = document.querySelector('input[name="sourceType"]:checked')?.value || "all";
  params.set("source_type", sourceType);
  if (size) {
    params.set("size", size);
  }
  if (selectedRetailers.length) {
    params.set("retailers", selectedRetailers.join(","));
  }

  searchButton.disabled = true;
  searchResults.className = "empty";
  searchResults.textContent = "Searching supported Australian retailers...";

  try {
    const payload = await getJson(`/api/search?${params.toString()}`);
    renderSearchResults(payload.results, payload.query);
  } catch (error) {
    searchResults.className = "empty error-text";
    searchResults.textContent = error.message;
  } finally {
    searchButton.disabled = false;
  }
}

async function startScan() {
  try {
    scanButton.disabled = true;
    await getJson("/api/scan", { method: "POST" });
    await refreshDashboard();
  } catch (error) {
    statusPill.className = "pill error";
    statusPill.textContent = "Error";
    statusTitle.textContent = "Could not start scan";
    statusDetail.textContent = error.message;
    scanButton.disabled = false;
  }
}

scanButton.addEventListener("click", startScan);
refreshButton.addEventListener("click", refreshDashboard);
searchForm.addEventListener("submit", searchShoes);
refreshDashboard();
