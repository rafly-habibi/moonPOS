const state = {
  products: [],
  cart: new Map(),
  refreshInFlight: false,
  toastTimer: null,
};

const currencyFmt = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  maximumFractionDigits: 0,
});

const dateFmt = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeStyle: "short",
});

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function asCurrency(value) {
  return currencyFmt.format(toNumber(value));
}

function asDate(value) {
  if (!value) {
    return "-";
  }
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) {
    return value;
  }
  return dateFmt.format(dt);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showToast(message, type = "success") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast ${type}`;
  el.classList.remove("hidden");

  if (state.toastTimer) {
    clearTimeout(state.toastTimer);
  }
  state.toastTimer = setTimeout(() => {
    el.classList.add("hidden");
  }, 3200);
}

async function api(path, options = {}) {
  const finalOptions = { ...options };
  const headers = { ...(options.headers || {}) };
  if (finalOptions.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  finalOptions.headers = headers;

  const response = await fetch(path, finalOptions);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch (_err) {
      const raw = await response.text();
      if (raw) detail = raw;
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function setSyncStatus(text) {
  document.getElementById("syncStatus").textContent = text;
}

function getProductById(productId) {
  return state.products.find((product) => product.id === productId) || null;
}

function getCartSubtotal() {
  let subtotal = 0;
  for (const [productId, qty] of state.cart.entries()) {
    const product = getProductById(productId);
    if (!product) continue;
    subtotal += toNumber(product.sell_price) * qty;
  }
  return subtotal;
}

function getCartTotal() {
  const subtotal = getCartSubtotal();
  const discount = toNumber(document.getElementById("discountInput").value);
  const tax = toNumber(document.getElementById("taxInput").value);
  return Math.max(0, subtotal - discount + tax);
}

function refreshCartTotalUI() {
  document.getElementById("cartTotalValue").textContent = asCurrency(getCartTotal());
}

function normalizeCartWithStock() {
  const staleIds = [];
  for (const [productId, qty] of state.cart.entries()) {
    const product = getProductById(productId);
    if (!product || product.stock_qty <= 0) {
      staleIds.push(productId);
      continue;
    }
    if (qty > product.stock_qty) {
      state.cart.set(productId, product.stock_qty);
    }
  }
  staleIds.forEach((id) => state.cart.delete(id));
}

function renderProductCatalog() {
  const container = document.getElementById("productCatalog");
  const query = document.getElementById("productSearch").value.trim().toLowerCase();

  const products = state.products.filter((product) => {
    const haystack = `${product.name} ${product.sku} ${product.category || ""}`.toLowerCase();
    return haystack.includes(query);
  });

  if (!products.length) {
    container.innerHTML = "<p class='catalog-meta'>Produk tidak ditemukan.</p>";
    return;
  }

  container.innerHTML = products
    .map((product) => {
      const low = product.stock_qty <= product.min_stock;
      return `
        <article class="catalog-item">
          <div>
            <p class="catalog-title">${escapeHtml(product.name)}</p>
            <p class="catalog-meta">${escapeHtml(product.sku)} | ${escapeHtml(product.category || "Tanpa kategori")}</p>
            <p class="catalog-meta">Harga: ${asCurrency(product.sell_price)} | Stok: ${product.stock_qty} ${low ? "(Low)" : ""}</p>
          </div>
          <div class="catalog-controls">
            <input type="number" min="1" max="${product.stock_qty}" value="1" data-qty-input="${product.id}" ${
              product.stock_qty <= 0 ? "disabled" : ""
            } />
            <button type="button" class="btn btn-secondary" data-add-product="${product.id}" ${
              product.stock_qty <= 0 ? "disabled" : ""
            }>Tambah Keranjang</button>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderCart() {
  const body = document.getElementById("cartTableBody");
  if (!state.cart.size) {
    body.innerHTML = "<tr><td colspan='4'>Keranjang masih kosong.</td></tr>";
    refreshCartTotalUI();
    return;
  }

  const rows = [];
  for (const [productId, qty] of state.cart.entries()) {
    const product = getProductById(productId);
    if (!product) continue;
    const subtotal = toNumber(product.sell_price) * qty;
    rows.push(`
      <tr>
        <td>${escapeHtml(product.name)}</td>
        <td>
          <input type="number" min="1" max="${product.stock_qty}" value="${qty}" data-cart-qty="${productId}" />
        </td>
        <td>${asCurrency(subtotal)}</td>
        <td>
          <button type="button" class="btn btn-danger" data-remove-cart="${productId}">Hapus</button>
        </td>
      </tr>
    `);
  }

  body.innerHTML = rows.join("");
  refreshCartTotalUI();
}

function renderRecentOrders(orders) {
  const body = document.getElementById("recentOrdersBody");
  if (!orders.length) {
    body.innerHTML = "<tr><td colspan='4'>Belum ada order.</td></tr>";
    return;
  }

  body.innerHTML = orders
    .map(
      (order) => `
      <tr>
        <td class="mono">${escapeHtml(order.order_number)}</td>
        <td>${asDate(order.created_at)}</td>
        <td>${escapeHtml(order.payment_method)}</td>
        <td>${asCurrency(order.total)}</td>
      </tr>
    `
    )
    .join("");
}

function renderInventoryTable() {
  const body = document.getElementById("inventoryTableBody");
  if (!state.products.length) {
    body.innerHTML = "<tr><td colspan='7'>Tidak ada data produk.</td></tr>";
    return;
  }

  body.innerHTML = state.products
    .map((product) => {
      const low = product.stock_qty <= product.min_stock;
      return `
      <tr>
        <td>${escapeHtml(product.sku)}</td>
        <td>${escapeHtml(product.name)}</td>
        <td>${escapeHtml(product.category || "-")}</td>
        <td>${asCurrency(product.sell_price)}</td>
        <td>${product.stock_qty}</td>
        <td>${product.min_stock}</td>
        <td><span class="chip ${low ? "low" : "ok"}">${low ? "Low stock" : "Aman"}</span></td>
      </tr>
    `;
    })
    .join("");
}

function populateAdjustProductSelect() {
  const select = document.getElementById("adjustProduct");
  select.innerHTML = state.products
    .map(
      (product) =>
        `<option value="${product.id}">${escapeHtml(product.name)} (${escapeHtml(product.sku)})</option>`
    )
    .join("");
}

function renderInventoryCounters() {
  const lowCount = state.products.filter((p) => p.stock_qty <= p.min_stock).length;
  document.getElementById("inventoryCount").textContent = String(state.products.length);
  document.getElementById("lowStockCount").textContent = String(lowCount);
}

function renderMovements(movements) {
  const body = document.getElementById("movementTableBody");
  if (!movements.length) {
    body.innerHTML = "<tr><td colspan='7'>Belum ada movement.</td></tr>";
    return;
  }

  body.innerHTML = movements
    .map(
      (item) => `
      <tr>
        <td>${asDate(item.created_at)}</td>
        <td>${item.product_id}</td>
        <td>${escapeHtml(item.movement_type)}</td>
        <td>${item.quantity_change > 0 ? "+" : ""}${item.quantity_change}</td>
        <td>${item.before_qty}</td>
        <td>${item.after_qty}</td>
        <td>${escapeHtml(item.reason || "-")}</td>
      </tr>
    `
    )
    .join("");
}

function renderTrialBalance(rows) {
  const body = document.getElementById("trialBalanceBody");
  if (!rows.length) {
    body.innerHTML = "<tr><td colspan='4'>Belum ada jurnal.</td></tr>";
    return;
  }

  body.innerHTML = rows
    .map(
      (row) => `
      <tr>
        <td>${escapeHtml(row.account)}</td>
        <td>${asCurrency(row.debit)}</td>
        <td>${asCurrency(row.credit)}</td>
        <td>${asCurrency(row.balance)}</td>
      </tr>
    `
    )
    .join("");
}

function renderLedger(entries) {
  const body = document.getElementById("ledgerBody");
  if (!entries.length) {
    body.innerHTML = "<tr><td colspan='6'>Belum ada ledger entry.</td></tr>";
    return;
  }

  body.innerHTML = entries
    .map(
      (entry) => `
      <tr>
        <td>${asDate(entry.tx_date)}</td>
        <td class="mono">${escapeHtml(entry.tx_ref)}</td>
        <td>${escapeHtml(entry.account)}</td>
        <td>${escapeHtml(entry.direction)}</td>
        <td>${asCurrency(entry.amount)}</td>
        <td>${escapeHtml(entry.note || "-")}</td>
      </tr>
    `
    )
    .join("");
}

function renderAnalytics(sales, topProducts, valuation) {
  document.getElementById("kpiRevenue").textContent = asCurrency(sales.revenue);
  document.getElementById("kpiProfit").textContent = asCurrency(sales.gross_profit);
  document.getElementById("kpiOrderCount").textContent = String(sales.order_count);
  document.getElementById("kpiAov").textContent = asCurrency(sales.avg_order_value);
  document.getElementById("kpiInventoryCost").textContent = asCurrency(
    valuation.inventory_cost_value
  );
  document.getElementById("kpiPotentialMargin").textContent = asCurrency(
    valuation.potential_margin
  );

  const body = document.getElementById("topProductsBody");
  if (!topProducts.length) {
    body.innerHTML = "<tr><td colspan='3'>Belum ada data penjualan produk.</td></tr>";
    return;
  }
  body.innerHTML = topProducts
    .map(
      (item) => `
      <tr>
        <td>${escapeHtml(item.product_name)}</td>
        <td>${item.qty_sold}</td>
        <td>${asCurrency(item.revenue)}</td>
      </tr>
    `
    )
    .join("");
}

async function loadProducts() {
  const products = await api("/products");
  state.products = products;
  normalizeCartWithStock();
  renderProductCatalog();
  renderCart();
  renderInventoryTable();
  populateAdjustProductSelect();
  renderInventoryCounters();
}

async function loadMovements() {
  const movements = await api("/inventory/movements?limit=80");
  renderMovements(movements);
}

async function loadRecentOrders() {
  const orders = await api("/orders?limit=20");
  renderRecentOrders(orders);
}

async function loadBookkeeping() {
  const [trialBalance, ledger] = await Promise.all([
    api("/bookkeeping/trial-balance"),
    api("/bookkeeping/ledger?limit=120"),
  ]);
  renderTrialBalance(trialBalance);
  renderLedger(ledger);
}

async function loadAnalytics() {
  const [sales, topProducts, valuation] = await Promise.all([
    api("/analytics/sales-summary"),
    api("/analytics/top-products?limit=10"),
    api("/analytics/stock-valuation"),
  ]);
  renderAnalytics(sales, topProducts, valuation);
}

async function refreshAllData({ withToast = false } = {}) {
  if (state.refreshInFlight) return;
  state.refreshInFlight = true;
  setSyncStatus("Sinkronisasi data...");
  try {
    await Promise.all([
      loadProducts(),
      loadMovements(),
      loadRecentOrders(),
      loadBookkeeping(),
      loadAnalytics(),
    ]);
    setSyncStatus(`Sinkron: ${asDate(new Date().toISOString())}`);
    if (withToast) showToast("Data berhasil di-refresh.", "success");
  } catch (error) {
    setSyncStatus("Sync gagal");
    showToast(error.message, "error");
  } finally {
    state.refreshInFlight = false;
  }
}

function setActiveTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    const active = btn.dataset.tab === tabName;
    btn.classList.toggle("is-active", active);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `tab-${tabName}`);
  });
}

function bindTabNavigation() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
  });
}

function bindCatalogActions() {
  const catalog = document.getElementById("productCatalog");
  catalog.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const productIdRaw = target.getAttribute("data-add-product");
    if (!productIdRaw) return;

    const productId = Number(productIdRaw);
    const qtyInput = catalog.querySelector(`input[data-qty-input="${productId}"]`);
    const qty = toNumber(qtyInput?.value || 1);
    if (qty <= 0) {
      showToast("Qty harus lebih dari 0.", "error");
      return;
    }

    const product = getProductById(productId);
    if (!product) return;

    const currentQty = state.cart.get(productId) || 0;
    const nextQty = currentQty + qty;
    if (nextQty > product.stock_qty) {
      showToast(`Stok ${product.name} tidak cukup.`, "error");
      return;
    }
    state.cart.set(productId, nextQty);
    renderCart();
    showToast(`${product.name} ditambahkan ke keranjang.`);
  });

  document.getElementById("productSearch").addEventListener("input", renderProductCatalog);
}

function bindCartActions() {
  document.getElementById("clearCartBtn").addEventListener("click", () => {
    state.cart.clear();
    renderCart();
    showToast("Keranjang dikosongkan.");
  });

  const cartBody = document.getElementById("cartTableBody");
  cartBody.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const removeRaw = target.getAttribute("data-remove-cart");
    if (!removeRaw) return;
    state.cart.delete(Number(removeRaw));
    renderCart();
  });

  cartBody.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    const cartIdRaw = target.getAttribute("data-cart-qty");
    if (!cartIdRaw) return;

    const productId = Number(cartIdRaw);
    const product = getProductById(productId);
    if (!product) return;
    let qty = Math.floor(toNumber(target.value));
    if (qty < 1) qty = 1;
    if (qty > product.stock_qty) qty = product.stock_qty;

    target.value = String(qty);
    state.cart.set(productId, qty);
    refreshCartTotalUI();
  });

  ["discountInput", "taxInput"].forEach((id) => {
    document.getElementById(id).addEventListener("input", refreshCartTotalUI);
  });
}

function bindCheckoutForm() {
  const form = document.getElementById("checkoutForm");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!state.cart.size) {
      showToast("Keranjang masih kosong.", "error");
      return;
    }

    const payload = {
      items: [...state.cart.entries()].map(([product_id, quantity]) => ({ product_id, quantity })),
      discount: toNumber(document.getElementById("discountInput").value),
      tax: toNumber(document.getElementById("taxInput").value),
      payment_method: document.getElementById("paymentMethodInput").value,
    };

    try {
      const result = await api("/checkout", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const output = document.getElementById("checkoutResult");
      output.classList.remove("hidden");
      output.innerHTML = `
        <p><strong>Checkout sukses</strong></p>
        <p>No Order: <span class="mono">${escapeHtml(result.order_number)}</span></p>
        <p>Total: ${asCurrency(result.total)} | COGS: ${asCurrency(result.cogs)} | Gross Profit: ${asCurrency(result.gross_profit)}</p>
      `;

      state.cart.clear();
      form.reset();
      document.getElementById("discountInput").value = "0";
      document.getElementById("taxInput").value = "0";
      refreshCartTotalUI();
      await refreshAllData();
      showToast(`Order ${result.order_number} berhasil dibuat.`);
    } catch (error) {
      showToast(error.message, "error");
    }
  });
}

function bindProductForm() {
  const form = document.getElementById("productForm");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const payload = {
      sku: String(formData.get("sku") || "").trim(),
      name: String(formData.get("name") || "").trim(),
      category: String(formData.get("category") || "").trim() || null,
      sell_price: toNumber(formData.get("sell_price")),
      cost_price: toNumber(formData.get("cost_price")),
      stock_qty: Math.max(0, Math.floor(toNumber(formData.get("stock_qty")))),
      min_stock: Math.max(0, Math.floor(toNumber(formData.get("min_stock")))),
    };

    try {
      await api("/products", { method: "POST", body: JSON.stringify(payload) });
      form.reset();
      form.stock_qty.value = "0";
      form.min_stock.value = "5";
      await refreshAllData();
      showToast("Produk baru berhasil disimpan.");
    } catch (error) {
      showToast(error.message, "error");
    }
  });
}

function bindAdjustForm() {
  const form = document.getElementById("adjustForm");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      product_id: Number(document.getElementById("adjustProduct").value),
      quantity_change: Math.floor(toNumber(document.getElementById("adjustQty").value)),
      reason: String(document.getElementById("adjustReason").value || "").trim() || null,
      counterparty_account:
        String(document.getElementById("adjustAccount").value || "").trim() || null,
    };

    if (!payload.product_id || !payload.quantity_change) {
      showToast("Pilih produk dan isi quantity change (tidak boleh 0).", "error");
      return;
    }

    try {
      await api("/inventory/adjust", { method: "POST", body: JSON.stringify(payload) });
      form.reset();
      await refreshAllData();
      showToast("Adjustment stok berhasil dicatat.");
    } catch (error) {
      showToast(error.message, "error");
    }
  });
}

function bindRefreshButton() {
  document.getElementById("refreshAllBtn").addEventListener("click", () => {
    refreshAllData({ withToast: true });
  });
}

function bootstrap() {
  bindTabNavigation();
  bindCatalogActions();
  bindCartActions();
  bindCheckoutForm();
  bindProductForm();
  bindAdjustForm();
  bindRefreshButton();
  renderCart();
  refreshAllData();
}

window.addEventListener("DOMContentLoaded", bootstrap);
