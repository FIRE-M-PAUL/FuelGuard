(() => {
  const qty = document.getElementById("quantity");
  const price = document.getElementById("price_per_litre");
  const total = document.getElementById("total_cost");
  if (!qty || !price || !total) return;

  const recalc = () => {
    const q = parseFloat(qty.value) || 0;
    const p = parseFloat(price.value) || 0;
    const t = Math.round(q * p * 100) / 100;
    total.value = t > 0 ? t.toFixed(2) : "";
  };

  qty.addEventListener("input", recalc);
  price.addEventListener("input", recalc);
  recalc();
})();
