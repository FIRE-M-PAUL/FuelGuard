(() => {
  // Total price (K) = selling price per litre × quantity (litres). Server recomputes on submit.
  const fuelSel = document.getElementById("fuel_type");
  const qty = document.getElementById("quantity");
  const price = document.getElementById("price_per_litre");
  const total = document.getElementById("total_amount");
  if (!fuelSel || !qty || !price || !total) return;

  const listPrices = window.FUEL_RETAIL_PRICES || {};

  const unitPrice = () => {
    const p = parseFloat(listPrices[fuelSel.value]);
    return Number.isFinite(p) && p > 0 ? p : 0;
  };

  const recalc = () => {
    const p = unitPrice();
    price.value = p > 0 ? p.toFixed(2) : "";
    const q = parseFloat(qty.value) || 0;
    const t = Math.round(q * p * 100) / 100;
    total.value = t > 0 ? t.toFixed(2) : "";
  };

  fuelSel.addEventListener("change", recalc);
  qty.addEventListener("input", recalc);
  recalc();
})();
