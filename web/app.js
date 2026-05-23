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
const schedulerText = document.querySelector("#schedulerText");
const progressBar = document.querySelector("#progressBar");
const productsEl = document.querySelector("#products");
const productCount = document.querySelector("#productCount");
const newMatchesEl = document.querySelector("#newMatches");
const matchCount = document.querySelector("#matchCount");
const sightingsEl = document.querySelector("#sightings");
const sightingCount = document.querySelector("#sightingCount");
const sourceHealthEl = document.querySelector("#sourceHealth");
const healthCount = document.querySelector("#healthCount");
const productAdminForm = document.querySelector("#productAdminForm");
const adminLabel = document.querySelector("#adminLabel");
const adminSku = document.querySelector("#adminSku");
const adminKeywords = document.querySelector("#adminKeywords");
const adminSizes = document.querySelector("#adminSizes");
const adminAlertRule = document.querySelector("#adminAlertRule");
const saveProductsButton = document.querySelector("#saveProductsButton");
const adminStatus = document.querySelector("#adminStatus");
const filterAvailability = document.querySelector("#filterAvailability");
const filterCondition = document.querySelector("#filterCondition");
const filterConfidence = document.querySelector("#filterConfidence");
const filterMinPrice = document.querySelector("#filterMinPrice");
const filterMaxPrice = document.querySelector("#filterMaxPrice");
const applySightingFilters = document.querySelector("#applySightingFilters");
const exportSightings = document.querySelector("#exportSightings");

let pollTimer = null;
let retailersLoaded = false;
let productState = [];
let retailerState = [];

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
  productState = products.map((product) => ({
    label: product.name,
    sku: product.sku,
    keywords: product.keywords || [],
    retailers: product.retailers || [],
    alert_rule: product.alert_rule || (product.discount_only ? "discount_only" : "any_stock"),
    required_sizes: product.required_sizes || [],
  }));
  productCount.textContent = products.length;
  productsEl.innerHTML = products.map((product, index) => {
    const rule = product.discount_only ? "Discount only" : "Any stock";
    const sizes = product.required_sizes.length ? `Size ${product.required_sizes.join(", ")}` : "All sizes";
    return `
      <div class="product">
        <div class="product-title">${escapeHtml(product.name)}</div>
        <div class="meta">
          <span class="tag">${escapeHtml(product.sku)}</span>
          <span class="tag ${product.discount_only ? "alert" : ""}">${rule}</span>
          <span class="tag">${escapeHtml(sizes)}</span>
          <span class="tag">${escapeHtml((product.keywords || []).join(", ") || "No keywords")}</span>
          <button class="mini-button" type="button" data-remove-product="${index}">Remove</button>
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
          <span class="tag ${match.match_confidence === "high" ? "alert" : ""}">${escapeHtml(match.match_confidence || "low")} confidence</span>
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
  retailerState = retailers;
  retailerFilters.innerHTML = retailers.map((retailer) => `
    <label class="retailer-option">
      <input type="checkbox" name="retailer" value="${escapeHtml(retailer.id)}" checked>
      <span>${escapeHtml(retailer.name)}${retailer.source_type === "second_hand" ? " · used" : ""}</span>
    </label>
  `).join("");
  retailersLoaded = true;
}

function sightingFilterParams() {
  const params = new URLSearchParams();
  if (filterAvailability.value) params.set("availability", filterAvailability.value);
  if (filterCondition.value) params.set("condition_type", filterCondition.value);
  if (filterConfidence.value) params.set("confidence", filterConfidence.value);
  if (filterMinPrice.value) params.set("min_price", filterMinPrice.value);
  if (filterMaxPrice.value) params.set("max_price", filterMaxPrice.value);
  return params;
}

function updateExportLink() {
  const params = sightingFilterParams();
  exportSightings.href = `/api/sightings.csv${params.toString() ? `?${params.toString()}` : ""}`;
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
    const wasPrice = result.was_price ? `<span class="was-price">${formatMoney(result.was_price)}</span>` : "";
    const sourceBadge = result.source_type === "second_hand" ? `<span class="tag alert">Second-hand</span>` : `<span class="tag">Retail</span>`;
    const location = result.location ? `<span class="tag">${escapeHtml(result.location)}</span>` : "";
    const image = result.image_url ? `<img class="result-image" src="${escapeHtml(result.image_url)}" alt="">` : "";
    const confidence = result.query_terms
      ? `${result.matched_terms}/${result.query_terms} terms`
      : `${result.matched_terms} terms`;
    const priceBlock = result.price === null || result.price === undefined
      ? `<div class="price-muted">Price not shown</div>`
      : `<div class="price-stack"><span class="price">${formatMoney(result.price)}</span>${wasPrice}</div>`;
    const dealBadge = result.is_deal ? `<span class="deal-badge deal">Deal detected</span>` : "";
    const terms = result.matched_term_values && result.matched_term_values.length
      ? `<span class="tag">Matched ${escapeHtml(result.matched_term_values.join(", "))}</span>`
      : `<span class="tag">${escapeHtml(confidence)}</span>`;
    return `
      <article class="result-card">
        ${image}
        <div class="result-topline">
          <span class="retailer-name">${escapeHtml(result.retailer)}</span>
          <span class="availability ${escapeHtml(result.availability)}">${availabilityLabel(result.availability)}</span>
        </div>
        <h3><a href="${escapeHtml(result.url)}" target="_blank" rel="noreferrer">${escapeHtml(result.title)}</a></h3>
        <div class="price-row">
          ${priceBlock}
          ${dealBadge}
        </div>
        <div class="meta">
          ${sourceBadge}
          ${terms}
          <span class="tag ${result.match_confidence === "high" ? "alert" : ""}">${escapeHtml(result.match_confidence || "low")} confidence</span>
          ${location}
          ${result.requested_size ? `<span class="tag ${result.size_match === "found" ? "alert" : ""}">US ${escapeHtml(result.requested_size)} ${result.size_match === "found" ? "found" : "not shown"}</span>` : ""}
        </div>
        <div class="result-actions">
          <a class="listing-link" href="${escapeHtml(result.url)}" target="_blank" rel="noreferrer">View listing</a>
          <a href="${escapeHtml(result.source_search_url)}" target="_blank" rel="noreferrer">Source search</a>
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
        ${sighting.match_confidence ? `<span class="tag ${sighting.match_confidence === "high" ? "alert" : ""}">${escapeHtml(sighting.match_confidence)} confidence</span>` : ""}
        ${sighting.current_price !== null && sighting.current_price !== undefined ? `<span class="tag">${formatMoney(sighting.current_price)}</span>` : ""}
        <span class="tag">${escapeHtml(sighting.first_seen_at)}</span>
      </div>
      <p class="snippet">${escapeHtml((sighting.matched_terms || []).join(", ") || sighting.matched_text).slice(0, 220)}</p>
    </div>
  `).join("");
}

function renderHealth(health) {
  healthCount.textContent = health.length;
  if (!health.length) {
    sourceHealthEl.className = "empty";
    sourceHealthEl.textContent = "No source health data yet.";
    return;
  }

  sourceHealthEl.className = "health-list";
  sourceHealthEl.innerHTML = health.map((source) => {
    const failureClass = source.consecutive_failures > 0 ? "alert" : "";
    const status = source.consecutive_failures > 0
      ? `${source.consecutive_failures} failure${source.consecutive_failures === 1 ? "" : "s"}`
      : "Healthy";
    const latestError = source.last_error_type
      ? `<p class="snippet">${escapeHtml(source.last_error_type)}: ${escapeHtml(source.last_error_message || "")}</p>`
      : "";
    return `
      <div class="health-item">
        <div class="product-title">${escapeHtml(source.retailer_id)}</div>
        <div class="meta">
          <span class="tag ${failureClass}">${escapeHtml(status)}</span>
          <span class="tag">Last attempt ${escapeHtml(source.last_attempt_at || "never")}</span>
          <span class="tag">Last success ${escapeHtml(source.last_success_at || "never")}</span>
        </div>
        ${latestError}
      </div>
    `;
  }).join("");
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
  schedulerText.textContent = status.scheduler_enabled
    ? `Scheduled every ${status.scan_interval_minutes} minutes. Next run ${status.scheduler_next_run_at || "pending"}.`
    : "Scheduled scans disabled.";

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
    getJson(`/api/sightings?${sightingFilterParams().toString()}`),
    getJson("/api/health"),
  ];
  if (!retailersLoaded) {
    requests.push(getJson("/api/retailers"));
  }

  const [status, products, sightings, health, retailers] = await Promise.all(requests);

  renderStatus(status);
  renderProducts(products.products);
  renderMatches(status.new_hits || []);
  renderSightings(sightings.sightings);
  renderHealth(health.health || []);
  updateExportLink();
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

function productPayloadForRender(product) {
  return {
    name: product.label,
    sku: product.sku,
    keywords: product.keywords,
    retailers: product.retailers,
    alert_rule: product.alert_rule,
    discount_only: product.alert_rule === "discount_only",
    required_sizes: product.required_sizes,
  };
}

function addProduct(event) {
  event.preventDefault();
  const label = adminLabel.value.trim();
  const sku = adminSku.value.trim();
  if (!label || !sku) {
    adminStatus.textContent = "Missing";
    return;
  }
  productState.push({
    label,
    sku,
    keywords: adminKeywords.value.split(",").map((value) => value.trim()).filter(Boolean),
    retailers: retailerState.map((retailer) => retailer.id),
    alert_rule: adminAlertRule.value,
    required_sizes: adminSizes.value.split(",").map((value) => value.trim()).filter(Boolean),
  });
  adminLabel.value = "";
  adminSku.value = "";
  adminKeywords.value = "";
  adminSizes.value = "";
  renderProducts(productState.map(productPayloadForRender));
  adminStatus.textContent = "Unsaved";
}

async function saveProducts() {
  saveProductsButton.disabled = true;
  try {
    const payload = await getJson("/api/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ products: productState }),
    });
    renderProducts(payload.products);
    adminStatus.textContent = "Saved";
  } catch (error) {
    adminStatus.textContent = "Error";
  } finally {
    saveProductsButton.disabled = false;
  }
}

scanButton.addEventListener("click", startScan);
refreshButton.addEventListener("click", refreshDashboard);
searchForm.addEventListener("submit", searchShoes);
productAdminForm.addEventListener("submit", addProduct);
saveProductsButton.addEventListener("click", saveProducts);
applySightingFilters.addEventListener("click", refreshDashboard);
productsEl.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-product]");
  if (!button) return;
  productState.splice(Number(button.dataset.removeProduct), 1);
  renderProducts(productState.map(productPayloadForRender));
  adminStatus.textContent = "Unsaved";
});
refreshDashboard();
