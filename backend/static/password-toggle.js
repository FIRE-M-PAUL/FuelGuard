(() => {
  const passwordInputs = document.querySelectorAll('input[type="password"][data-password-toggle="true"]');
  passwordInputs.forEach((input) => {
    const field = input.parentElement;
    if (!field || !field.classList.contains("password-field")) return;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "password-toggle";
    btn.setAttribute("aria-label", "Show password");
    btn.textContent = "👁";

    btn.addEventListener("click", () => {
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      btn.setAttribute("aria-label", showing ? "Show password" : "Hide password");
      btn.textContent = showing ? "👁" : "🙈";
    });

    field.appendChild(btn);
  });
})();
