(() => {
  const form = document.getElementById("loginForm");
  const roleSelect = document.getElementById("role");
  if (!form || !roleSelect) return;

  const subtitle = document.getElementById("roleSubtitle");
  const identityLabel = document.getElementById("identityLabel");
  const selected = roleSelect.dataset.selected || "sales";
  roleSelect.value = selected;

  const titles = {
    sales: "Salesperson login",
    manager: "Manager login",
    accountant: "Accountant login",
  };

  const sync = () => {
    const role = roleSelect.value || "sales";
    form.action = `/login/${role}`;
    if (subtitle) subtitle.textContent = `${titles[role]} using your email or username.`;
    if (identityLabel) identityLabel.textContent = "Email or Username";
  };

  roleSelect.addEventListener("change", sync);
  sync();
})();
