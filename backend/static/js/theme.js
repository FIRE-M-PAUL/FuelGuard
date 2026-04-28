(() => {
    const THEME_KEY = "fuelguard-theme";
    const root = document.documentElement;
    const body = document.body;

    if (!root || !body) return;

    const validTheme = (value) => (value === "dark" ? "dark" : "light");

    const applyTheme = (theme) => {
        const next = validTheme(theme);
        root.setAttribute("data-theme", next);
        localStorage.setItem(THEME_KEY, next);
    };

    const ensureToggle = () => {
        let btn = document.querySelector("[data-theme-toggle]");
        if (btn) return btn;

        btn = document.createElement("button");
        btn.type = "button";
        btn.className = "theme-toggle";
        btn.setAttribute("data-theme-toggle", "true");
        btn.setAttribute("aria-label", "Toggle color theme");
        btn.textContent = "Toggle Theme";
        body.appendChild(btn);
        return btn;
    };

    const saved = localStorage.getItem(THEME_KEY);
    if (saved) {
        root.setAttribute("data-theme", validTheme(saved));
    } else if (!root.getAttribute("data-theme")) {
        root.setAttribute("data-theme", "light");
    }

    const toggleBtn = ensureToggle();
    toggleBtn.addEventListener("click", () => {
        const current = root.getAttribute("data-theme");
        applyTheme(current === "dark" ? "light" : "dark");
    });
})();
